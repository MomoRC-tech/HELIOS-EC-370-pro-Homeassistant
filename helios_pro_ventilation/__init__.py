# __init__.py (essentials)
import logging, threading, voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.util.yaml import load_yaml
import os

from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT
from .coordinator import HeliosCoordinatorWithQueue
from .broadcast_listener import HeliosBroadcastReader

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CLIMATE]

# --- YAML support: import → create a config entry so devices/entities show in UI
async def async_setup(hass: HomeAssistant, config: dict):
    """Set up from YAML (once), by importing into a config entry."""
    if DOMAIN not in config:
        return True

    data = {
        "host": config[DOMAIN].get("host", DEFAULT_HOST),
        "port": config[DOMAIN].get("port", DEFAULT_PORT),
    }

    # If an entry already exists (UI or previous import), do nothing.
    existing = hass.config_entries.async_entries(DOMAIN)
    for e in existing:
        # Same host/port or any prior SOURCE_IMPORT entry → skip creating a new flow
        if e.source == SOURCE_IMPORT or e.data.get("host") == data["host"]:
            return True

    # Otherwise import once
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=data
    )
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    host = entry.data.get("host", DEFAULT_HOST)
    port = entry.data.get("port", DEFAULT_PORT)

    coord = HeliosCoordinatorWithQueue(hass)
    stop_event = threading.Event()
    reader = HeliosBroadcastReader(host, port, coord, stop_event)
    reader.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "stop_event": stop_event, "reader": reader, "coordinator": coord
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("✅ Helios EC-Pro v2.6.0 initialized for %s:%d (entry=%s)", host, port, entry.entry_id)

    # ----- Services (register once) -----
    if not hass.services.has_service(DOMAIN, "set_fan_level"):
        import voluptuous as vol
        SERVICE_SET_AUTO_MODE_SCHEMA = vol.Schema({ vol.Optional("enabled", default=True): cv.boolean })
        SERVICE_SET_FAN_LEVEL_SCHEMA = vol.Schema({ vol.Required("level"): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)) })

        async def handle_set_auto_mode(call):
            for d in hass.data.get(DOMAIN, {}).values():
                d["coordinator"].set_auto_mode(bool(call.data.get("enabled", True)))

        async def handle_set_fan_level(call):
            lvl = int(call.data.get("level", 0))
            for d in hass.data.get(DOMAIN, {}).values():
                d["coordinator"].set_fan_level(lvl)

        hass.services.async_register(DOMAIN, "set_auto_mode", handle_set_auto_mode, schema=SERVICE_SET_AUTO_MODE_SCHEMA)
        hass.services.async_register(DOMAIN, "set_fan_level", handle_set_fan_level, schema=SERVICE_SET_FAN_LEVEL_SCHEMA)

        # bind services.yaml so the Integration tile shows “2 services”
        try:
            services_path = os.path.join(os.path.dirname(__file__), "services.yaml")
            desc = await hass.async_add_executor_job(load_yaml, services_path)
            if isinstance(desc, dict):
                for srv, schema in desc.items():
                    async_set_service_schema(hass, DOMAIN, srv, schema)
        except Exception:  # fine if it’s missing
            pass

        _LOGGER.info("✅ Helios services ready: set_auto_mode, set_fan_level")

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        data["stop_event"].set()
    return unloaded
