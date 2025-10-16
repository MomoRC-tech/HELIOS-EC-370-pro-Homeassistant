from __future__ import annotations

import os
import time
import threading
import queue
import logging
import html
from typing import Optional, Dict, Any, List
import json

from ..const import HeliosVar, CLIENT_ID
from ..parser import _checksum, _decode_sequence

_LOGGER = logging.getLogger(__name__)


class Rs485Logger:
    """Non-intrusive RS-485 stream logger.

    Feed it RX/TX byte chunks; it reconstructs frames and writes line-based logs.
    - Thread-safe, minimal overhead on ingest (queues and returns immediately).
    - Worker thread parses and writes to disk.
    """

    def __init__(self, hass, base_path: Optional[str] = None, raw_only: bool = False):
        self._hass = hass
        self._running = False
        self._rx_buf = bytearray()
        self._tx_buf = bytearray()
        self._q: queue.Queue = queue.Queue(maxsize=1000)
        self._thread: Optional[threading.Thread] = None
        self._file = None
        self._raw_file = None
        self._raw_html_file = None
        self._path = self._make_path(base_path)
        self._raw_path = self._make_raw_path(self._path)
        self._raw_only = bool(raw_only)
        self._raw_html_path = self._make_raw_html_path(self._path)
        # Stats and timing
        self._start_mono: float = 0.0
        self._stats: Dict[str, Dict[str, Any]] = {
            "ping": {"count": 0, "last": None, "intervals": []},
            "broadcast": {"count": 0, "last": None, "intervals": []},
            "ack": {"count": 0, "last": None, "intervals": []},
            "known": {"count": 0, "last": None, "intervals": []},
            "unknown": {"count": 0, "last": None, "intervals": []},
            "garbage": {"count": 0, "bytes": 0},
            # Directional tallies across all non-ping/non-garbage frames
            "tx": {"count": 0, "last": None, "intervals": []},
            "rx": {"count": 0, "last": None, "intervals": []},
        }
        # Variable counts by RX/TX for generic frames
        self._var_counts_rx: Dict[int, int] = {}
        self._var_counts_tx: Dict[int, int] = {}
        # Track last valid frame per direction for enhanced garbage context
        self._last_frame_rx: Optional[bytes] = None
        self._last_frame_tx: Optional[bytes] = None

    def _make_path(self, base_path: Optional[str]) -> str:
        """Choose a log file path in the HA config directory using a stable base name.

                - If base_path is provided, use its folder (treat as directory when it exists or ends with a separator);
                    otherwise use hass.config.path("") (HA config root).
        - Always name the file as helios_rs485_YYYYmmdd-HHMMSS.html
        """
        try:
            ts = time.strftime("%Y%m%d-%H%M%S")
            folder = None
            if base_path:
                # If caller passed a directory, use it; otherwise use the directory of the file
                is_dir = False
                try:
                    is_dir = os.path.isdir(base_path)
                except Exception:
                    is_dir = False
                if is_dir or base_path.endswith(os.sep) or base_path.endswith("/"):
                    folder = base_path.rstrip("/\\")
                else:
                    folder = os.path.dirname(base_path)
            if not folder:
                folder = self._default_base_folder()
            if folder:
                os.makedirs(folder, exist_ok=True)
            return os.path.join(folder or "", f"helios_rs485_{ts}.html")
        except Exception:
            return f"helios_rs485_{int(time.time())}.html"

    def _default_base_folder(self) -> str:
        # Try HA config directory
        try:
            path_fn = getattr(getattr(self._hass, "config", None), "path", None)
            if callable(path_fn):
                return str(path_fn(""))
        except Exception:
            pass
        # Fallback to CWD
        return os.getcwd()

    def _make_raw_path(self, html_path: str) -> str:
        try:
            root, ext = os.path.splitext(html_path)
            return f"{root}.raw.jsonl"
        except Exception:
            return f"helios_rs485_{int(time.time())}.raw.jsonl"

    def _make_raw_html_path(self, html_path: str) -> str:
        try:
            root, ext = os.path.splitext(html_path)
            return f"{root}.raw.html"
        except Exception:
            return f"helios_rs485_{int(time.time())}.raw.html"

    def start(self) -> str:
        if self._running:
            return self._path
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True, name="HeliosRs485Logger")
        self._thread.start()
        return self._path

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        try:
            self._q.put_nowait(("__STOP__", b""))
        except Exception:
            pass
        try:
            if self._thread:
                self._thread.join(timeout=2.0)
        except Exception:
            pass
        finally:
            self._thread = None

    # Public ingestion API
    def on_rx(self, chunk: bytes) -> None:
        if not self._running or not chunk:
            return
        try:
            self._q.put_nowait(("RX", bytes(chunk), self._ts()))
        except Exception:
            pass

    def on_tx(self, chunk: bytes) -> None:
        if not self._running or not chunk:
            return
        try:
            self._q.put_nowait(("TX", bytes(chunk), self._ts()))
        except Exception:
            pass

    # Worker thread
    def _worker(self) -> None:
        # Open the file in the worker thread to avoid blocking HA's event loop
        try:
            folder = os.path.dirname(self._path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            if not self._raw_only:
                self._file = open(self._path, "w", encoding="utf-8")
                # Raw JSONL file (for optional offline decode)
                self._raw_file = open(self._raw_path, "w", encoding="utf-8")
            else:
                # Raw-only mode: write a lightweight raw HTML file
                self._raw_html_file = open(self._raw_html_path, "w", encoding="utf-8")
            self._start_mono = time.monotonic()
            if not self._raw_only:
                self._write_html_header()
            else:
                self._write_raw_html_header()
        except Exception as exc:
            _LOGGER.warning("RS485 logger: worker failed to open file %s: %s", self._path, exc)
            # Continue running without file; lines will be dropped
            self._file = None
            try:
                if self._raw_file:
                    self._raw_file.close()
            except Exception:
                pass
            self._raw_file = None

        while self._running:
            try:
                try:
                    item = self._q.get(timeout=0.5)
                except queue.Empty:
                    continue
                # Back-compat: support 2-tuple and 3-tuple items
                if isinstance(item, tuple) and len(item) == 3:
                    tag, data, ts_in = item
                elif isinstance(item, tuple) and len(item) == 2:
                    tag, data = item
                    ts_in = None
                else:
                    # Unknown message shape; skip
                    continue
                if tag == "__STOP__":
                    break
                if tag == "RX":
                    self._rx_buf.extend(data)
                    self._drain(tag, self._rx_buf, ts_in)
                elif tag == "TX":
                    self._tx_buf.extend(data)
                    self._drain(tag, self._tx_buf, ts_in)
            except Exception as exc:
                _LOGGER.debug("RS485 logger worker error: %s", exc)
        # Graceful shutdown and close file in worker
        try:
            # Flush any residual partial bytes as tail garbage so nothing is dropped
            try:
                if self._rx_buf:
                    self._emit_garbage("RX", bytes(self._rx_buf), self._ts())
                    self._rx_buf.clear()
            except Exception:
                pass
            try:
                if self._tx_buf:
                    self._emit_garbage("TX", bytes(self._tx_buf), self._ts())
                    self._tx_buf.clear()
            except Exception:
                pass
            if not self._raw_only:
                self._write_html_footer()
            if (not self._raw_only) and self._file:
                try:
                    self._file.flush()
                except Exception:
                    pass
                try:
                    self._file.close()
                except Exception:
                    pass
            if self._raw_file:
                try:
                    self._raw_file.flush()
                except Exception:
                    pass
                try:
                    self._raw_file.close()
                except Exception:
                    pass
            if self._raw_html_file:
                try:
                    self._write_raw_html_footer()
                except Exception:
                    pass
                try:
                    self._raw_html_file.flush()
                except Exception:
                    pass
                try:
                    self._raw_html_file.close()
                except Exception:
                    pass
        finally:
            self._file = None
            self._raw_file = None
            self._raw_html_file = None

    def _drain(self, direction: str, buf: bytearray, ts_in: Optional[str] = None) -> None:
        # Parse greedily; log garbage chunks when skipping bytes
        used_ts = False
        while True:
            if len(buf) < 4:
                return
            # Try ping (4 bytes at head only)
            if self._try_ping(direction, buf, (ts_in if not used_ts else None)):
                used_ts = True if ts_in and not used_ts else used_ts
                continue
            # Find next broadcast and generic, pick the earliest valid one
            b_idx, b_total = self._find_broadcast(buf)
            g_idx, g_total = self._find_generic(buf)
            # Choose earliest positive index
            choices = [(b_idx, b_total, "broadcast"), (g_idx, g_total, "generic")]
            # Filter out not found
            choices = [c for c in choices if c[0] >= 0]
            if choices:
                idx, total, kind = min(choices, key=lambda t: t[0])
                if idx > 0:
                    self._emit_garbage(direction, buf[:idx], (ts_in if not used_ts else None))
                    used_ts = True if ts_in and not used_ts else used_ts
                    del buf[:idx]
                frame = bytes(buf[:total])
                del buf[:total]
                if kind == "broadcast":
                    self._emit_broadcast(direction, frame, (ts_in if not used_ts else None))
                else:
                    self._emit_generic(direction, frame, (ts_in if not used_ts else None))
                used_ts = True if ts_in and not used_ts else used_ts
                continue
            # No match; if buffer too big, flush some as garbage to avoid growth
            if len(buf) > 4096:
                self._emit_garbage(direction, buf[:64], (ts_in if not used_ts else None))
                used_ts = True if ts_in and not used_ts else used_ts
                del buf[:64]
            return

    # Frame finders
    def _find_broadcast(self, buf: bytearray) -> tuple[int, int]:
        for i in range(0, len(buf) - 4):
            if buf[i] == 0xFF and buf[i + 1] == 0xFF:
                if i + 4 > len(buf):
                    break
                plen = buf[i + 2]
                total = 3 + plen + 1
                if i + total > len(buf):
                    break
                frame = bytes(buf[i : i + total])
                if _checksum(frame[:-1]) == frame[-1]:
                    return i, total
        return -1, 0

    def _find_generic(self, buf: bytearray) -> tuple[int, int]:
        for i in range(0, len(buf) - 5):
            if i + 5 > len(buf):
                break
            plen = buf[i + 2]
            total = 3 + plen + 1
            if total < 5 or i + total > len(buf):
                continue
            frame = bytes(buf[i : i + total])
            if _checksum(frame[:-1]) == frame[-1]:
                return i, total
        return -1, 0

    # Emitters
    def _emit_garbage(self, direction: str, bytes_chunk: bytes, ts_override: Optional[str] = None) -> None:
        # Update stats
        self._stats["garbage"]["count"] += 1
        self._stats["garbage"]["bytes"] += len(bytes_chunk)
        # Create a combined hex stream: previous valid frame bytes (green) + garbage bytes (red)
        prev = self._last_frame_tx if direction == "TX" else self._last_frame_rx
        hex_prev = html.escape(prev.hex(" ")) if prev else ""
        hex_garbage = html.escape(bytes_chunk.hex(" "))
        combined_hex = ""
        if hex_prev:
            combined_hex += f"<span class=\"hex hex-prev\">{hex_prev}</span> "
        combined_hex += f"<span class=\"hex hex-garbage\">{hex_garbage}</span>"
        # Raw: record garbage (and last frame context for debugging)
        # Raw recording
        self._write_raw({
            "dir": direction,
            "kind": "garbage",
            "data": bytes_chunk.hex(),
            "prev": (prev.hex() if prev else None),
        }, ts_override)
        if self._raw_only:
            self._write_raw_html_row(
                category="garbage",
                direction=direction,
                summary=f"garbage ({len(bytes_chunk)} bytes)",
                data=bytes(),
                hex_html=combined_hex,
                var_label="",
                ts_override=ts_override,
            )
        else:
            self._write_row(
                category="garbage",
                direction=direction,
                summary=f"garbage ({len(bytes_chunk)} bytes)",
                data=bytes(),
                hex_html=combined_hex,
                var_label="",
                ts_override=ts_override,
            )

    def _try_ping(self, direction: str, buf: bytearray, ts_override: Optional[str] = None) -> bool:
        if len(buf) < 4:
            return False
        b0, b1, b2, b3 = buf[0], buf[1], buf[2], buf[3]
        if b1 == 0x00 and b2 == 0x00 and ((_checksum(bytes([b0, b1, b2])) & 0xFF) == b3):
            frame = bytes(buf[:4])
            del buf[:4]
            self._mark_event("ping")
            # Directional tally for all frames
            self._mark_event("tx" if direction == "TX" else "rx")
            # Raw
            self._write_raw({
                "dir": direction,
                "kind": "ping",
                "data": frame.hex(),
            }, ts_override)
            if self._raw_only:
                self._write_raw_html_row(
                    category="ping",
                    direction=direction,
                    summary="ping ok",
                    data=frame,
                    var_label="",
                    ts_override=ts_override,
                )
            else:
                self._write_row(
                    category="ping",
                    direction=direction,
                    summary="ping ok",
                    data=frame,
                    var_label="",
                    ts_override=ts_override,
                )
            return True
        return False

    def _emit_broadcast(self, direction: str, frame: bytes, ts_override: Optional[str] = None) -> None:
        # Layout: [0xFF, 0xFF, plen, payload..., chk]
        try:
            self._mark_event("broadcast")
            # Directional count
            self._mark_event("tx" if direction == "TX" else "rx")
            # Remember last frame for this direction
            if direction == "TX":
                self._last_frame_tx = frame
            else:
                self._last_frame_rx = frame
            # Raw
            self._write_raw({
                "dir": direction,
                "kind": "broadcast",
                "data": frame.hex(),
            }, ts_override)
            # Build enhanced hex with known/unknown highlights for payload bytes
            plen = frame[2]
            payload = frame[3:3+plen]
            # Known: payload[6] fan_level, payload[7] bit0 auto_mode, payload[10] bit0 filter_warning
            known_idx = {6: 'fan_level', 7: 'auto_mode(bit0)', 10: 'filter_warning(bit0)'}
            # Render hex segments
            def _seg(byte_val: int, idx: int) -> str:
                if idx in known_idx:
                    title = known_idx[idx]
                    return f'<span class="hex hex-known" title="{title}">{byte_val:02x}</span>'
                return f'<span class="hex hex-unknown" title="payload[{idx}]=0x{byte_val:02x}">{byte_val:02x}</span>'
            # Header and checksum normal hex
            head_hex = f"{frame[0]:02x} {frame[1]:02x} {frame[2]:02x}"
            pay_hex = " ".join(_seg(b, i) for i, b in enumerate(payload))
            tail_hex = f" {frame[-1]:02x}"
            hex_html = f"<span class=\"hex\">{head_hex} </span>{pay_hex}<span class=\"hex\">{tail_hex}</span>"
            # Summary suffix for known fields (compact)
            # Also include date/time and weekday from payload when available
            fan_level = payload[6] if len(payload) > 6 else None
            auto_bit = (payload[7] & 0x01) if len(payload) > 7 else None
            filter_bit = (payload[10] & 0x01) if len(payload) > 10 else None
            day = payload[0] if len(payload) > 0 else None
            weekday_idx = payload[1] if len(payload) > 1 else None
            month = payload[2] if len(payload) > 2 else None
            year_yy = payload[3] if len(payload) > 3 else None
            hour = payload[4] if len(payload) > 4 else None
            minute = payload[5] if len(payload) > 5 else None
            wd_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
            kv = []
            if fan_level is not None:
                kv.append(f"fan_level={fan_level}")
            if auto_bit is not None:
                kv.append(f"auto_mode={bool(auto_bit)}")
            if filter_bit is not None:
                kv.append(f"filter_warn={bool(filter_bit)}")
            if (day is not None) and (month is not None) and (year_yy is not None):
                yyyy = 2000 + (int(year_yy) % 100)
                kv.append(f"date={int(yyyy):04d}-{int(month):02d}-{int(day):02d}")
            if (hour is not None) and (minute is not None):
                kv.append(f"time={int(hour):02d}:{int(minute):02d}")
            if weekday_idx is not None:
                try:
                    wd_abbr = wd_names[int(weekday_idx) % 7]
                except Exception:
                    wd_abbr = str(weekday_idx)
                kv.append(f"wd={wd_abbr}({int(weekday_idx)})")
            suffix_txt = (" | " + ", ".join(kv)) if kv else ""
            if self._raw_only:
                self._write_raw_html_row(
                    category="broadcast",
                    direction=direction,
                    summary=f"broadcast ok, plen={frame[2]}{suffix_txt}",
                    data=frame,
                    hex_html=hex_html,
                    var_label="",
                    ts_override=ts_override,
                )
            else:
                self._write_row(
                    category="broadcast",
                    direction=direction,
                    summary=f"broadcast ok, plen={frame[2]}{suffix_txt}",
                    data=frame,
                    hex_html=hex_html,
                    var_label="",
                    ts_override=ts_override,
                )
        except Exception:
            self._mark_event("broadcast")
            if direction == "TX":
                self._last_frame_tx = frame
            else:
                self._last_frame_rx = frame
            # Raw
            self._write_raw({
                "dir": direction,
                "kind": "broadcast",
                "data": frame.hex(),
            }, ts_override)
            # Fallback simple row on errors
            if self._raw_only:
                self._write_raw_html_row(
                    category="broadcast",
                    direction=direction,
                    summary="broadcast ok",
                    data=frame,
                    var_label="",
                    ts_override=ts_override,
                )
            else:
                self._write_row(
                    category="broadcast",
                    direction=direction,
                    summary="broadcast ok",
                    data=frame,
                    var_label="",
                    ts_override=ts_override,
                )

    def _emit_generic(self, direction: str, frame: bytes, ts_override: Optional[str] = None) -> None:
        try:
            addr, cmd, plen = frame[0], frame[1], frame[2]
            var_idx = frame[3]
            payload = frame[4:-1]
            chk = frame[-1]
            var_name = None
            label = None
            values = None
            try:
                var = HeliosVar(var_idx)
                var_name = var.name
                if not self._raw_only:
                    values = _decode_sequence(payload, var)
                label = f"{var_name}"
            except Exception:
                label = None
            # Directional semantics and ACK detection
            is_reqresp = cmd in (0x00, 0x01)
            is_ack = (cmd == 0x05)
            # Render values compactly
            val_txt = ""
            if isinstance(values, list) and values:
                # Limit long payloads in log lines
                if len(values) <= 8:
                    val_txt = f" values={values}"
                else:
                    val_txt = f" values={values[:8]}…({len(values)})"
            # Compose
            suffix = ""
            if label:
                role_txt = ("TX" if direction == "TX" else "RX") if is_reqresp else "frame"
                suffix = f" | {role_txt}: ID 0x{var_idx:02X} ({label})"
            # Stats: ack vs known/unknown
            if is_ack:
                self._mark_event("ack")
                cat = "ack"
            else:
                if label is not None:
                    self._mark_event("known")
                    cat = "known"
                else:
                    self._mark_event("unknown")
                    cat = "unknown"
            # Directional overall
            self._mark_event("tx" if direction == "TX" else "rx")
            # Count variables per direction
            try:
                if direction == "TX":
                    self._var_counts_tx[var_idx] = self._var_counts_tx.get(var_idx, 0) + 1
                else:
                    self._var_counts_rx[var_idx] = self._var_counts_rx.get(var_idx, 0) + 1
            except Exception:
                pass
            # Remember last frame for this direction
            if direction == "TX":
                self._last_frame_tx = frame
            else:
                self._last_frame_rx = frame
            # Raw
            self._write_raw({
                "dir": direction,
                "kind": ("ack" if is_ack else "generic"),
                "data": frame.hex(),
                "var": var_idx,
            }, ts_override)
            if self._raw_only:
                summary = (
                    f"{'ack ok' if is_ack else 'frame ok'} addr=0x{addr:02X} cmd=0x{cmd:02X} var=0x{var_idx:02X} len={plen} chk=0x{chk:02X}"
                )
                self._write_raw_html_row(
                    category=cat,
                    direction=direction,
                    summary=summary,
                    data=frame,
                    var_label=(var_name or f"0x{var_idx:02X}"),
                    var_idx=var_idx,
                    ts_override=ts_override,
                )
            else:
                # Summary tag: TX ok for requests, RX ok for responses; ack ok for ACK frames
                if is_ack:
                    tag = "ack ok"
                elif is_reqresp:
                    tag = "TX ok" if direction == "TX" else "RX ok"
                else:
                    tag = "frame ok"
                summary = (
                    f"{tag} addr=0x{addr:02X} cmd=0x{cmd:02X} var=0x{var_idx:02X} len={plen} chk=0x{chk:02X}{val_txt}{suffix}"
                )
                self._write_row(
                    category=cat,
                    direction=direction,
                    summary=summary,
                    data=frame,
                    var_label=(var_name or f"0x{var_idx:02X}"),
                    var_idx=var_idx,
                    ts_override=ts_override,
                )
        except Exception as exc:
            self._mark_event("unknown")
            self._mark_event("tx" if direction == "TX" else "rx")
            if self._raw_only:
                self._write_raw_html_row(
                    category="unknown",
                    direction=direction,
                    summary=f"frame ok | parse_err={exc}",
                    data=frame,
                    var_label="",
                    ts_override=ts_override,
                )
            else:
                self._write_row(
                    category="unknown",
                    direction=direction,
                    summary=f"frame ok | parse_err={exc}",
                    data=frame,
                    var_label="",
                    ts_override=ts_override,
                )

    def _write_raw(self, obj: Dict[str, Any], ts_override: Optional[str] = None) -> None:
        try:
            if self._raw_only:
                return
            if not self._raw_file:
                return
            if ts_override:
                obj = {**obj, "ts": ts_override}
            else:
                obj = {**obj, "ts": self._ts()}
            self._raw_file.write(json.dumps(obj, separators=(",", ":")) + "\n")
            self._raw_file.flush()
        except Exception:
            # Swallow raw write errors silently to avoid perturbing runtime
            pass

    # Raw HTML helpers (used in raw_only mode)
    def _write_raw_html_header(self) -> None:
        if not self._raw_html_file:
            return
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            self._raw_html_file.write("""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Helios RS-485 Raw Log</title>
</head>
<body>
""")
            self._raw_html_file.write(f"  <h1>Helios RS-485 raw log</h1>\n  <div class=\"meta\">Started: {html.escape(started)} — File: {html.escape(os.path.basename(self._raw_html_path))}</div>\n")
            self._raw_html_file.write("  <table>\n    <thead>\n    <tr><th class=\"ts\">Time</th><th class=\"dir\">Dir</th><th class=\"kind\">Type</th><th class=\"var\">Var</th><th class=\"summary\">Summary</th><th class=\"hex\">Hex</th></tr>\n    </thead>\n    <tbody>\n")
            self._raw_html_file.flush()
        except Exception as exc:
            _LOGGER.debug("RS485 raw HTML header write failed: %s", exc)

    def _write_raw_html_row(self, category: str, direction: str, summary: str, data: bytes, hex_html: Optional[str] = None, var_label: str = "", var_idx: Optional[int] = None, ts_override: Optional[str] = None) -> None:
        if not self._raw_html_file:
            return
        ts = html.escape(ts_override or self._ts())
        dir_arrow = "→" if direction == "TX" else "←"
        dir_txt = html.escape(f"{dir_arrow} {direction}")
        kind = {
            "ping": "Ping",
            "broadcast": "Broadcast",
            "ack": "Ack",
            "known": "Known",
            "unknown": "Unknown",
            "garbage": "Garbage",
        }.get(category, category)
        kind_txt = html.escape(kind)
        if hex_html is not None:
            hex_cell = hex_html
        else:
            hex_cell = html.escape(data.hex(" "))
        row_cls = [f"cat-{category}"]
        if direction == "TX" and category in ("known", "unknown", "ack"):
            row_cls.append("dir-tx")
        cls = " ".join(row_cls)
        var_cell = html.escape(var_label or "")
        data_var_attr = ""
        if isinstance(var_idx, int):
            data_var_attr = f" data-var=\"0x{var_idx:02X}\" data-var-label=\"{html.escape(var_label or f'0x{var_idx:02X}') }\""
        row = f"<tr class=\"{cls}\"{data_var_attr}><td class=\"ts\">{ts}</td><td class=\"dir\">{dir_txt}</td><td class=\"kind\">{kind_txt}</td><td class=\"var\">{var_cell}</td><td class=\"summary\">{html.escape(summary)}</td><td class=\"hex\">{hex_cell}</td></tr>\n"
        try:
            self._raw_html_file.write(row)
            self._raw_html_file.flush()
        except Exception as exc:
            _LOGGER.debug("RS485 raw HTML row write failed: %s", exc)

    def _write_raw_html_footer(self) -> None:
        if not self._raw_html_file:
            return
        stopped = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            self._raw_html_file.write("""
    </tbody>
  </table>
""")
            self._raw_html_file.write(f"  <div class=\"meta\">Stopped: {html.escape(stopped)}</div>\n</body>\n</html>\n")
            self._raw_html_file.flush()
        except Exception as exc:
            _LOGGER.debug("RS485 raw HTML footer write failed: %s", exc)

    # Utilities
    def _write_line(self, line: str) -> None:
        # Back-compat utility; not used in HTML mode but kept if needed
        try:
            if self._file:
                self._file.write(line + "\n")
                self._file.flush()
        except Exception as exc:
            _LOGGER.debug("RS485 logger write failed: %s", exc)

    def _ts(self) -> str:
        # UTC-ish human timestamp for portability
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) + ".%03dZ" % int((time.time() % 1) * 1000)

    # HTML helpers
    def _write_html_header(self) -> None:
        if not self._file:
            return
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        css = (
            "body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;background:#111;color:#ddd;margin:0;padding:0;}"
            "h1{font-size:18px;margin:12px 16px;} .meta{margin:0 16px 8px 16px;color:#aaa;}"
            "table{width:100%;border-collapse:collapse;font-size:13px;} thead th{position:sticky;top:0;background:#1a1a1a;color:#bbb;text-align:left;border-bottom:1px solid #333;padding:6px 8px;}"
            "tbody tr{border-bottom:1px solid #222;} td{padding:6px 8px;vertical-align:top;} .ts{white-space:nowrap;color:darkmagenta;padding-right:24px;} .dir{width:54px;color:#bbb;} .kind{width:90px;font-weight:600;} .var{width:130px;color:#bbb;white-space:nowrap;} .hex{font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;white-space:pre;color:#ddd;} .summary{color:#ddd;}"
            ".cat-ping{background:#2b2b2b;} .cat-broadcast{background:#103410;} .cat-ack{background:#2b2e3a;} .cat-known{background:#0e2f0e;} .cat-unknown{background:#401515;} .cat-garbage{background:#2b1f1f;}"
            ".cat-broadcast .summary,.cat-known .summary{color:#cfeecf;} .cat-unknown .summary,.cat-garbage .summary{color:#ffd0d0;} .cat-ping .summary{color:#ccc;} .cat-ack .summary{color:#cfe9ff;}"
            ".dir-tx.cat-known td,.dir-tx.cat-unknown td{background:#0b1e3a;} .dir-tx .summary,.dir-tx .hex,.dir-tx .kind,.dir-tx .dir{color:#cfe9ff;}"
            ".hex-prev{color:#8fd88f;} .hex-garbage{color:#ffd0d0;} .hex-known{color:#8fd88f;font-weight:600;} .hex-unknown{color:#cccccc;} .tag{display:inline-block;min-width:120px;margin-right:8px;} .summary-rest{display:inline-block;}"
        )
        # Lightweight JS to toggle categories and individual variables; persists state in localStorage
        js = (
            "(function(){\n"
            "  function qs(s,root){return (root||document).querySelector(s);}\n"
            "  function qsa(s,root){return Array.from((root||document).querySelectorAll(s));}\n"
            "  function load(key,def){try{return JSON.parse(localStorage.getItem(key))}catch(e){}return def;}\n"
            "  function save(key,val){try{localStorage.setItem(key,JSON.stringify(val))}catch(e){}}\n"
            "  function currentVarVisibility(){\n"
            "    var map = {};\n"
            "    qsa('#var-filters input[type=checkbox]').forEach(function(cb){ map[cb.getAttribute('data-var')] = !!cb.checked; });\n"
            "    return map;\n"
            "  }\n"
            "  function apply(){\n"
            "    var showPing = qs('#filter-ping').checked;\n"
            "    var showBcast = qs('#filter-broadcast').checked;\n"
            "    var showKnown = qs('#filter-known').checked;\n"
            "    var showAck = qs('#filter-ack').checked;\n"
            "    var showUnknown = qs('#filter-unknown').checked;\n"
            "    var varMap = currentVarVisibility();\n"
            "    qsa('tbody tr').forEach(function(tr){\n"
            "      var isPing = tr.classList.contains('cat-ping');\n"
            "      var isBcast = tr.classList.contains('cat-broadcast');\n"
            "      var isAck = tr.classList.contains('cat-ack');\n"
            "      var isKnown = tr.classList.contains('cat-known');\n"
            "      var isUnknown = tr.classList.contains('cat-unknown');\n"
            "      var catOk = (isPing?showPing:(isBcast?showBcast:(isAck?showAck:(isKnown?showKnown:(isUnknown?showUnknown:true)))));\n"
            "      var v = tr.getAttribute('data-var');\n"
            "      var varOk = (v? (varMap[v]!==false): true);\n"
            "      tr.style.display = (catOk && varOk)? '':'none';\n"
            "    });\n"
            "    save('helios_rs485_showPing', showPing);\n"
            "    save('helios_rs485_showBcast', showBcast);\n"
            "    save('helios_rs485_showKnown', showKnown);\n"
            "    save('helios_rs485_showAck', showAck);\n"
            "    save('helios_rs485_showUnknown', showUnknown);\n"
            "    // Persist per-var states\n"
            "    qsa('#var-filters input[type=checkbox]').forEach(function(cb){ save('helios_rs485_var_'+cb.getAttribute('data-var'), !!cb.checked); });\n"
            "  }\n"
            "  function buildVarFilters(){\n"
            "    var cont = qs('#var-filters'); if(!cont) return;\n"
            "    var seen = {}; var items = [];\n"
            "    qsa('tbody tr[data-var]').forEach(function(tr){\n"
            "      var code = tr.getAttribute('data-var'); if(!code || seen[code]) return;\n"
            "      seen[code]=true;\n"
            "      var labelCell = tr.querySelector('td.var');\n"
            "      var text = labelCell? labelCell.textContent.trim(): code;\n"
            "      items.push({code:code, text:text});\n"
            "    });\n"
            "    items.sort(function(a,b){ return a.code.localeCompare(b.code); });\n"
            "    // Render checkboxes\n"
            "    cont.innerHTML = '';\n"
            "    items.forEach(function(it){\n"
            "      var key = 'helios_rs485_var_'+it.code;\n"
            "      var show = load(key, true) !== false;\n"
            "      var id = 'filter-var-'+it.code;\n"
            "      var lbl = document.createElement('label'); lbl.style.marginLeft = '8px';\n"
            "      var cb = document.createElement('input'); cb.type='checkbox'; cb.id=id; cb.setAttribute('data-var', it.code); cb.checked = show; cb.addEventListener('change', apply);\n"
            "      lbl.appendChild(cb); lbl.appendChild(document.createTextNode(' '+it.text));\n"
            "      cont.appendChild(lbl);\n"
            "    });\n"
            "  }\n"
            "  function init(){\n"
            "    var sp = load('helios_rs485_showPing', true);\n"
            "    var sb = load('helios_rs485_showBcast', true);\n"
            "    var sk = load('helios_rs485_showKnown', true);\n"
            "    var sa = load('helios_rs485_showAck', true);\n"
            "    var su = load('helios_rs485_showUnknown', true);\n"
            "    var pingCb = qs('#filter-ping'); var bcastCb = qs('#filter-broadcast');\n"
            "    var knownCb = qs('#filter-known'); var ackCb = qs('#filter-ack'); var unknownCb = qs('#filter-unknown');\n"
            "    if(pingCb){pingCb.checked = sp; pingCb.addEventListener('change', apply);}\n"
            "    if(bcastCb){bcastCb.checked = sb; bcastCb.addEventListener('change', apply);}\n"
            "    if(knownCb){knownCb.checked = sk; knownCb.addEventListener('change', apply);}\n"
            "    if(ackCb){ackCb.checked = sa; ackCb.addEventListener('change', apply);}\n"
            "    if(unknownCb){unknownCb.checked = su; unknownCb.addEventListener('change', apply);}\n"
            "    buildVarFilters();\n"
            "    apply();\n"
            "  }\n"
            "  window.addEventListener('DOMContentLoaded', init);\n"
            "})();"
        )
        html_head = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Helios RS-485 Log</title>
    <style>{css}</style>
    <script>{js}</script>
</head>
<body>
  <h1>Helios RS-485 log</h1>
  <div class=\"meta\">Started: {html.escape(started)} — File: {html.escape(os.path.basename(self._path))}</div>
    <div class=\"meta\">
        <strong>Legend:</strong>
        <span style=\"display:inline-block;padding:2px 6px;background:#103410;color:#cfeecf;margin-left:8px;border-radius:3px;\">Broadcast</span>
    <span style=\"display:inline-block;padding:2px 6px;background:#0e2f0e;color:#cfeecf;margin-left:8px;border-radius:3px;\">Known</span>
    <span style=\"display:inline-block;padding:2px 6px;background:#2b2e3a;color:#cfe9ff;margin-left:8px;border-radius:3px;\">Ack</span>
        <span style=\"display:inline-block;padding:2px 6px;background:#401515;color:#ffd0d0;margin-left:8px;border-radius:3px;\">Unknown</span>
        <span style=\"display:inline-block;padding:2px 6px;background:#2b1f1f;color:#ffd0d0;margin-left:8px;border-radius:3px;\">Garbage</span>
        <span style=\"display:inline-block;padding:2px 6px;background:#2b2b2b;color:#ccc;margin-left:8px;border-radius:3px;\">Ping</span>
                <span style=\"display:inline-block;padding:2px 6px;background:#0b1e3a;color:#cfe9ff;margin-left:8px;border-radius:3px;\">TX</span>
        <span style=\"display:inline-block;padding:2px 6px;background:transparent;border:1px solid #444;color:#ddd;margin-left:8px;border-radius:3px;\"><span style=\"color:#8fd88f\">prev-frame</span> + <span style=\"color:#ffd0d0\">garbage</span></span>
        <span style=\"display:inline-block;margin-left:16px;\">Dir: ← RX, → TX</span>
                <span style=\"display:inline-block;margin-left:24px;\"><strong>Filter:</strong>
                    <label style=\"margin-left:8px;\"><input id=\"filter-ping\" type=\"checkbox\" checked> show Ping</label>
                    <label style=\"margin-left:8px;\"><input id=\"filter-broadcast\" type=\"checkbox\" checked> show Broadcast</label>
                    <label style=\"margin-left:8px;\"><input id=\"filter-known\" type=\"checkbox\" checked> show Known</label>
                    <label style=\"margin-left:8px;\"><input id=\"filter-ack\" type=\"checkbox\" checked> show Ack</label>
                    <label style=\"margin-left:8px;\"><input id=\"filter-unknown\" type=\"checkbox\" checked> show Unknown</label>
                </span>
                <div class=\"meta\" id=\"var-filters\" style=\"margin-left:16px; margin-top:8px;\"><strong>Variables:</strong></div>
    </div>
  <table>
    <thead>
    <tr><th class=\"ts\">Time</th><th class=\"dir\">Dir</th><th class=\"kind\">Type</th><th class=\"var\">Var</th><th class=\"summary\">Summary</th><th class=\"hex\">Hex</th></tr>
    </thead>
    <tbody>
"""
        try:
            self._file.write(html_head)
            self._file.flush()
        except Exception as exc:
            _LOGGER.debug("RS485 logger header write failed: %s", exc)

    def _write_row(self, category: str, direction: str, summary: str, data: bytes, hex_html: Optional[str] = None, var_label: str = "", var_idx: Optional[int] = None, ts_override: Optional[str] = None) -> None:
        if not self._file:
            return
        ts = html.escape(ts_override or self._ts())
        # Direction text with arrow
        dir_arrow = "→" if direction == "TX" else "←"
        dir_txt = html.escape(f"{dir_arrow} {direction}")
        kind = {
            "ping": "Ping",
            "broadcast": "Broadcast",
            "ack": "Ack",
            "known": "Known",
            "unknown": "Unknown",
            "garbage": "Garbage",
        }.get(category, category)
        kind_txt = html.escape(kind)
        # Tag spacing: ensure equal spacing after common tags like "ping ok", "broadcast ok", etc.
        tag_prefixes = ["ping ok", "broadcast ok", "TX ok", "RX ok", "ack ok", "frame ok"]
        tag_used = None
        for p in tag_prefixes:
            if summary.lower().startswith(p):
                tag_used = p
                break
        if tag_used:
            rest = summary[len(tag_used):].lstrip(", ")
            summary_html = f"<span class=\"tag\">{html.escape(tag_used)}</span><span class=\"summary-rest\">{html.escape(rest)}</span>"
        else:
            summary_html = html.escape(summary)

        if hex_html is not None:
            hex_cell = hex_html
        else:
            hex_cell = html.escape(data.hex(" "))
        # Add TX styling class for generic frames
        row_cls = [f"cat-{category}"]
        if direction == "TX" and category in ("known", "unknown"):
            row_cls.append("dir-tx")
        cls = " ".join(row_cls)
        var_cell = html.escape(var_label or "")
        # data-var: like 0x07, used for filtering; only present for generic frames
        data_var_attr = ""
        if isinstance(var_idx, int):
            data_var_attr = f" data-var=\"0x{var_idx:02X}\" data-var-label=\"{html.escape(var_label or f'0x{var_idx:02X}') }\""
        row = f"<tr class=\"{cls}\"{data_var_attr}><td class=\"ts\">{ts}</td><td class=\"dir\">{dir_txt}</td><td class=\"kind\">{kind_txt}</td><td class=\"var\">{var_cell}</td><td class=\"summary\">{summary_html}</td><td class=\"hex\">{hex_cell}</td></tr>\n"
        try:
            self._file.write(row)
            self._file.flush()
        except Exception as exc:
            _LOGGER.debug("RS485 logger row write failed: %s", exc)

    def _write_html_footer(self) -> None:
        if not self._file:
            return
        stopped = time.strftime("%Y-%m-%d %H:%M:%S")
        # Compute stats
        def fmt_intervals(ints: List[float]) -> str:
            if not ints:
                return "n/a"
            ms = [v * 1000.0 for v in ints]
            return f"min {min(ms):.1f} ms — avg {sum(ms)/len(ms):.1f} ms — max {max(ms):.1f} ms"

        # Snapshot current counters
        ping = self._stats.get("ping", {})
        bcast = self._stats.get("broadcast", {})
        ack = self._stats.get("ack", {})
        known = self._stats.get("known", {})
        unknown = self._stats.get("unknown", {})
        garbage = self._stats.get("garbage", {})
        tx_all = self._stats.get("tx", {})
        rx_all = self._stats.get("rx", {})

        # Build variable counts section
        try:
            all_vars = sorted(
                set(self._var_counts_rx.keys()) | set(self._var_counts_tx.keys()),
                key=lambda k: (-(self._var_counts_rx.get(k, 0) + self._var_counts_tx.get(k, 0)), k),
            )
        except Exception:
            all_vars = []
        var_lines: List[str] = []
        for vid in all_vars:
            rx = int(self._var_counts_rx.get(vid, 0))
            tx = int(self._var_counts_tx.get(vid, 0))
            total = rx + tx
            try:
                name = HeliosVar(vid).name
            except Exception:
                name = None
            label = f"0x{vid:02X}"
            if name:
                label += f" ({html.escape(name)})"
            var_lines.append(f"<li><code>{label}</code>: RX {rx}, TX {tx}, total {total}</li>")
        vars_html_list = "\n".join(var_lines) if var_lines else "<li>None observed</li>"

        # Compute span since start
        span_s = max(0.0, time.monotonic() - float(self._start_mono or time.monotonic()))
        span_h = int(span_s // 3600)
        span_m = int((span_s % 3600) // 60)
        span_sec = span_s % 60.0
        span_str = f"{span_h:02d}:{span_m:02d}:{span_sec:06.3f}"

        # Aligned stats in monospace block
        lines: List[str] = []
        lines.append(f"Trace span:          {span_str}")
        lines.append("")
        lines.append(f"Ping:           {int(ping.get('count', 0)):6d}    {fmt_intervals(ping.get('intervals', []))}")
        lines.append(f"Broadcast:      {int(bcast.get('count', 0)):6d}    {fmt_intervals(bcast.get('intervals', []))}")
        lines.append(f"Ack frames:     {int(ack.get('count', 0)):6d}    {fmt_intervals(ack.get('intervals', []))}")
        lines.append(f"Known frames:   {int(known.get('count', 0)):6d}    {fmt_intervals(known.get('intervals', []))}")
        lines.append(f"Unknown frames: {int(unknown.get('count', 0)):6d}    {fmt_intervals(unknown.get('intervals', []))}")
        lines.append(f"Garbage:        {int(garbage.get('count', 0)):6d}    bytes={int(garbage.get('bytes', 0))}")
        lines.append("")
        lines.append(f"All TX frames:  {int(tx_all.get('count', 0)):6d}    {fmt_intervals(tx_all.get('intervals', []))}")
        lines.append(f"All RX frames:  {int(rx_all.get('count', 0)):6d}    {fmt_intervals(rx_all.get('intervals', []))}")
        pre_stats = "\n".join(lines)

        stats_html = f"""
            </tbody>
          </table>
          <div class=\"meta\">Stopped: {html.escape(stopped)}</div>
          <div class=\"meta\">Summary:</div>
          <pre class=\"meta\" style=\"font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:12px; background:#1a1a1a; color:#ddd; padding:8px; border:1px solid #333; border-radius:4px; white-space:pre;\">{html.escape(pre_stats)}</pre>
          <div class=\"meta\">Variables seen (by frequency):</div>
          <ul class=\"meta\">\n    {vars_html_list}\n  </ul>\n</body>\n</html>\n"""
        try:
            self._file.write(stats_html)
            self._file.flush()
        except Exception as exc:
            _LOGGER.debug("RS485 logger footer write failed: %s", exc)

    def _mark_event(self, key: str) -> None:
        now = time.monotonic()
        st = self._stats.get(key)
        if st is None:
            return
        last = st.get("last")
        st["count"] = int(st.get("count", 0)) + 1
        if last is not None:
            try:
                st.setdefault("intervals", []).append(now - float(last))
            except Exception:
                pass
        st["last"] = now
