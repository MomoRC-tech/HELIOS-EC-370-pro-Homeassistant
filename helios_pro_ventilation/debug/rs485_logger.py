from __future__ import annotations

import os
import time
import threading
import queue
import logging
import html
from typing import Optional, Dict, Any, List

from ..const import HeliosVar, CLIENT_ID
from ..parser import _checksum, _decode_sequence

_LOGGER = logging.getLogger(__name__)


class Rs485Logger:
    """Non-intrusive RS-485 stream logger.

    Feed it RX/TX byte chunks; it reconstructs frames and writes line-based logs.
    - Thread-safe, minimal overhead on ingest (queues and returns immediately).
    - Worker thread parses and writes to disk.
    """

    def __init__(self, hass, base_path: Optional[str] = None):
        self._hass = hass
        self._running = False
        self._rx_buf = bytearray()
        self._tx_buf = bytearray()
        self._q: queue.Queue[tuple[str, bytes]] = queue.Queue(maxsize=1000)
        self._thread: Optional[threading.Thread] = None
        self._file = None
        self._path = self._make_path(base_path)
        # Stats and timing
        self._start_mono: float = 0.0
        self._stats: Dict[str, Dict[str, Any]] = {
            "ping": {"count": 0, "last": None, "intervals": []},
            "broadcast": {"count": 0, "last": None, "intervals": []},
            "known": {"count": 0, "last": None, "intervals": []},
            "unknown": {"count": 0, "last": None, "intervals": []},
            "garbage": {"count": 0, "bytes": 0},
        }
        # Track last valid frame per direction for enhanced garbage context
        self._last_frame_rx: Optional[bytes] = None
        self._last_frame_tx: Optional[bytes] = None

    def _make_path(self, base_path: Optional[str]) -> str:
        """Choose a log file path in the HA config directory using a stable base name.

        - If base_path is provided, use its folder; otherwise use hass.config.path("") (HA config root).
        - Always name the file as helios_rs485_YYYYmmdd-HHMMSS.html
        """
        try:
            ts = time.strftime("%Y%m%d-%H%M%S")
            folder = None
            if base_path:
                # If caller passed a directory, use it; otherwise use the directory of the file
                if base_path.endswith(os.sep) or base_path.endswith("/"):
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
            self._q.put_nowait(("RX", bytes(chunk)))
        except Exception:
            pass

    def on_tx(self, chunk: bytes) -> None:
        if not self._running or not chunk:
            return
        try:
            self._q.put_nowait(("TX", bytes(chunk)))
        except Exception:
            pass

    # Worker thread
    def _worker(self) -> None:
        # Open the file in the worker thread to avoid blocking HA's event loop
        try:
            folder = os.path.dirname(self._path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            self._file = open(self._path, "w", encoding="utf-8")
            self._start_mono = time.monotonic()
            self._write_html_header()
        except Exception as exc:
            _LOGGER.warning("RS485 logger: worker failed to open file %s: %s", self._path, exc)
            # Continue running without file; lines will be dropped
            self._file = None

        while self._running:
            try:
                try:
                    tag, data = self._q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if tag == "__STOP__":
                    break
                if tag == "RX":
                    self._rx_buf.extend(data)
                    self._drain(tag, self._rx_buf)
                elif tag == "TX":
                    self._tx_buf.extend(data)
                    self._drain(tag, self._tx_buf)
            except Exception as exc:
                _LOGGER.debug("RS485 logger worker error: %s", exc)
        # Graceful shutdown and close file in worker
        try:
            self._write_html_footer()
            if self._file:
                try:
                    self._file.flush()
                except Exception:
                    pass
                try:
                    self._file.close()
                except Exception:
                    pass
        finally:
            self._file = None

    def _drain(self, direction: str, buf: bytearray) -> None:
        # Parse greedily; log garbage chunks when skipping bytes
        while True:
            if len(buf) < 4:
                return
            # Try ping (4 bytes)
            if self._try_ping(direction, buf):
                continue
            # Try broadcast (0xFF 0xFF)
            idx, total = self._find_broadcast(buf)
            if idx >= 0:
                if idx > 0:
                    self._emit_garbage(direction, buf[:idx])
                    del buf[:idx]
                frame = bytes(buf[:total])
                del buf[:total]
                self._emit_broadcast(direction, frame)
                continue
            # Try generic (CLIENT_ID address or any addr)
            idx, total = self._find_generic(buf)
            if idx >= 0:
                if idx > 0:
                    self._emit_garbage(direction, buf[:idx])
                    del buf[:idx]
                frame = bytes(buf[:total])
                del buf[:total]
                self._emit_generic(direction, frame)
                continue
            # No match; if buffer too big, flush some as garbage to avoid growth
            if len(buf) > 4096:
                self._emit_garbage(direction, buf[:64])
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
    def _emit_garbage(self, direction: str, bytes_chunk: bytes) -> None:
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
        self._write_row(
            category="garbage",
            direction=direction,
            summary=f"garbage ({len(bytes_chunk)} bytes)",
            data=bytes(),
            hex_html=combined_hex,
        )

    def _try_ping(self, direction: str, buf: bytearray) -> bool:
        if len(buf) < 4:
            return False
        b0, b1, b2, b3 = buf[0], buf[1], buf[2], buf[3]
        if b1 == 0x00 and b2 == 0x00 and ((_checksum(bytes([b0, b1, b2])) & 0xFF) == b3):
            frame = bytes(buf[:4])
            del buf[:4]
            self._mark_event("ping")
            self._write_row(
                category="ping",
                direction=direction,
                summary="ping ok",
                data=frame,
            )
            return True
        return False

    def _emit_broadcast(self, direction: str, frame: bytes) -> None:
        # Layout: [0xFF, 0xFF, plen, payload..., chk]
        try:
            self._mark_event("broadcast")
            # Remember last frame for this direction
            if direction == "TX":
                self._last_frame_tx = frame
            else:
                self._last_frame_rx = frame
            self._write_row(
                category="broadcast",
                direction=direction,
                summary=f"broadcast ok, plen={frame[2]}",
                data=frame,
            )
        except Exception:
            self._mark_event("broadcast")
            if direction == "TX":
                self._last_frame_tx = frame
            else:
                self._last_frame_rx = frame
            self._write_row(
                category="broadcast",
                direction=direction,
                summary="broadcast ok",
                data=frame,
            )

    def _emit_generic(self, direction: str, frame: bytes) -> None:
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
                values = _decode_sequence(payload, var)
                label = f"{var_name}"
            except Exception:
                label = None
            # Directional semantics (best effort)
            role = "frame"
            if direction == "TX":
                role = "request" if cmd in (0x00, 0x01) else "frame"
            elif direction == "RX":
                role = "response" if cmd in (0x00, 0x01) else "frame"
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
                suffix = f" | {role}: ID 0x{var_idx:02X} ({label})"
            # Stats: known vs unknown
            if label is not None:
                self._mark_event("known")
                cat = "known"
            else:
                self._mark_event("unknown")
                cat = "unknown"
            # Remember last frame for this direction
            if direction == "TX":
                self._last_frame_tx = frame
            else:
                self._last_frame_rx = frame
            summary = (
                f"{role} ok addr=0x{addr:02X} cmd=0x{cmd:02X} var=0x{var_idx:02X} len={plen} chk=0x{chk:02X}{val_txt}{suffix}"
            )
            self._write_row(
                category=cat,
                direction=direction,
                summary=summary,
                data=frame,
            )
        except Exception as exc:
            self._mark_event("unknown")
            self._write_row(
                category="unknown",
                direction=direction,
                summary=f"frame ok | parse_err={exc}",
                data=frame,
            )

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
            "body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;background:#111;color:#ddd;margin:0;padding:0;}" \
            "h1{font-size:18px;margin:12px 16px;} .meta{margin:0 16px 8px 16px;color:#aaa;}" \
            "table{width:100%;border-collapse:collapse;font-size:13px;} thead th{position:sticky;top:0;background:#1a1a1a;color:#bbb;text-align:left;border-bottom:1px solid #333;padding:6px 8px;}" \
            "tbody tr{border-bottom:1px solid #222;} td{padding:6px 8px;vertical-align:top;} .ts{white-space:nowrap;color:darkmagenta;padding-right:24px;} .dir{width:54px;color:#bbb;} .kind{width:90px;font-weight:600;} .hex{font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;white-space:pre;color:#ddd;} .summary{color:#ddd;}" \
            ".cat-ping{background:#2b2b2b;} .cat-broadcast{background:#103410;} .cat-known{background:#0e2f0e;} .cat-unknown{background:#401515;} .cat-garbage{background:#2b1f1f;}" \
            ".cat-broadcast .summary,.cat-known .summary{color:#cfeecf;} .cat-unknown .summary,.cat-garbage .summary{color:#ffd0d0;} .cat-ping .summary{color:#ccc;}" \
            ".dir-tx.cat-known td,.dir-tx.cat-unknown td{background:#0b1e3a;} .dir-tx .summary,.dir-tx .hex,.dir-tx .kind,.dir-tx .dir{color:#cfe9ff;}" \
            ".hex-prev{color:#8fd88f;} .hex-garbage{color:#ffd0d0;} .tag{display:inline-block;min-width:120px;margin-right:8px;} .summary-rest{display:inline-block;}"
        )
        html_head = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Helios RS-485 Log</title>
  <style>{css}</style>
</head>
<body>
  <h1>Helios RS-485 log</h1>
  <div class=\"meta\">Started: {html.escape(started)} — File: {html.escape(os.path.basename(self._path))}</div>
    <div class=\"meta\">
        <strong>Legend:</strong>
        <span style=\"display:inline-block;padding:2px 6px;background:#103410;color:#cfeecf;margin-left:8px;border-radius:3px;\">Broadcast</span>
        <span style=\"display:inline-block;padding:2px 6px;background:#0e2f0e;color:#cfeecf;margin-left:8px;border-radius:3px;\">Known</span>
        <span style=\"display:inline-block;padding:2px 6px;background:#401515;color:#ffd0d0;margin-left:8px;border-radius:3px;\">Unknown</span>
        <span style=\"display:inline-block;padding:2px 6px;background:#2b1f1f;color:#ffd0d0;margin-left:8px;border-radius:3px;\">Garbage</span>
        <span style=\"display:inline-block;padding:2px 6px;background:#2b2b2b;color:#ccc;margin-left:8px;border-radius:3px;\">Ping</span>
        <span style=\"display:inline-block;padding:2px 6px;background:#0b1e3a;color:#cfe9ff;margin-left:8px;border-radius:3px;\">TX</span>
        <span style=\"display:inline-block;padding:2px 6px;background:transparent;border:1px solid #444;color:#ddd;margin-left:8px;border-radius:3px;\"><span style=\"color:#8fd88f\">prev-frame</span> + <span style=\"color:#ffd0d0\">garbage</span></span>
        <span style=\"display:inline-block;margin-left:16px;\">Dir: ← RX, → TX</span>
    </div>
  <table>
    <thead>
      <tr><th class=\"ts\">Time</th><th class=\"dir\">Dir</th><th class=\"kind\">Type</th><th class=\"summary\">Summary</th><th class=\"hex\">Hex</th></tr>
    </thead>
    <tbody>
"""
        try:
            self._file.write(html_head)
            self._file.flush()
        except Exception as exc:
            _LOGGER.debug("RS485 logger header write failed: %s", exc)

    def _write_row(self, category: str, direction: str, summary: str, data: bytes, hex_html: Optional[str] = None) -> None:
        if not self._file:
            return
        ts = html.escape(self._ts())
        # Direction text with arrow
        dir_arrow = "→" if direction == "TX" else "←"
        dir_txt = html.escape(f"{dir_arrow} {direction}")
        kind = {
            "ping": "Ping",
            "broadcast": "Broadcast",
            "known": "Known",
            "unknown": "Unknown",
            "garbage": "Garbage",
        }.get(category, category)
        kind_txt = html.escape(kind)
        # Tag spacing: ensure equal spacing after common tags like "ping ok", "broadcast ok", etc.
        tag_prefixes = ["ping ok", "broadcast ok", "request ok", "response ok", "frame ok"]
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
        row = f"<tr class=\"{cls}\"><td class=\"ts\">{ts}</td><td class=\"dir\">{dir_txt}</td><td class=\"kind\">{kind_txt}</td><td class=\"summary\">{summary_html}</td><td class=\"hex\">{hex_cell}</td></tr>\n"
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

        ping = self._stats.get("ping", {})
        bcast = self._stats.get("broadcast", {})
        known = self._stats.get("known", {})
        unknown = self._stats.get("unknown", {})
        garbage = self._stats.get("garbage", {})

        stats_html = f"""
    </tbody>
  </table>
  <div class=\"meta\">Stopped: {html.escape(stopped)}</div>
  <div class=\"meta\">Summary:</div>
  <ul class=\"meta\">
    <li>Ping: {int(ping.get('count', 0))} events — {fmt_intervals(ping.get('intervals', []))}</li>
    <li>Broadcast: {int(bcast.get('count', 0))} events — {fmt_intervals(bcast.get('intervals', []))}</li>
    <li>Known frames: {int(known.get('count', 0))} events — {fmt_intervals(known.get('intervals', []))}</li>
    <li>Unknown frames: {int(unknown.get('count', 0))} events — {fmt_intervals(unknown.get('intervals', []))}</li>
    <li>Garbage: {int(garbage.get('count', 0))} chunks, {int(garbage.get('bytes', 0))} bytes</li>
  </ul>
</body>
</html>
"""
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
