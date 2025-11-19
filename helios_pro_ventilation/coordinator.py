import logging, time, threading
from typing import Any, Dict, List
from collections import deque
from .const import HeliosVar, CLIENT_ID
from .parser import _checksum, calendar_pack_levels48_to24

_LOGGER = logging.getLogger(__name__)

def _checksum(data: bytes) -> int:
    return (sum(data) + 1) & 0xFF


class HeliosCoordinator:
    def __init__(self, hass):
        self.hass = hass
        self.data: Dict[str, Any] = {}
        self.entities: List[Any] = []
        self.last_ping_time: float = 0.0
        self.last_ping_addr: int | None = None
        self.send_slot_active: bool = False
        self.send_slot_expires: float = 0.0
        self.send_slot_event = threading.Event()
        # Optional callback used by the debug scanner to receive parsed var responses
        self.debug_var_callback = None  # type: ignore[assignment]
        # Addresses that are permitted to open a TX send slot when they emit a ping.
        # Default to our client address only (CLIENT_ID / 0x11).
        try:
            self.allowed_ping_addrs = {int(CLIENT_ID)}
        except Exception:
            self.allowed_ping_addrs = set()
        # Initialize icing protection flags to well-defined defaults
        self.icing_protection_enabled = False  # switch default state
        self.data["icing_protection_active"] = False  # binary sensor default state
        self._icing_start_time = None  # internal timer baseline for icing detection window

    def register_entity(self, entity):
        self.entities.append(entity)

    def mark_ping(self, addr: int | None = None):
        """Record a ping from addr and open a send slot if addr is allowed.

        If addr is None, treat as unknown and allow by default (backward compatibility).
        """
        now = time.time()
        self.last_ping_time = now
        self.last_ping_addr = int(addr) if addr is not None else None
        allow = True if addr is None else (int(addr) in getattr(self, 'allowed_ping_addrs', {0x10}))
        if not allow:
            try:
                _LOGGER.debug("Ping seen from addr 0x%02X but not allowed for send slot", int(addr or 0))
            except Exception:
                _LOGGER.debug("Ping seen from disallowed addr (None)")
            return
        self.send_slot_active = True
        self.send_slot_expires = now + 0.08
        self.send_slot_event.set()
        # Note: on-ping opportunistic date/time probing disabled by user request

    def tick(self):
        if self.send_slot_active and time.time() > self.send_slot_expires:
            self.send_slot_active = False
            self.send_slot_event.clear()

    def update_values(self, new_values: Dict[str, Any]):
        changed = False
        icing_check_time = None
        icing_threshold = None
        # Get current frostschutz temperature from state if available
        try:
            icing_threshold = float(self.hass.states.get("sensor.helios_ec_pro_frostschutz_temperatur").state)
        except Exception:
            icing_threshold = 4.0
        # Track icing protection logic
        if getattr(self, "icing_protection_enabled", False):
            temp_outdoor = new_values.get("temp_outdoor", self.data.get("temp_outdoor"))
            fan_level = new_values.get("fan_level", self.data.get("fan_level"))
            now = time.time()
            if temp_outdoor is not None:
                if temp_outdoor < icing_threshold:
                    if not hasattr(self, "_icing_start_time") or self._icing_start_time is None:
                        self._icing_start_time = now
                    elif now - self._icing_start_time > 600:
                        # 10 minutes below threshold
                        if fan_level != 0 and hasattr(self, "set_fan_level"):
                            self.set_fan_level(0)
                        self.data["icing_protection_active"] = True
                else:
                    self._icing_start_time = None
                    self.data["icing_protection_active"] = False
            # Reset icing protection if fan level is set again
            if fan_level != 0 and self.data.get("icing_protection_active"):
                self.data["icing_protection_active"] = False
        for k, v in new_values.items():
            if k.startswith("_"):
                continue
            if self.data.get(k) != v:
                self.data[k] = v
                changed = True
        if changed:
            _LOGGER.debug("Coordinator updating entities with %s", new_values)
            self.hass.loop.call_soon_threadsafe(self._notify_entities)

    def _notify_entities(self):
        for e in list(self.entities):
            try:
                e.async_write_ha_state()
            except Exception as exc:
                _LOGGER.debug("Entity update failed: %s", exc)


class HeliosCoordinatorWithQueue(HeliosCoordinator):
    def __init__(self, hass):
        super().__init__(hass)
        self.tx_queue = deque()
        # Per-variable last-queued timestamps for read throttling
        self._last_read_ts: Dict[int, float] = {}
        # Last time we opportunistically probed date/time on ping
        self._last_dt_probe_ts: float = 0.0

    # ---------- TX QUEUE ----------
    def queue_frame(self, frame: bytes):
        # Throttle read requests for certain variables to avoid hammering the bus
        try:
            if isinstance(frame, (bytes, bytearray)) and len(frame) >= 5:
                addr, cmd, plen, var_idx = frame[0], frame[1], frame[2], frame[3]
                if cmd == 0x00:  # read
                    now = time.time()
                    min_interval = 0.0
                    if var_idx == int(HeliosVar.Var_3A_sensors_temp):
                        # Target ~30s cadence; allow if older than 25s
                        min_interval = 25.0
                    elif var_idx in (int(HeliosVar.Var_07_date_month_year), int(HeliosVar.Var_08_time_hour_min)):
                        # Avoid spamming date/time reads — at most every 5 seconds implicitly
                        min_interval = 5.0
                    if min_interval > 0.0:
                        last = float(self._last_read_ts.get(var_idx, 0.0))
                        if now - last < min_interval:
                            _LOGGER.debug("Throttle read var 0x%02X (%.1fs < %.1fs)", var_idx, now - last, min_interval)
                            return
                        self._last_read_ts[var_idx] = now
        except Exception:
            # Never block if throttling logic fails
            pass

        self.tx_queue.append(frame)
        _LOGGER.debug("Queued frame: %s", frame.hex(" "))

    # ---------- WRITE FRAME BUILDERS ----------
    def _build_fan_frame(self, data1: int, data2: int) -> bytes:
        """Build Helios write frame for fan control.

        Developer note (write variable + AA/BB semantics):
        - Although `HeliosVar.Var_35_fan_level` is documented as read-only in
          the community mapping, real devices accept write frames at this
          index with special semantics.
        - Frame format (bytes):
            [CLIENT_ID, 0x01, 0x03, 0x35, data1, data2, chk]
            where chk = (sum(all previous bytes) + 1) & 0xFF
        - Semantics used here:
            • Enable/disable AUTO mode: data1 = 0xAA, data2 = 0x01 (on) / 0x00 (off)
            • Manual fan level:        data1 = 0..4, data2 = 0xBB

        Do not change the variable index (0x35) or the AA/BB markers unless
        you also update the device-side expectations; other indices are not
        known to accept writes for these actions.
        """
        payload = bytes([
            CLIENT_ID,            # our address
            0x01,                 # write command
            0x03,                 # payload length (Var + 2 bytes)
            HeliosVar.Var_35_fan_level,
            data1,
            data2,
        ])
        chk = _checksum(payload)
        return payload + bytes([chk])

    def _build_write_var1(self, var: HeliosVar, value: int) -> bytes:
        """Build generic write frame with 1 data byte (Var + 1 byte)."""
        return self._build_write_var(var, [value & 0xFF])

    def _build_write_var(self, var: HeliosVar, data_bytes: list[int]) -> bytes:
        """Build generic write frame with N data bytes.

        Layout: [CLIENT_ID, 0x01, length, var, data..., chk] where length = 1 (Var) + len(data).
        """
        data = [max(0, min(255, int(b))) for b in (data_bytes or [])]
        length = 1 + len(data)
        payload = bytes([
            CLIENT_ID,
            0x01,  # write
            length & 0xFF,
            int(var),
            *data,
        ])
        chk = _checksum(payload)
        return payload + bytes([chk])

    def _build_read_request(self, var: HeliosVar) -> bytes:
        """Build read frame for a single variable."""
        frame = bytes([CLIENT_ID, 0x00, 0x01, int(var)])
        return frame + bytes([_checksum(frame)])

    def _build_calendar_write_extended(self, var: HeliosVar, levels48: list[int]) -> bytes:
        """Build extended calendar write with 52-byte payload (0x34):
        [0x11, 0x01, 0x34, var, 0x00, 0x00, 24 packed bytes, 25x 0x00 padding, chk]
        """
        packed24 = calendar_pack_levels48_to24(levels48)
        payload = bytearray()
        payload.extend([CLIENT_ID, 0x01, 0x34, int(var), 0x00, 0x00])
        payload.extend(packed24)
        # pad 25 zeros
        payload.extend([0x00] * 25)
        chk = _checksum(bytes(payload))
        payload.append(chk)
        return bytes(payload)

    # ---------- SERVICE HANDLERS ----------
    def set_auto_mode(self, enabled: bool):
        """Enable or disable AUTO mode."""
        frame = self._build_fan_frame(0xAA, 0x01 if enabled else 0x00)
        self.queue_frame(frame)
        _LOGGER.info(
            "HeliosPro: queued %s mode frame → %s",
            "AUTO" if enabled else "MANUAL",
            frame.hex(" "),
        )

    def set_fan_level(self, level: int):
        """Set manual fan level 0–4."""
        level = max(0, min(4, level))
        frame = self._build_fan_frame(level, 0xBB)
        self.queue_frame(frame)
        _LOGGER.info(
            "HeliosPro: queued manual fan level %d frame → %s",
            level,
            frame.hex(" "),
        )

    def set_party_enabled(self, enabled: bool):
        """Enable/disable Party mode via Var_0F (write-only). Optimistic update and confirm via Var_10 read."""
        try:
            frame = self._build_write_var1(HeliosVar.Var_0F_party_enabled, 0x01 if enabled else 0x00)
            self.queue_frame(frame)
            # Optimistic state update for immediate UI feedback
            self.update_values({"party_enabled": bool(enabled)})
            # Immediately request Var_10 (current time) to confirm state on next send slot
            read_v10 = self._build_read_request(HeliosVar.Var_10_party_curr_time)
            self.queue_frame(read_v10)
            _LOGGER.info(
                "HeliosPro: queued Party %s frame → %s",
                "ON" if enabled else "OFF",
                frame.hex(" "),
            )
        except Exception as exc:
            _LOGGER.warning("HeliosPro: set_party_enabled failed: %s", exc)

    # ---------- Calendar API ----------
    def request_calendar_day(self, day: int):
        """Queue a read for a calendar day (0=Mon..6=Sun)."""
        day = max(0, min(6, int(day)))
        var = HeliosVar(int(HeliosVar.Var_00_calendar_mon) + day)
        self.queue_frame(self._build_read_request(var))

    def set_calendar_day(self, day: int, levels48: list[int]):
        """Write a calendar day using extended format matching ESP32 implementation."""
        if len(levels48) != 48:
            raise ValueError("levels48 must have length 48")
        day = max(0, min(6, int(day)))
        var = HeliosVar(int(HeliosVar.Var_00_calendar_mon) + day)
        frame = self._build_calendar_write_extended(var, levels48)
        self.queue_frame(frame)
        _LOGGER.info("HeliosPro: queued calendar write for day %d → %s", day, frame.hex(" "))

    def copy_calendar_day(self, source_day: int, target_days: list[int]):
        """Copy the calendar from source_day to each day in target_days.

        - source_day: int 0=Mon..6=Sun
        - target_days: list[int] of days 0..6

        Reads levels from coordinator.data['calendar_day_{source_day}'].
        If missing, it will queue a read for the source and log a warning.
        """
        try:
            s = max(0, min(6, int(source_day)))
        except Exception:
            raise ValueError("source_day must be 0..6")
        if not isinstance(target_days, list) or not target_days:
            raise ValueError("target_days must be a non-empty list of 0..6")

        levels = self.data.get(f"calendar_day_{s}")
        if not isinstance(levels, list) or len(levels) != 48:
            _LOGGER.warning(
                "HeliosPro: calendar_day_%d not available (len=%s); queuing a read and aborting copy",
                s,
                (len(levels) if isinstance(levels, list) else None),
            )
            # Ensure we fetch it soon
            self.request_calendar_day(s)
            return

        # Normalize and unique target list
        ts: list[int] = []
        seen = set()
        for t in target_days:
            try:
                ti = max(0, min(6, int(t)))
            except Exception:
                continue
            if ti in seen:
                continue
            seen.add(ti)
            ts.append(ti)

        for t in ts:
            self.set_calendar_day(t, list(levels))
            # Optionally queue a read-back to refresh UI/state
            self.request_calendar_day(t)

    # ---------- Date/Time API ----------
    def set_device_date(self, year: int, month: int, day: int):
        """Set device date (Var_07) using year/month/day.

        Var_07 layout per enum note: [day, month, year_since_2000].
        """
        y = max(0, min(255, int(year) - 2000))
        m = max(1, min(12, int(month)))
        d = max(1, min(31, int(day)))
        frame = self._build_write_var(HeliosVar.Var_07_date_month_year, [d, m, y])
        self.queue_frame(frame)
        # read-back for confirmation on next slot
        self.queue_frame(self._build_read_request(HeliosVar.Var_07_date_month_year))
        _LOGGER.info("HeliosPro: queued device date set to %04d-%02d-%02d → %s", int(year), m, d, frame.hex(" "))

    def set_device_time(self, hour: int, minute: int):
        """Set device time (Var_08) to hour/minute (local).

        Note: Per updated spec, we do not issue any Var_08 read requests; confirmation
        will arrive alongside Var_07 responses when polled, or via subsequent Var_07 reads.
        """
        h = max(0, min(23, int(hour)))
        mi = max(0, min(59, int(minute)))
        frame = self._build_write_var(HeliosVar.Var_08_time_hour_min, [h, mi])
        self.queue_frame(frame)
        # Do not queue Var_08 read-back (unsupported); optionally rely on Var_07 reads elsewhere
        _LOGGER.info("HeliosPro: queued device time set to %02d:%02d → %s", h, mi, frame.hex(" "))

    def set_device_datetime(self, year: int, month: int, day: int, hour: int, minute: int):
        """Set both device date and time in a single send slot window if possible.

        Frames are queued as Var_07 then Var_08 and should be sent within a send slot.
        Per updated spec, we avoid any Var_08 read requests for confirmation.
        """
        # Queue date first, then time
        y = max(0, min(255, int(year) - 2000))
        m = max(1, min(12, int(month)))
        d = max(1, min(31, int(day)))
        h = max(0, min(23, int(hour)))
        mi = max(0, min(59, int(minute)))
        f_date = self._build_write_var(HeliosVar.Var_07_date_month_year, [d, m, y])
        f_time = self._build_write_var(HeliosVar.Var_08_time_hour_min, [h, mi])
        self.queue_frame(f_date)
        self.queue_frame(f_time)
        # read-back after writes (Var_07 only; Var_08 read not supported)
        self.queue_frame(self._build_read_request(HeliosVar.Var_07_date_month_year))
        _LOGGER.info(
            "HeliosPro: queued device datetime set to %04d-%02d-%02d %02d:%02d",
            int(year), m, d, h, mi,
        )
