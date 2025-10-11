import threading
import time
import logging
from typing import Callable, Optional

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

    def __init__(self, coordinator, on_complete: Optional[Callable[[], None]] = None):
        self._coord = coordinator
        self._thread: Optional[threading.Thread] = None
        self._active = False
        self._on_complete = on_complete

    def _on_var(self, result: dict) -> None:
        var = result.get("var")
        values = result.get("values", [])
        ts = result.get("_frame_ts")
        # Render values with unit if scalar and unit known
        unit = getattr(var, "unit", None) if var is not None else None
        var_name = getattr(var, "name", str(var)) if var is not None else "<unknown>"
        if not values:
            _LOGGER.info("HeliosDebug: %s → (no values)", var_name)
            return
        if len(values) == 1:
            v = values[0]
            if unit:
                _LOGGER.info("HeliosDebug: %s → %s %s", var_name, v, unit)
            else:
                _LOGGER.info("HeliosDebug: %s → %s", var_name, v)
        else:
            # Shorten long arrays for log readability
            preview = values[:8]
            suffix = "…" if len(values) > 8 else ""
            if unit:
                _LOGGER.info("HeliosDebug: %s → %s%s %s", var_name, preview, suffix, unit)
            else:
                _LOGGER.info("HeliosDebug: %s → %s%s", var_name, preview, suffix)

    def _scan(self) -> None:
        try:
            self._active = True
            # Wire callback so listener forwards decoded results here
            prev_cb = getattr(self._coord, "debug_var_callback", None)
            self._coord.debug_var_callback = self._on_var
            try:
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
