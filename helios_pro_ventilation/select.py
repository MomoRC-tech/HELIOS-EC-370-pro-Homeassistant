from __future__ import annotations

import logging
from typing import Any

try:  # pragma: no cover - dynamic import for local editors
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.components.select import SelectEntity
    from homeassistant.helpers.entity import DeviceInfo
except Exception:  # pragma: no cover
    HomeAssistant = Any  # type: ignore
    ConfigEntry = Any  # type: ignore
    class SelectEntity:  # type: ignore
        options: list[str] = []
        def async_write_ha_state(self): pass
    class DeviceInfo:  # type: ignore
        def __init__(self, **kwargs): pass

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FAN_LEVEL_OPTIONS = ["0", "1", "2", "3", "4"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]
    async_add_entities([HeliosFanLevelSelect(coord, entry)])


class HeliosFanLevelSelect(SelectEntity):
    _attr_should_poll = False
    _attr_name = "Lüfterstufe (Auswahl)"
    _attr_options = FAN_LEVEL_OPTIONS

    def __init__(self, coord: Any, entry: ConfigEntry) -> None:
        self._coord = coord
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}-fanlevel-select"
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
    def current_option(self) -> str | None:
        lvl = int(self._coord.data.get("fan_level", 0) or 0)
        lvl = max(0, min(4, lvl))
        return str(lvl)

    async def async_select_option(self, option: str) -> None:
        try:
            level = int(option)
            level = max(0, min(4, level))
            if hasattr(self._coord, "set_fan_level"):
                self._coord.set_fan_level(level)
        except Exception as exc:
            _LOGGER.warning("Failed to set fan level via select to %s: %s", option, exc)
        self.async_write_ha_state()
