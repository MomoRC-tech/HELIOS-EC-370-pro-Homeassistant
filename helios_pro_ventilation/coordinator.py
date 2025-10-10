import logging, time, threading
from typing import Any, Dict, List
from collections import deque
from .const import HeliosVar, CLIENT_ID

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
    def _build_write_frame(self, var_index: int, *data_bytes: int) -> bytes:
        """Generic write frame builder: [CLIENT][0x01][len][var][data...][chk]."""
        length = 1 + len(data_bytes)
        payload = bytes([CLIENT_ID, 0x01, length, var_index, *data_bytes])
        chk = _checksum(payload)
        return payload + bytes([chk])

    # ---------- SERVICE HANDLERS ----------
    def set_auto_mode(self, enabled: bool):
        """Enable or disable AUTO mode."""
        # New API: write to auto_mode variable (0x11) with 0/1
        frame = self._build_write_frame(HeliosVar.Var_11_auto_mode.index, 0x01 if enabled else 0x00)
        self.queue_frame(frame)
        _LOGGER.info(
            "HeliosPro: queued %s mode frame → %s",
            "AUTO" if enabled else "MANUAL",
            frame.hex(" "),
        )

    def set_fan_level(self, level: int):
        """Set manual fan level 0–4."""
        level = max(0, min(4, level))
        # New API: write to fan_level variable (0x10) with 0..4
        frame = self._build_write_frame(HeliosVar.Var_10_fan_level.index, level)
        self.queue_frame(frame)
        _LOGGER.info(
            "HeliosPro: queued manual fan level %d frame → %s",
            level,
            frame.hex(" "),
        )
