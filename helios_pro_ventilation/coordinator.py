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
        self.debug_var_callback = None  # optional callback
        try:
            self.allowed_ping_addrs = {int(CLIENT_ID)}
        except Exception:
            self.allowed_ping_addrs = set()

        # Icing protection defaults
        self.icing_protection_enabled = True
        self.data["icing_protection_active"] = False
        self._icing_start_time = None
        # Rolling 24h activation timestamps (bounded for safety)
        self._icing_trigger_ts = deque(maxlen=500)
        self.data["icing_triggers_24h"] = 0

    def register_entity(self, entity):
        self.entities.append(entity)

    def mark_ping(self, addr: int | None = None):
        """Record a ping and open a send slot if allowed."""
        now = time.time()
        self.last_ping_time = now
        self.last_ping_addr = int(addr) if addr is not None else None
        allow = True if addr is None else (int(addr) in getattr(self, "allowed_ping_addrs", {0x10}))
        if not allow:
            try:
                _LOGGER.debug("Ping from disallowed addr 0x%02X", int(addr or 0))
            except Exception:
                _LOGGER.debug("Ping from disallowed addr (None)")
            return
        self.send_slot_active = True
        self.send_slot_expires = now + 0.08
        self.send_slot_event.set()

    def tick(self):
        if self.send_slot_active and time.time() > self.send_slot_expires:
            self.send_slot_active = False
            self.send_slot_event.clear()

    def update_values(self, new_values: Dict[str, Any]):
        changed = False
        # Determine icing threshold (fallback to 4.0°C)
        try:
            icing_threshold = float(self.hass.states.get("sensor.helios_ec_pro_frostschutz_temperatur").state)
        except Exception:
            icing_threshold = 4.0

        if self.icing_protection_enabled:
            temp_outdoor = new_values.get("temp_outdoor", self.data.get("temp_outdoor"))
            fan_level = new_values.get("fan_level", self.data.get("fan_level"))
            old_fan_level = self.data.get("fan_level")
            now = time.time()
            was_active = bool(self.data.get("icing_protection_active", False))

            if temp_outdoor is not None:
                if temp_outdoor < icing_threshold:
                    if self._icing_start_time is None:
                        self._icing_start_time = now
                    elif now - self._icing_start_time > 600:  # 10 minutes below threshold
                        if fan_level != 0 and hasattr(self, "set_fan_level"):
                            self.set_fan_level(0)
                        if not was_active:
                            self._icing_trigger_ts.append(now)
                        self.data["icing_protection_active"] = True
                else:
                    self._icing_start_time = None
                    self.data["icing_protection_active"] = False

            # Reset only if user overrides from 0 → non-zero while active
            if (
                fan_level is not None
                and fan_level != 0
                and old_fan_level == 0
                and self.data.get("icing_protection_active")
            ):
                self.data["icing_protection_active"] = False

            # Purge old triggers > 24h
            cutoff = now - 86400
            while self._icing_trigger_ts and self._icing_trigger_ts[0] < cutoff:
                self._icing_trigger_ts.popleft()
            self.data["icing_triggers_24h"] = len(self._icing_trigger_ts)

        # Apply new values and mark changes
        for k, v in new_values.items():
            if k.startswith("_"):
                continue
            if self.data.get(k) != v:
                self.data[k] = v
                changed = True

        if changed:
            _LOGGER.debug("Coordinator updating entities with %s", new_values)
            try:
                self.hass.loop.call_soon_threadsafe(self._notify_entities)
            except Exception:
                self._notify_entities()

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
        self._last_read_ts: Dict[int, float] = {}
        self._last_dt_probe_ts: float = 0.0

    def queue_frame(self, frame: bytes):
        try:
            if isinstance(frame, (bytes, bytearray)) and len(frame) >= 5:
                addr, cmd, plen, var_idx = frame[0], frame[1], frame[2], frame[3]
                if cmd == 0x00:  # read
                    now = time.time()
                    min_interval = 0.0
                    if var_idx == int(HeliosVar.Var_3A_sensors_temp):
                        min_interval = 25.0
                    elif var_idx in (int(HeliosVar.Var_07_date_month_year), int(HeliosVar.Var_08_time_hour_min)):
                        min_interval = 5.0
                    if min_interval > 0.0:
                        last = float(self._last_read_ts.get(var_idx, 0.0))
                        if now - last < min_interval:
                            _LOGGER.debug(
                                "Throttle read var 0x%02X (%.1fs < %.1fs)",
                                var_idx,
                                now - last,
                                min_interval,
                            )
                            return
                        self._last_read_ts[var_idx] = now
        except Exception:
            pass

        self.tx_queue.append(frame)
        _LOGGER.debug("Queued frame: %s", frame.hex(" "))

    def _build_fan_frame(self, data1: int, data2: int) -> bytes:
        payload = bytes([
            CLIENT_ID,
            0x01,
            0x03,
            HeliosVar.Var_35_fan_level,
            data1,
            data2,
        ])
        chk = _checksum(payload)
        return payload + bytes([chk])

    def _build_write_var1(self, var: HeliosVar, value: int) -> bytes:
        return self._build_write_var(var, [value & 0xFF])

    def _build_write_var(self, var: HeliosVar, data_bytes: list[int]) -> bytes:
        data = [max(0, min(255, int(b))) for b in (data_bytes or [])]
        length = 1 + len(data)
        payload = bytes([
            CLIENT_ID,
            0x01,
            length & 0xFF,
            int(var),
            *data,
        ])
        chk = _checksum(payload)
        return payload + bytes([chk])

    def _build_read_request(self, var: HeliosVar) -> bytes:
        frame = bytes([CLIENT_ID, 0x00, 0x01, int(var)])
        return frame + bytes([_checksum(frame)])

    def _build_calendar_write_extended(self, var: HeliosVar, levels48: list[int]) -> bytes:
        packed24 = calendar_pack_levels48_to24(levels48)
        payload = bytearray()
        payload.extend([CLIENT_ID, 0x01, 0x34, int(var), 0x00, 0x00])
        payload.extend(packed24)
        payload.extend([0x00] * 25)
        chk = _checksum(bytes(payload))
        payload.append(chk)
        return bytes(payload)

    def set_auto_mode(self, enabled: bool):
        frame = self._build_fan_frame(0xAA, 0x01 if enabled else 0x00)
        self.queue_frame(frame)
        _LOGGER.info(
            "HeliosPro: queued %s mode frame → %s",
            "AUTO" if enabled else "MANUAL",
            frame.hex(" "),
        )

    def set_fan_level(self, level: int):
        level = max(0, min(4, level))
        frame = self._build_fan_frame(level, 0xBB)
        self.queue_frame(frame)
        _LOGGER.info(
            "HeliosPro: queued manual fan level %d frame → %s",
            level,
            frame.hex(" "),
        )

    def set_party_enabled(self, enabled: bool):
        try:
            frame = self._build_write_var1(HeliosVar.Var_0F_party_enabled, 0x01 if enabled else 0x00)
            self.queue_frame(frame)
            self.update_values({"party_enabled": bool(enabled)})
            read_v10 = self._build_read_request(HeliosVar.Var_10_party_curr_time)
            self.queue_frame(read_v10)
            _LOGGER.info(
                "HeliosPro: queued Party %s frame → %s",
                "ON" if enabled else "OFF",
                frame.hex(" "),
            )
        except Exception as exc:
            _LOGGER.warning("HeliosPro: set_party_enabled failed: %s", exc)

    def request_calendar_day(self, day: int):
        day = max(0, min(6, int(day)))
        var = HeliosVar(int(HeliosVar.Var_00_calendar_mon) + day)
        self.queue_frame(self._build_read_request(var))

    def set_calendar_day(self, day: int, levels48: list[int]):
        if len(levels48) != 48:
            raise ValueError("levels48 must have length 48")
        day = max(0, min(6, int(day)))
        var = HeliosVar(int(HeliosVar.Var_00_calendar_mon) + day)
        frame = self._build_calendar_write_extended(var, levels48)
        self.queue_frame(frame)
        _LOGGER.info("HeliosPro: queued calendar write for day %d → %s", day, frame.hex(" "))

    def copy_calendar_day(self, source_day: int, target_days: list[int]):
        try:
            s = max(0, min(6, int(source_day)))
        except Exception:
            raise ValueError("source_day must be 0..6")
        if not isinstance(target_days, list) or not target_days:
            raise ValueError("target_days must be a non-empty list of 0..6")
        levels = self.data.get(f"calendar_day_{s}")
        if not isinstance(levels, list) or len(levels) != 48:
            _LOGGER.warning(
                "HeliosPro: calendar_day_%d not available; queuing read and aborting copy",
                s,
            )
            self.request_calendar_day(s)
            return
        seen = set()
        targets: list[int] = []
        for t in target_days:
            try:
                ti = max(0, min(6, int(t)))
            except Exception:
                continue
            if ti in seen:
                continue
            seen.add(ti)
            targets.append(ti)
        for t in targets:
            self.set_calendar_day(t, list(levels))
            self.request_calendar_day(t)

    def set_device_date(self, year: int, month: int, day: int):
        y = max(0, min(255, int(year) - 2000))
        m = max(1, min(12, int(month)))
        d = max(1, min(31, int(day)))
        frame = self._build_write_var(HeliosVar.Var_07_date_month_year, [d, m, y])
        self.queue_frame(frame)
        self.queue_frame(self._build_read_request(HeliosVar.Var_07_date_month_year))
        _LOGGER.info("HeliosPro: queued device date %04d-%02d-%02d → %s", int(year), m, d, frame.hex(" "))

    def set_device_time(self, hour: int, minute: int):
        h = max(0, min(23, int(hour)))
        mi = max(0, min(59, int(minute)))
        frame = self._build_write_var(HeliosVar.Var_08_time_hour_min, [h, mi])
        self.queue_frame(frame)
        _LOGGER.info("HeliosPro: queued device time %02d:%02d → %s", h, mi, frame.hex(" "))

    def set_device_datetime(self, year: int, month: int, day: int, hour: int, minute: int):
        y = max(0, min(255, int(year) - 2000))
        m = max(1, min(12, int(month)))
        d = max(1, min(31, int(day)))
        h = max(0, min(23, int(hour)))
        mi = max(0, min(59, int(minute)))
        f_date = self._build_write_var(HeliosVar.Var_07_date_month_year, [d, m, y])
        f_time = self._build_write_var(HeliosVar.Var_08_time_hour_min, [h, mi])
        self.queue_frame(f_date)
        self.queue_frame(f_time)
        self.queue_frame(self._build_read_request(HeliosVar.Var_07_date_month_year))
        _LOGGER.info(
            "HeliosPro: queued device datetime %04d-%02d-%02d %02d:%02d",
            int(year), m, d, h, mi,
        )
