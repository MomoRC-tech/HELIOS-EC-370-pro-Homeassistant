import threading
import time
import logging
from typing import Callable, Optional
import os
import tempfile

from .const import HeliosVar, CLIENT_ID
from .parser import _checksum

_LOGGER = logging.getLogger(__name__)


def _build_read_request(var: int) -> bytes:
    var_code = int(var)
    frame = bytes([CLIENT_ID, 0x00, 0x01, var_code])
    return frame + bytes([_checksum(frame)])


class HeliosDebugScanner:
    """One-shot scanner that requests all known variables and logs decoded values.

    Usage:
      scanner = HeliosDebugScanner(coord)
      scanner.trigger_scan()
    """

    def __init__(self, coordinator, on_complete: Optional[Callable[[], None]] = None, output_path: Optional[str] = None):
        self._coord = coordinator
        self._thread: Optional[threading.Thread] = None
        self._active = False
        self._on_complete = on_complete
        base_path = output_path or self._default_output_path()
        self._output_path = self._timestamped_path(base_path)
        # Aggregation for single-shot summary
        self._lock = threading.Lock()
        self._requested: list[int] = []
        self._responses: dict[int, dict] = {}

    def _default_output_path(self) -> str:
        # Prefer Home Assistant config directory if accessible
        try:
            hass = getattr(self._coord, "hass", None)
            config = getattr(hass, "config", None) if hass else None
            path_fn = getattr(config, "path", None) if config else None
            if callable(path_fn):
                return str(path_fn("helios_scan_summary.txt"))
        except Exception:
            pass
        # Fallback to temp dir
        try:
            return os.path.join(tempfile.gettempdir(), "helios_scan_summary.txt")
        except Exception:
            return "helios_scan_summary.txt"

    def _timestamped_path(self, path: str) -> str:
        ts = time.strftime("%Y%m%d-%H%M%S")
        # If path ends with a separator, treat it as a directory and append a default filename
        if path.endswith(os.sep) or path.endswith("/"):
            return os.path.join(path, f"helios_scan_summary_{ts}.txt")
        root, ext = os.path.splitext(path)
        if not ext:
            ext = ".txt"
        return f"{root}_{ts}{ext}"

    def _on_var(self, result: dict) -> None:
        var = result.get("var")
        values = result.get("values", [])
        ts = result.get("_frame_ts")
        # Render values with unit if scalar and unit known
        unit = getattr(var, "unit", None) if var is not None else None
        var_name = getattr(var, "name", str(var)) if var is not None else "<unknown>"
        # Aggregate for summary
        try:
            if var is not None:
                with self._lock:
                    self._responses[int(var)] = {
                        "var": var,
                        "values": list(values),
                        "_frame_ts": ts,
                    }
        except Exception:
            pass

        if not values:
            _LOGGER.debug("HeliosDebug: %s → (no values)", var_name)
            return
        if len(values) == 1:
            v = values[0]
            if unit:
                _LOGGER.debug("HeliosDebug: %s → %s %s", var_name, v, unit)
            else:
                _LOGGER.debug("HeliosDebug: %s → %s", var_name, v)
        else:
            # Shorten long arrays for log readability
            preview = values[:8]
            suffix = "…" if len(values) > 8 else ""
            if unit:
                _LOGGER.debug("HeliosDebug: %s → %s%s %s", var_name, preview, suffix, unit)
            else:
                _LOGGER.debug("HeliosDebug: %s → %s%s", var_name, preview, suffix)

    def _scan(self) -> None:
        try:
            self._active = True
            # Wire callback so listener forwards decoded results here
            prev_cb = getattr(self._coord, "debug_var_callback", None)
            self._coord.debug_var_callback = self._on_var
            try:
                self._requested = [int(v) for v in sorted(HeliosVar, key=int)]
                for var in sorted(HeliosVar, key=int):
                    try:
                        frame = _build_read_request(var)
                        if hasattr(self._coord, "queue_frame"):
                            self._coord.queue_frame(frame)
                    except Exception as exc:
                        _LOGGER.debug("HeliosDebug: failed to queue %s: %s", var.name, exc)
                    time.sleep(0.5)  # at least 500 ms between requests
            finally:
                # Restore previous callback (if any) and mark inactive
                self._coord.debug_var_callback = prev_cb
                # Brief grace period for final responses
                time.sleep(0.2)
                # Emit single-shot summary log
                try:
                    with self._lock:
                        requested = list(self._requested)
                        responses = dict(self._responses)
                    lines: list[str] = []
                    rows: list[tuple[int, str, str, str]] = []  # (code, name, rendered, note)
                    header = "HeliosDebug summary: single-shot scan completed ({} requested, {} responses)".format(
                        len(requested), len(responses)
                    )
                    lines.append(header)
                    lines.append("Var  Name                                      Response                                      Note")
                    lines.append("---  -----------------------------------------  ---------------------------------------------  ----------------------------------------------")
                    for code in requested:
                        try:
                            var = HeliosVar(code)
                            name = getattr(var, "name", f"0x{code:02X}")
                        except Exception:
                            var = None
                            name = f"0x{code:02X}"
                        resp = responses.get(code)
                        note = getattr(var, "note", None) if var is not None else None
                        if resp is None:
                            # Special case: synthesize known broadcast-backed values
                            if code == int(HeliosVar.Var_35_fan_level):
                                try:
                                    lvl = getattr(self._coord, "data", {}).get("fan_level")
                                    if lvl is not None:
                                        rendered = f"[{lvl}] {getattr(HeliosVar.Var_35_fan_level, 'unit', '')}".strip()
                                    else:
                                        rendered = "— no response —"
                                except Exception:
                                    rendered = "— no response —"
                            else:
                                rendered = "— no response —"
                        else:
                            vals = resp.get("values", [])
                            unit = getattr(var, "unit", None) if var is not None else None
                            if isinstance(vals, list):
                                # Render full list without shortening
                                rendered = str(vals)
                            else:
                                rendered = str(vals)
                            if unit:
                                rendered = f"{rendered} {unit}"
                        lines.append(f"0x{code:02X}  {name:<41}  {rendered:<45}  {note or ''}")
                        rows.append((code, name, rendered, note or ""))
                    summary = "\n".join(lines)
                    _LOGGER.info(summary)
                    # Always write to file (default path if not overridden)
                    try:
                        # Ensure parent directory exists
                        try:
                            parent = os.path.dirname(self._output_path)
                            if parent:
                                os.makedirs(parent, exist_ok=True)
                        except Exception:
                            pass
                        with open(self._output_path, "w", encoding="utf-8") as f:
                            f.write(summary)
                        _LOGGER.info("HeliosDebug summary written to %s", self._output_path)
                        # Markdown export alongside the text summary
                        root, _ext = os.path.splitext(self._output_path)
                        md_path = f"{root}.md"
                        ts_human = time.strftime("%Y-%m-%d %H:%M:%S")
                        md_lines: list[str] = []
                        md_lines.append("# Helios Debug Scan Summary")
                        md_lines.append("")
                        md_lines.append(f"- Requested: {len(requested)}")
                        md_lines.append(f"- Responses: {len(responses)}")
                        md_lines.append(f"- Generated: {ts_human}")
                        md_lines.append("")
                        md_lines.append("| Var | Name | Response | Note |")
                        md_lines.append("| --- | --- | --- | --- |")
                        for code, name, rendered, note in rows:
                            # Wrap response in backticks to preserve array formatting
                            md_lines.append(f"| 0x{code:02X} | {name} | `{rendered}` | {note} |")
                        with open(md_path, "w", encoding="utf-8") as mf:
                            mf.write("\n".join(md_lines) + "\n")
                        _LOGGER.info("HeliosDebug markdown summary written to %s", md_path)
                    except Exception as wexc:
                        _LOGGER.debug("HeliosDebug: failed to write summary file: %s", wexc)
                except Exception as exc:
                    _LOGGER.debug("HeliosDebug: failed to emit summary: %s", exc)
        finally:
            self._active = False
            # Fire completion callback if provided
            if callable(self._on_complete):
                try:
                    self._on_complete()
                except Exception:
                    pass

    def trigger_scan(self) -> None:
        if self._active:
            _LOGGER.info("HeliosDebug: scan already active; ignoring trigger")
            return
        self._thread = threading.Thread(target=self._scan, daemon=True, name="HeliosDebugScanner")
        self._thread.start()

    @property
    def is_active(self) -> bool:
        return self._active
