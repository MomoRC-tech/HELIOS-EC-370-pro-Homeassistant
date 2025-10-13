# __init__.py (essentials)
import logging, threading, voluptuous as vol, os, json, base64
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.util.yaml import load_yaml
from homeassistant.components.http import HomeAssistantView
from aiohttp import web

from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT
from .coordinator import HeliosCoordinatorWithQueue
from .broadcast_listener import HeliosBroadcastReader

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SWITCH, Platform.FAN, Platform.SELECT]

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
    # Read from options first (if set), then fall back to data, then defaults
    host = entry.options.get("host", entry.data.get("host", DEFAULT_HOST))
    port = entry.options.get("port", entry.data.get("port", DEFAULT_PORT))

    coord = HeliosCoordinatorWithQueue(hass)
    stop_event = threading.Event()
    reader = HeliosBroadcastReader(host, port, coord, stop_event)
    reader.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "stop_event": stop_event, "reader": reader, "coordinator": coord
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Read version from manifest.json to keep log in sync with manifest
    version = None
    try:
        manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            version = json.load(f).get("version")
    except Exception:
        pass
    ver_str = f"v{version}" if version else "(version unknown)"
    _LOGGER.info("✅ Helios EC-Pro %s initialized for %s:%d (entry=%s)", ver_str, host, port, entry.entry_id)

    # ----- HTTP view to serve an optional device image -----
    try:
        # Register once per HA instance
        key = "_image_view_registered"
        hass.data.setdefault(DOMAIN, {})
        if not hass.data[DOMAIN].get(key):
            class HeliosImageView(HomeAssistantView):
                url = "/api/helios_pro_ventilation/image.png"
                name = "api:helios_pro_ventilation:image"
                requires_auth = False

                async def get(self, request):  # type: ignore[override]
                    hass_local: HomeAssistant = request.app["hass"]  # type: ignore
                    # Try config/www first, then packaged image in the integration folder, else return a 1x1 transparent PNG
                    try:
                        candidates = [
                            hass_local.config.path("www/MomoRC_HELIOS_HASS.png"),
                            hass_local.config.path("www/helios_ec_pro.png"),
                            os.path.join(os.path.dirname(__file__), "MomoRC_HELIOS_HASS.png"),
                            os.path.join(os.path.dirname(__file__), "helios_ec_pro.png"),
                        ]
                        for path in candidates:
                            if os.path.exists(path):
                                with open(path, "rb") as f:
                                    data = f.read()
                                return web.Response(body=data, content_type="image/png")
                    except Exception:
                        pass
                    # 1x1 transparent PNG fallback
                    pixel_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
                    data = base64.b64decode(pixel_b64)
                    return web.Response(body=data, content_type="image/png")

            hass.http.register_view(HeliosImageView())
            hass.data[DOMAIN][key] = True
    except Exception as exc:
        _LOGGER.debug("Image HTTP view registration skipped: %s", exc)

    # ----- Services (register once) -----
    if not hass.services.has_service(DOMAIN, "set_fan_level"):
        import voluptuous as vol
        SERVICE_SET_AUTO_MODE_SCHEMA = vol.Schema({ vol.Optional("enabled", default=True): cv.boolean })
        SERVICE_SET_FAN_LEVEL_SCHEMA = vol.Schema({ vol.Required("level"): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)) })
        SERVICE_SET_PARTY_ENABLED_SCHEMA = vol.Schema({ vol.Optional("enabled", default=True): cv.boolean })
        # Calendar services
        SERVICE_CALENDAR_REQUEST_SCHEMA = vol.Schema({ vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)) })
        SERVICE_CALENDAR_SET_SCHEMA = vol.Schema({
            vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
            vol.Required("levels"): vol.All(list, vol.Length(min=48, max=48)),
        })

        async def handle_set_auto_mode(call):
            for d in hass.data.get(DOMAIN, {}).values():
                d["coordinator"].set_auto_mode(bool(call.data.get("enabled", True)))

        async def handle_set_fan_level(call):
            lvl = int(call.data.get("level", 0))
            for d in hass.data.get(DOMAIN, {}).values():
                d["coordinator"].set_fan_level(lvl)

        async def handle_set_party_enabled(call):
            enabled = bool(call.data.get("enabled", True))
            for d in hass.data.get(DOMAIN, {}).values():
                coord = d["coordinator"]
                if hasattr(coord, "set_party_enabled"):
                    coord.set_party_enabled(enabled)

        hass.services.async_register(DOMAIN, "set_auto_mode", handle_set_auto_mode, schema=SERVICE_SET_AUTO_MODE_SCHEMA)
        hass.services.async_register(DOMAIN, "set_fan_level", handle_set_fan_level, schema=SERVICE_SET_FAN_LEVEL_SCHEMA)
        hass.services.async_register(DOMAIN, "set_party_enabled", handle_set_party_enabled, schema=SERVICE_SET_PARTY_ENABLED_SCHEMA)

        async def handle_calendar_request(call):
            day = int(call.data.get("day"))
            for d in hass.data.get(DOMAIN, {}).values():
                d["coordinator"].request_calendar_day(day)

        async def handle_calendar_set(call):
            day = int(call.data.get("day"))
            levels = list(call.data.get("levels"))
            for d in hass.data.get(DOMAIN, {}).values():
                d["coordinator"].set_calendar_day(day, levels)

        hass.services.async_register(DOMAIN, "calendar_request_day", handle_calendar_request, schema=SERVICE_CALENDAR_REQUEST_SCHEMA)
        hass.services.async_register(DOMAIN, "calendar_set_day", handle_calendar_set, schema=SERVICE_CALENDAR_SET_SCHEMA)

        # bind services.yaml so the Integration tile shows service descriptions
        try:
            services_path = os.path.join(os.path.dirname(__file__), "services.yaml")
            desc = await hass.async_add_executor_job(load_yaml, services_path)
            if isinstance(desc, dict):
                for srv, schema in desc.items():
                    async_set_service_schema(hass, DOMAIN, srv, schema)
        except Exception:  # fine if it’s missing
            pass

    _LOGGER.info("✅ Helios services ready: set_auto_mode, set_fan_level, set_party_enabled, calendar_request_day, calendar_set_day")

    # Register options update listener to reload the integration when options change
    entry.async_on_unload(entry.add_update_listener(async_options_update_listener))

    return True

async def async_options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update by reloading the integration."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        data["stop_event"].set()
    return unloaded
