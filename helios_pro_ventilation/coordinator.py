from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict

class HeliosCoordinator:
    def __init__(self, hass):
        self.hass = hass
        self.entities = []
        self.data: Dict[str, Any] = {}

        # Icing protection: enabled by default, inactive at startup
        self.icing_protection_enabled = True
        self.data["icing_protection_active"] = False
        self._icing_start_time = None

        # Rolling 24h counter of icing protection triggers (cap size defensively)
        self._icing_trigger_ts = deque(maxlen=500)
        self.data["icing_triggers_24h"] = 0

    def register_entity(self, entity):
        self.entities.append(entity)

    def set_fan_level(self, level: int):
        """Stub or existing implementation that sets fan level on device."""
        pass

    def update_values(self, new_values: Dict[str, Any]):
        """
        Update coordinator values and manage icing protection logic.
        Expected keys in new_values may include: temp_outdoor, fan_level, etc.
        """
        icing_threshold = 4.0  # Ensure this matches actual project constant

        old_fan_level = self.data.get("fan_level")

        # Merge incoming values first
        for k, v in new_values.items():
            if k.startswith("_"):
                continue
            self.data[k] = v

        if self.icing_protection_enabled:
            temp_outdoor = self.data.get("temp_outdoor")
            fan_level = self.data.get("fan_level")
            now = time.time()
            was_active = bool(self.data.get("icing_protection_active", False))

            if temp_outdoor is not None:
                if temp_outdoor < icing_threshold:
                    if self._icing_start_time is None:
                        self._icing_start_time = now
                    if now - self._icing_start_time > 600:  # 10 minutes
                        if fan_level != 0:
                            self.set_fan_level(0)
                        if not was_active:
                            self._icing_trigger_ts.append(now)
                        self.data["icing_protection_active"] = True
                else:
                    self._icing_start_time = None
                    self.data["icing_protection_active"] = False

            if (
                fan_level is not None
                and fan_level != 0
                and old_fan_level == 0
                and self.data.get("icing_protection_active")
            ): 
                self.data["icing_protection_active"] = False

            cutoff = now - 86400
            while self._icing_trigger_ts and self._icing_trigger_ts[0] < cutoff:
                self._icing_trigger_ts.popleft()
            self.data["icing_triggers_24h"] = len(self._icing_trigger_ts)

        for entity in self.entities:
            try:
                entity.handle_coordinator_update()
            except Exception:
                pass