# __init__.py (essentials)
import logging, threading, voluptuous as vol, os, json, base64
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.util.yaml import load_yaml
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
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
    # Propagate options for auto time sync behavior
    try:
        coord.auto_time_sync = bool(entry.options.get("auto_time_sync", False))  # type: ignore[attr-defined]
        coord.time_sync_max_drift_min = int(entry.options.get("time_sync_max_drift_min", 20))  # type: ignore[attr-defined]
    except Exception:
        pass
    stop_event = threading.Event()
    reader = HeliosBroadcastReader(host, port, coord, stop_event)
    reader.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "stop_event": stop_event, "reader": reader, "coordinator": coord
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Read version from manifest.json using thread executor to avoid blocking the event loop
    version = None
    try:
        manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
        def _read_manifest(p: str):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f).get("version")
        version = await hass.async_add_executor_job(_read_manifest, manifest_path)
    except Exception:
        version = None
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

        # Register embedded calendar UI and API (no auth per user request)
        ui_key = "_calendar_ui_registered"
        api_key = "_calendar_api_registered"
        if not hass.data[DOMAIN].get(ui_key):
            class HeliosCalendarUiView(HomeAssistantView):
                url = "/api/helios_pro_ventilation/calendar.html"
                name = "api:helios_pro_ventilation:calendar_ui"
                requires_auth = False

                async def get(self, request):  # type: ignore[override]
                    # Serve the external HTML file instead of embedding it here
                    try:
                        html_path = os.path.join(os.path.dirname(__file__), "calendar.html")
                        if os.path.exists(html_path):
                            return web.FileResponse(path=html_path)
                        # Fallback: not found page
                        return web.Response(text="<html><body><h3>calendar.html not found</h3></body></html>", content_type="text/html", status=404)
                    except Exception as exc:
                        return web.Response(text=f"Error serving calendar.html: {exc}", content_type="text/plain", status=500)

            hass.http.register_view(HeliosCalendarUiView())
            hass.data[DOMAIN][ui_key] = True

        if not hass.data[DOMAIN].get(api_key):
            # GET /calendar.json
            class HeliosCalendarJson(HomeAssistantView):
                url = "/api/helios_pro_ventilation/calendar.json"
                name = "api:helios_pro_ventilation:calendar_json"
                requires_auth = False

                async def get(self, request):  # type: ignore[override]
                    hass_local: HomeAssistant = request.app["hass"]  # type: ignore
                    coord = None
                    for d in hass_local.data.get(DOMAIN, {}).values():
                        if isinstance(d, dict) and "coordinator" in d:
                            coord = d["coordinator"]; break
                    if coord is None:
                        return web.json_response({"days": [None]*7, "meta": {"error": "no coordinator"}})
                    days = []
                    missing = []
                    for i in range(7):
                        v = coord.data.get(f"calendar_day_{i}")
                        if not isinstance(v, list) or len(v) != 48:
                            days.append(None); missing.append(i)
                            try:
                                coord.request_calendar_day(i)
                            except Exception:
                                pass
                        else:
                            days.append([int(x) for x in v])
                    meta = {
                        "missing_days": missing,
                        "date_str": coord.data.get("date_str"),
                        "time_str": coord.data.get("time_str"),
                        "clock_drift_min": coord.data.get("device_clock_drift_min"),
                        "clock_in_sync": coord.data.get("device_clock_in_sync"),
                        "date_time_state": coord.data.get("device_date_time_state"),
                    }
                    return web.json_response({"days": days, "meta": meta})

            # POST /calendar/set
            class HeliosCalendarSet(HomeAssistantView):
                url = "/api/helios_pro_ventilation/calendar/set"
                name = "api:helios_pro_ventilation:calendar_set"
                requires_auth = False

                async def post(self, request):  # type: ignore[override]
                    hass_local: HomeAssistant = request.app["hass"]  # type: ignore
                    coord = None
                    for d in hass_local.data.get(DOMAIN, {}).values():
                        if isinstance(d, dict) and "coordinator" in d:
                            coord = d["coordinator"]; break
                    if coord is None:
                        return web.json_response({"ok": False, "error": "no coordinator"}, status=400)
                    try:
                        body = await request.json()
                        day = int(body.get("day"))
                        levels = list(body.get("levels"))
                        if len(levels) != 48:
                            return web.json_response({"ok": False, "error": "levels must have length 48"}, status=400)
                        lv = [max(0, min(4, int(x))) for x in levels]
                        coord.set_calendar_day(day, lv)
                        try: coord.request_calendar_day(day)
                        except Exception: pass
                        return web.json_response({"ok": True})
                    except Exception as exc:
                        return web.json_response({"ok": False, "error": str(exc)}, status=400)

            # POST /calendar/copy
            class HeliosCalendarCopy(HomeAssistantView):
                url = "/api/helios_pro_ventilation/calendar/copy"
                name = "api:helios_pro_ventilation:calendar_copy"
                requires_auth = False

                async def post(self, request):  # type: ignore[override]
                    hass_local: HomeAssistant = request.app["hass"]  # type: ignore
                    coord = None
                    for d in hass_local.data.get(DOMAIN, {}).values():
                        if isinstance(d, dict) and "coordinator" in d:
                            coord = d["coordinator"]; break
                    if coord is None:
                        return web.json_response({"ok": False, "error": "no coordinator"}, status=400)
                    try:
                        body = await request.json()
                        src = int(body.get("source_day"))
                        targets = [int(x) for x in (body.get("target_days") or [])]
                        if not targets:
                            return web.json_response({"ok": False, "error": "target_days required"}, status=400)
                        coord.copy_calendar_day(src, targets)
                        return web.json_response({"ok": True})
                    except Exception as exc:
                        return web.json_response({"ok": False, "error": str(exc)}, status=400)

            hass.http.register_view(HeliosCalendarJson())
            hass.http.register_view(HeliosCalendarSet())
            hass.http.register_view(HeliosCalendarCopy())
            hass.data[DOMAIN][api_key] = True
    except Exception as exc:
        _LOGGER.debug("Image HTTP view registration skipped: %s", exc)

    # ----- Sidebar panel (iframe) for quick access to the calendar editor -----
    try:
        hass.data.setdefault(DOMAIN, {})
        if not hass.data[DOMAIN].get("_panel_registered"):
            async_register_built_in_panel(
                hass,
                component_name="iframe",
                sidebar_title="Helios Calendar",
                sidebar_icon="mdi:calendar-clock",
                url_path="helios-calendar",
                config={"url": "/api/helios_pro_ventilation/calendar.html"},
                require_admin=False,
            )
            hass.data[DOMAIN]["_panel_registered"] = True
    except Exception as exc:
        _LOGGER.debug("Sidebar panel registration skipped: %s", exc)

    # ----- Services (register once) -----
    if not hass.services.has_service(DOMAIN, "set_fan_level"):
        SERVICE_SET_AUTO_MODE_SCHEMA = vol.Schema({ vol.Optional("enabled", default=True): cv.boolean })
        SERVICE_SET_FAN_LEVEL_SCHEMA = vol.Schema({ vol.Required("level"): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)) })
        SERVICE_SET_PARTY_ENABLED_SCHEMA = vol.Schema({ vol.Optional("enabled", default=True): cv.boolean })
    # Calendar services
        SERVICE_CALENDAR_REQUEST_SCHEMA = vol.Schema({ vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)) })
        SERVICE_CALENDAR_SET_SCHEMA = vol.Schema({
            vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
            vol.Required("levels"): vol.All(
                [vol.All(vol.Coerce(int), vol.Range(min=0, max=4))],
                vol.Length(min=48, max=48)
            ),
        })
        SERVICE_CALENDAR_COPY_SCHEMA = vol.Schema({
            vol.Required("source_day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
            vol.Optional("all_days", default=False): cv.boolean,
            vol.Optional("preset", default="none"): vol.In(["none", "weekday"]),
            vol.Optional("target_days", default=[]): [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
        })

        # Date/time services
        SERVICE_SET_DEVICE_DATETIME_SCHEMA = vol.Schema({
            vol.Required("year"): vol.All(vol.Coerce(int), vol.Range(min=2000, max=2255)),
            vol.Required("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
            vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
            vol.Required("hour"): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
            vol.Required("minute"): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
        })
        SERVICE_SYNC_DEVICE_TIME_SCHEMA = vol.Schema({
            vol.Optional("now", default=True): cv.boolean,
        })

        async def handle_set_auto_mode(call):
            for d in hass.data.get(DOMAIN, {}).values():
                if isinstance(d, dict) and "coordinator" in d:
                    d["coordinator"].set_auto_mode(bool(call.data.get("enabled", True)))

        async def handle_set_fan_level(call):
            lvl = int(call.data.get("level", 0))
            for d in hass.data.get(DOMAIN, {}).values():
                if isinstance(d, dict) and "coordinator" in d:
                    d["coordinator"].set_fan_level(lvl)

        async def handle_set_party_enabled(call):
            enabled = bool(call.data.get("enabled", True))
            for d in hass.data.get(DOMAIN, {}).values():
                if isinstance(d, dict) and "coordinator" in d:
                    coord = d["coordinator"]
                    if hasattr(coord, "set_party_enabled"):
                        coord.set_party_enabled(enabled)

        hass.services.async_register(DOMAIN, "set_auto_mode", handle_set_auto_mode, schema=SERVICE_SET_AUTO_MODE_SCHEMA)
        hass.services.async_register(DOMAIN, "set_fan_level", handle_set_fan_level, schema=SERVICE_SET_FAN_LEVEL_SCHEMA)
        hass.services.async_register(DOMAIN, "set_party_enabled", handle_set_party_enabled, schema=SERVICE_SET_PARTY_ENABLED_SCHEMA)

        async def handle_calendar_request(call):
            day = int(call.data.get("day"))
            for d in hass.data.get(DOMAIN, {}).values():
                if isinstance(d, dict) and "coordinator" in d:
                    d["coordinator"].request_calendar_day(day)

        async def handle_calendar_set(call):
            day = int(call.data.get("day"))
            levels = list(call.data.get("levels"))
            # Friendly validation at runtime
            if len(levels) != 48:
                raise ValueError("levels must contain exactly 48 integers (0..4)")
            bad = [v for v in levels if not isinstance(v, (int,)) or v < 0 or v > 4]
            if bad:
                raise ValueError("levels values must be integers in range 0..4")
            for d in hass.data.get(DOMAIN, {}).values():
                if isinstance(d, dict) and "coordinator" in d:
                    d["coordinator"].set_calendar_day(day, levels)

        hass.services.async_register(DOMAIN, "calendar_request_day", handle_calendar_request, schema=SERVICE_CALENDAR_REQUEST_SCHEMA)
        hass.services.async_register(DOMAIN, "calendar_set_day", handle_calendar_set, schema=SERVICE_CALENDAR_SET_SCHEMA)
        
        async def handle_calendar_copy(call):
            src = int(call.data.get("source_day"))
            all_days = bool(call.data.get("all_days", False))
            preset = str(call.data.get("preset", "none"))
            targets = list(call.data.get("target_days", []))
            if preset == "weekday":
                # Mon -> Tue..Fri
                targets = [1, 2, 3, 4]
            elif all_days:
                targets = [0, 1, 2, 3, 4, 5, 6]
            for d in hass.data.get(DOMAIN, {}).values():
                if isinstance(d, dict) and "coordinator" in d:
                    coord = d["coordinator"]
                    if hasattr(coord, "copy_calendar_day"):
                        coord.copy_calendar_day(src, targets)

        hass.services.async_register(DOMAIN, "calendar_copy_day", handle_calendar_copy, schema=SERVICE_CALENDAR_COPY_SCHEMA)

        async def handle_set_device_datetime(call):
            y = int(call.data.get("year"))
            mo = int(call.data.get("month"))
            d = int(call.data.get("day"))
            h = int(call.data.get("hour"))
            mi = int(call.data.get("minute"))
            for v in hass.data.get(DOMAIN, {}).values():
                if isinstance(v, dict) and "coordinator" in v:
                    coord = v["coordinator"]
                    if hasattr(coord, "set_device_datetime"):
                        coord.set_device_datetime(y, mo, d, h, mi)

        hass.services.async_register(DOMAIN, "set_device_datetime", handle_set_device_datetime, schema=SERVICE_SET_DEVICE_DATETIME_SCHEMA)

        async def handle_sync_device_time(call):
            # Use HA's local time for best alignment with user expectations
            import datetime as _dt
            now = _dt.datetime.now()
            y, mo, d = now.year, now.month, now.day
            h, mi = now.hour, now.minute
            for v in hass.data.get(DOMAIN, {}).values():
                if isinstance(v, dict) and "coordinator" in v:
                    coord = v["coordinator"]
                    if hasattr(coord, "set_device_datetime"):
                        coord.set_device_datetime(y, mo, d, h, mi)

        hass.services.async_register(DOMAIN, "sync_device_time", handle_sync_device_time, schema=SERVICE_SYNC_DEVICE_TIME_SCHEMA)

        # bind services.yaml so the Integration tile shows service descriptions
        try:
            services_path = os.path.join(os.path.dirname(__file__), "services.yaml")
            desc = await hass.async_add_executor_job(load_yaml, services_path)
            if isinstance(desc, dict):
                for srv, schema in desc.items():
                    async_set_service_schema(hass, DOMAIN, srv, schema)
        except Exception:  # fine if it’s missing
            pass

    _LOGGER.info("✅ Helios services ready: set_auto_mode, set_fan_level, set_party_enabled, calendar_request_day, calendar_set_day, calendar_copy_day, set_device_datetime, sync_device_time")

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
    # If no coordinator entries remain, remove the sidebar panel
    try:
        has_any_entry = False
        for v in hass.data.get(DOMAIN, {}).values():
            if isinstance(v, dict) and "coordinator" in v:
                has_any_entry = True
                break
        if not has_any_entry:
            async_remove_panel(hass, "helios-calendar")
            if DOMAIN in hass.data:
                hass.data[DOMAIN].pop("_panel_registered", None)
    except Exception:
        pass
    return unloaded
