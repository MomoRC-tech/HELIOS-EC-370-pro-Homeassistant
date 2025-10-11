from __future__ import annotations

import logging
from typing import Any, Optional
import os

# Dynamic import pattern to avoid editor errors outside HA runtime
try:  # pragma: no cover
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.components.fan import (
        FanEntity,
        FanEntityFeature,
    )
    from homeassistant.helpers.entity import DeviceInfo
except Exception:  # pragma: no cover
    HomeAssistant = Any  # type: ignore
    ConfigEntry = Any  # type: ignore
    class FanEntity:  # type: ignore
        _attr_should_poll = False
        def async_write_ha_state(self): pass
    class FanEntityFeature:  # type: ignore
        SET_SPEED = 1
        PRESET_MODE = 2
        TURN_ON = 4
        TURN_OFF = 8
    class DeviceInfo:  # type: ignore
        def __init__(self, **kwargs): pass

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PERCENT_STEPS = [0, 25, 50, 75, 100]
PRESET_MODES = ["manual", "auto"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    async_add_entities([HeliosFan(coord, entry)])


class HeliosFan(FanEntity):
    _attr_should_poll = False
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
    _attr_preset_modes = PRESET_MODES
    _attr_name = "Helios Lüfter"

    def __init__(self, coord: Any, entry: ConfigEntry) -> None:
        self._coord = coord
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}-fan"
        self._entity_picture_url = "/local/helios_ec_pro.png"
        self._entity_picture_exists: Optional[bool] = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Helios EC-Pro",
            manufacturer="Helios",
            model="EC-Pro",
        )
        try:
            if hasattr(coord, "register_entity"):
                coord.register_entity(self)
        except Exception:
            pass

    @property
    def entity_picture(self) -> Optional[str]:
        # Optional: show /local/helios_ec_pro.png if user placed it in config/www
        try:
            if self._entity_picture_exists is False:
                return None
            if self.hass is None:
                return None
            if self._entity_picture_exists is None:
                exists = False
                try:
                    for fn in ("MomoRC_HELIOS_HASS.png", "helios_ec_pro.png"):
                        fs_path = self.hass.config.path(f"www/{fn}")
                        if os.path.exists(fs_path):
                            exists = True
                            break
                except Exception:
                    pass
                try:
                    for fn in ("MomoRC_HELIOS_HASS.png", "helios_ec_pro.png"):
                        pkg_path = os.path.join(os.path.dirname(__file__), fn)
                        if os.path.exists(pkg_path):
                            exists = True
                            break
                except Exception:
                    pass
                self._entity_picture_exists = exists
            return self._entity_picture_url if self._entity_picture_exists else None
        except Exception:
            return None

    # ---------- State ----------
    @property
    def percentage(self) -> Optional[int]:
        lvl = int(self._coord.data.get("fan_level", 0) or 0)
        lvl = max(0, min(4, lvl))
        return PERCENT_STEPS[lvl]

    @property
    def preset_mode(self) -> Optional[str]:
        return "auto" if self._coord.data.get("auto_mode", False) else "manual"

    # ---------- Commands ----------
    async def async_set_percentage(self, percentage: int) -> None:
        # Map 0..100 to 0..4
        percentage = max(0, min(100, int(percentage)))
        # Find nearest step
        nearest = min(PERCENT_STEPS, key=lambda s: abs(s - percentage))
        level = PERCENT_STEPS.index(nearest)
        try:
            if hasattr(self._coord, "set_fan_level"):
                self._coord.set_fan_level(level)
        except Exception as exc:
            _LOGGER.warning("Failed to set percentage %s (level %s): %s", percentage, level, exc)
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        want_auto = preset_mode == "auto"
        try:
            if hasattr(self._coord, "set_auto_mode"):
                self._coord.set_auto_mode(want_auto)
        except Exception as exc:
            _LOGGER.warning("Failed to set preset %s: %s", preset_mode, exc)
        self.async_write_ha_state()

    async def async_turn_on(self, percentage: Optional[int] = None, **kwargs: Any) -> None:
        # If manual and at level 0, set to level 1; else respect provided percentage
        try:
            if percentage is None:
                lvl = int(self._coord.data.get("fan_level", 0) or 0)
                auto = bool(self._coord.data.get("auto_mode", False))
                if lvl == 0 and not auto:
                    if hasattr(self._coord, "set_fan_level"):
                        self._coord.set_fan_level(1)
                else:
                    # already running or auto; no-op
                    pass
            else:
                await self.async_set_percentage(percentage)
        except Exception as exc:
            _LOGGER.warning("Failed to turn on: %s", exc)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            if hasattr(self._coord, "set_auto_mode"):
                self._coord.set_auto_mode(False)
            if hasattr(self._coord, "set_fan_level"):
                self._coord.set_fan_level(0)
        except Exception as exc:
            _LOGGER.warning("Failed to turn off: %s", exc)
        self.async_write_ha_state()
