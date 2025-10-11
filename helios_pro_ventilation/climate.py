from __future__ import annotations
# climate.py

import logging
from typing import Any, Optional
import os

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    ClimateEntityFeature,
    HVACAction,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import ATTR_SUPPORTED_FEATURES

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Für Lüftungsgeräte sind OFF und FAN_ONLY die passenden HVAC-Modi
HVAC_MODES = [HVACMode.OFF, HVACMode.FAN_ONLY]
PRESET_MODES = ["auto", "manual"]
# UI-seitige Lüfterstufen 1–4 (0 entspricht AUS; wird nicht als Fan-Mode angezeigt)
FAN_MODES = ["1", "2", "3", "4"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]  # muss .data/.set_auto_mode/.set_fan_level besitzen
    async_add_entities([HeliosClimate(coord, entry)])


class HeliosClimate(ClimateEntity):
    """Climate-Entity für Helios EC-Pro: Fan-only + Auto/Manuell Presets."""

    _attr_should_poll = False
    _attr_hvac_modes = HVAC_MODES
    _attr_supported_features = (
        ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.FAN_MODE
    )
    _attr_preset_modes = PRESET_MODES
    _attr_fan_modes = FAN_MODES

    def __init__(self, coord: Any, entry: ConfigEntry):
        self._coord = coord
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}-climate"
        self._attr_name = "Helios Lüftung"
        # Use API endpoint which serves either config/www image or packaged one
        self._entity_picture_url = "/api/helios_pro_ventilation/image.png"
        self._entity_picture_exists = None  # type: Optional[bool]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Helios EC-Pro",
            manufacturer="Helios",
            model="EC-Pro",
        )
        # Register for push updates from the coordinator
        try:
            if hasattr(coord, "register_entity"):
                coord.register_entity(self)
        except Exception:
            pass

        # Push model: we get updates from the coordinator, so don't poll.
        self._attr_should_poll = False

        # Fan modes “0..4” so Mushroom can show/track the current selection.
        self._attr_fan_modes = ["0", "1", "2", "3", "4"]

        # Manual/Auto presets; this is what your logic already uses.
        self._attr_preset_modes = ["manual", "auto"]

        # Make sure the card exposes the right features to the UI.
        self._attr_supported_features = (
            ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.PRESET_MODE
        )

    @property
    def entity_picture(self) -> Optional[str]:
        # Always return our API endpoint; it serves www or packaged image,
        # and falls back to a 1x1 transparent PNG if none found.
        return self._entity_picture_url
    # -----------------------
    #      Live-Daten
    # -----------------------
    @property
    def hvac_mode(self):
        fan_level = int(self._coord.data.get("fan_level", 0) or 0)
        auto = bool(self._coord.data.get("auto_mode", False))
        # OFF only if manual and level 0; any auto or level>0 is FAN_ONLY
        return HVACMode.OFF if (fan_level <= 0 and not auto) else HVACMode.FAN_ONLY

    @property
    def hvac_action(self):
        fan_level = int(self._coord.data.get("fan_level", 0) or 0)
        auto = bool(self._coord.data.get("auto_mode", False))
        # Expose current action explicitly (drawn by Mushroom)
        return HVACAction.FAN if (fan_level > 0 or auto) else HVACAction.OFF

    @property
    def preset_mode(self) -> Optional[str]:
        return "auto" if self._coord.data.get("auto_mode", False) else "manual"

    @property
    def fan_mode(self) -> Optional[str]:
        lvl = int(self._coord.data.get("fan_level", 0) or 0)
        # Align with supported fan modes ["0".."4"]: report "0" when level is 0
        return str(min(max(lvl, 0), 4))

    @property
    def current_temperature(self) -> Optional[float]:
        # Anzeige-Temperatur: bevorzugt Zuluft, sonst Abluft (falls vorhanden)
        return (
            self._coord.data.get("temp_supply")
            or self._coord.data.get("temp_extract")
            or None
        )

    @property
    def temperature_unit(self) -> str:
        return "°C"

    # -----------------------
    #        Setzen
    # -----------------------
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            # Manuell AUS: Auto deaktivieren + Stufe 0
            try:
                if hasattr(self._coord, "set_auto_mode"):
                    self._coord.set_auto_mode(False)
            except Exception as exc:
                _LOGGER.warning("Failed to disable auto mode: %s", exc)
            try:
                if hasattr(self._coord, "set_fan_level"):
                    self._coord.set_fan_level(0)
            except Exception as exc:
                _LOGGER.warning("Failed to set fan level 0: %s", exc)
        elif hvac_mode == HVACMode.FAN_ONLY:
            # Wenn aktuell OFF und nicht Auto, setze eine sinnvolle Stufe (1)
            try:
                fan_level = int(self._coord.data.get("fan_level", 0) or 0)
                auto = bool(self._coord.data.get("auto_mode", False))
                if fan_level == 0 and not auto and hasattr(self._coord, "set_fan_level"):
                    self._coord.set_fan_level(1)
            except Exception as exc:
                _LOGGER.warning("Failed to set fan level 1: %s", exc)
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        want_auto = preset_mode == "auto"
        try:
            if hasattr(self._coord, "set_auto_mode"):
                self._coord.set_auto_mode(want_auto)
        except Exception as exc:
            _LOGGER.warning("Failed to set auto mode %s: %s", want_auto, exc)
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        try:
            if hasattr(self._coord, "set_fan_level"):
                level = int(fan_mode)
                self._coord.set_fan_level(level)
        except Exception as exc:
            _LOGGER.warning("Failed to set fan level %s: %s", fan_mode, exc)
        self.async_write_ha_state()
