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
