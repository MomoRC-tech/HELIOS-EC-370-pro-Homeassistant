from __future__ import annotations

import logging
from typing import Any
import importlib

# Dynamic import to avoid editor/linter import errors outside HA runtime
try:  # pragma: no cover - best-effort import when HA is installed
    ha_core = importlib.import_module("homeassistant.core")
    ha_entries = importlib.import_module("homeassistant.config_entries")
    ha_switch = importlib.import_module("homeassistant.components.switch")
    HomeAssistant = getattr(ha_core, "HomeAssistant")  # type: ignore
    ConfigEntry = getattr(ha_entries, "ConfigEntry")  # type: ignore
    SwitchEntity = getattr(ha_switch, "SwitchEntity")  # type: ignore
    ha_entity = importlib.import_module("homeassistant.helpers.entity")
    DeviceInfo = getattr(ha_entity, "DeviceInfo")  # type: ignore
    EntityCategory = getattr(ha_entity, "EntityCategory")  # type: ignore
except Exception:  # pragma: no cover - fallback for local editors/tests
    HomeAssistant = Any  # type: ignore
    ConfigEntry = Any  # type: ignore
    class SwitchEntity:  # type: ignore
        hass: Any = None
        def async_write_ha_state(self) -> None:  # type: ignore
            return
    class DeviceInfo:  # type: ignore
        def __init__(self, **kwargs):
            pass
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

from .const import DOMAIN
from .debug_scanner import HeliosDebugScanner

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coordinator"]

    entities: list[SwitchEntity] = [
        HeliosDebugScanSwitch(coord, entry.entry_id),
        HeliosFanLevel1ToggleSwitch(coord, entry),
    ]
    async_add_entities(entities)


class HeliosDebugScanSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coord = coordinator
        self._entry_id = entry_id
        self._is_on = False
        self._output_path: str | None = None
        self._scanner = HeliosDebugScanner(self._coord, on_complete=self._on_scan_complete, output_path=self._output_path)
        # Requested stable entity id and name
        try:
            self.entity_id = "switch.helios_ec_pro_variablen_scan_debug"
        except Exception:
            # entity registry may override; best-effort assignment
            pass
        # Attach to the integration device so it appears on the card
        try:
            from .const import DOMAIN
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry_id)},
                name="Helios EC-Pro",
                manufacturer="Helios",
                model="EC-Pro",
            )
            # Diagnostic entity, hidden by default
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
        except Exception:
            pass

    @property
    def unique_id(self) -> str:
        # stable unique id so entity id persists
        return "helios_ec_pro_variablen_scan_debug"

    @property
    def name(self) -> str:
        # Requested friendly name
        return "variablen Scan (debug)"

    @property
    def icon(self) -> str | None:
        return "mdi:magnify-scan"

    @property
    def is_on(self) -> bool:
        return self._is_on or self._scanner.is_active

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._scanner.is_active:
            _LOGGER.info("HeliosDebug: scan already running; ignoring turn_on")
            return
        # Optional: allow passing a 'path' kwarg to write the summary to
        path = kwargs.get("path") if isinstance(kwargs, dict) else None
        if isinstance(path, str) and path:
            self._output_path = path
            # Recreate scanner with the new output path
            self._scanner = HeliosDebugScanner(self._coord, on_complete=self._on_scan_complete, output_path=self._output_path)
        self._is_on = True
        self.async_write_ha_state()

        # Kick off in executor to avoid any sync work on event loop
        def _start():
            try:
                self._scanner.trigger_scan()
            except Exception as exc:
                _LOGGER.warning("HeliosDebug: failed to start scan: %s", exc)
        await self.hass.async_add_executor_job(_start)

    async def async_turn_off(self, **kwargs: Any) -> None:
        # It's a one-shot; turning off just clears the visual state
        self._is_on = False
        self.async_write_ha_state()

    def _on_scan_complete(self) -> None:
        # Called from worker thread; bounce to HA loop and switch off
        def _clear():
            self._is_on = False
            self.async_write_ha_state()
        try:
            self.hass.loop.call_soon_threadsafe(_clear)
        except Exception:
            pass

    async def async_added_to_hass(self) -> None:
        try:
            if hasattr(self._coord, "register_entity"):
                self._coord.register_entity(self)
        except Exception:
            pass


class HeliosFanLevel1ToggleSwitch(SwitchEntity):
    """Primary switch to toggle ventilation between OFF and manual level 1.

    - turn_on(): ensure manual mode and set fan level = 1
    - turn_off(): ensure manual mode and set fan level = 0 (OFF)
    - is_on: True when manual mode and current level == 1
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: Any, entry: Any) -> None:
        self._coord = coordinator
        self._entry = entry
        try:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry.entry_id)},
                name="Helios EC-Pro",
                manufacturer="Helios",
                model="EC-Pro",
            )
        except Exception:
            pass
        # Stable unique id derived from entry id
        try:
            self._attr_unique_id = f"{entry.entry_id}-toggle_level1"
        except Exception:
            self._attr_unique_id = "helios_toggle_level1"

    @property
    def name(self) -> str:
        return "Lüftung EIN/AUS (Stufe 1)"

    @property
    def icon(self) -> str | None:
        return "mdi:fan" if self.is_on else "mdi:fan-off"

    @property
    def is_on(self) -> bool:
        try:
            auto = bool(self._coord.data.get("auto_mode", False))
            lvl = int(self._coord.data.get("fan_level", 0) or 0)
            return (not auto) and (lvl == 1)
        except Exception:
            return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            if hasattr(self._coord, "set_auto_mode"):
                self._coord.set_auto_mode(False)
            if hasattr(self._coord, "set_fan_level"):
                self._coord.set_fan_level(1)
        except Exception as exc:
            _LOGGER.warning("Helios toggle: failed to turn on level 1: %s", exc)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        # Register for coordinator push updates now that hass is set
        try:
            if hasattr(self._coord, "register_entity"):
                self._coord.register_entity(self)
        except Exception:
            pass

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            if hasattr(self._coord, "set_auto_mode"):
                self._coord.set_auto_mode(False)
            if hasattr(self._coord, "set_fan_level"):
                self._coord.set_fan_level(0)
        except Exception as exc:
            _LOGGER.warning("Helios toggle: failed to turn off (level 0): %s", exc)
        self.async_write_ha_state()
