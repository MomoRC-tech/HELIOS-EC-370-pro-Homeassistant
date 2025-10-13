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
        self.send_slot_active: bool = False
        self.send_slot_expires: float = 0.0
        self.send_slot_event = threading.Event()
        # Optional callback used by the debug scanner to receive parsed var responses
        self.debug_var_callback = None  # type: ignore[assignment]

    def register_entity(self, entity):
        self.entities.append(entity)

    def mark_ping(self):
        now = time.time()
        self.last_ping_time = now
        self.send_slot_active = True
        self.send_slot_expires = now + 0.08
        self.send_slot_event.set()

    def tick(self):
        if self.send_slot_active and time.time() > self.send_slot_expires:
            self.send_slot_active = False
            self.send_slot_event.clear()

    def update_values(self, new_values: Dict[str, Any]):
        changed = False
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

    # ---------- TX QUEUE ----------
    def queue_frame(self, frame: bytes):
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
        payload = bytes([
            CLIENT_ID,
            0x01,  # write
            0x02,  # payload length (Var + 1 byte)
            int(var),
            value & 0xFF,
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
