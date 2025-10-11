import sys
import types

# Stub out Home Assistant modules so importing the integration doesn't fail during tests
ha = types.ModuleType("homeassistant")
ha.__path__ = []  # mark as package so submodule imports work

# homeassistant.core
core = types.ModuleType("homeassistant.core")
class HomeAssistant:  # minimal placeholder
    def __init__(self):
        self.data = {}
        class Loop:
            def call_soon_threadsafe(self, cb, *a, **kw):
                try:
                    cb(*a, **kw)
                except Exception:
                    pass
        self.loop = Loop()
core.HomeAssistant = HomeAssistant

# homeassistant.config_entries
cfg = types.ModuleType("homeassistant.config_entries")
class ConfigEntry:  # minimal placeholder
    def __init__(self, data=None, entry_id="test", source="user"):
        self.data = data or {}
        self.entry_id = entry_id
        self.source = source
cfg.ConfigEntry = ConfigEntry
cfg.SOURCE_IMPORT = "import"

# homeassistant.const
const = types.ModuleType("homeassistant.const")
class Platform:
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    CLIMATE = "climate"
    SWITCH = "switch"
    FAN = "fan"
    SELECT = "select"
const.Platform = Platform

# homeassistant.helpers.config_validation
helpers = types.ModuleType("homeassistant.helpers")
cv = types.ModuleType("homeassistant.helpers.config_validation")
cv.boolean = object()
helpers.config_validation = cv

# homeassistant.helpers.service
srv = types.ModuleType("homeassistant.helpers.service")
async def async_set_service_schema(*args, **kwargs):
    return None
srv.async_set_service_schema = async_set_service_schema
helpers.service = srv

# homeassistant.util.yaml
util = types.ModuleType("homeassistant.util")
util.__path__ = []
yaml_mod = types.ModuleType("homeassistant.util.yaml")
def load_yaml(path):
    return {}
yaml_mod.load_yaml = load_yaml

# homeassistant.components.switch
components_pkg = types.ModuleType("homeassistant.components")
components_pkg.__path__ = []  # mark as namespace/package
sys.modules.setdefault("homeassistant.components", components_pkg)
comp_switch = types.ModuleType("homeassistant.components.switch")
class SwitchEntity:
    def __init__(self):
        self.hass = HomeAssistant()
    def async_write_ha_state(self):
        return None
comp_switch.SwitchEntity = SwitchEntity

# register modules
sys.modules.setdefault("homeassistant", ha)
sys.modules.setdefault("homeassistant.core", core)
sys.modules.setdefault("homeassistant.config_entries", cfg)
sys.modules.setdefault("homeassistant.const", const)
sys.modules.setdefault("homeassistant.helpers", helpers)
sys.modules.setdefault("homeassistant.helpers.config_validation", cv)
sys.modules.setdefault("homeassistant.helpers.service", srv)
sys.modules.setdefault("homeassistant.util", util)
sys.modules.setdefault("homeassistant.util.yaml", yaml_mod)
sys.modules.setdefault("homeassistant.components.switch", comp_switch)

# Stub out voluptuous used by __init__ services
vol = types.ModuleType("voluptuous")
class _Schema:
    def __init__(self, *a, **kw):
        pass
    def __call__(self, *a, **kw):
        return None

def _identity(*a, **kw):
    return _identity

vol.Schema = _Schema
vol.Optional = _identity
vol.Required = _identity
vol.All = _identity
vol.Coerce = _identity
vol.Range = _identity

sys.modules.setdefault("voluptuous", vol)

# Stub out homeassistant.components.http for HomeAssistantView
sys.modules.setdefault("homeassistant.components", components_pkg)
comp_http = types.ModuleType("homeassistant.components.http")
class HomeAssistantView:  # minimal base
    url = "/"
    name = "test"
    requires_auth = False
    async def get(self, request):
        return None
comp_http.HomeAssistantView = HomeAssistantView
sys.modules.setdefault("homeassistant.components.http", comp_http)

# Stub out aiohttp.web Response used by __init__
aiohttp = types.ModuleType("aiohttp")
web = types.ModuleType("aiohttp.web")
class Response:
    def __init__(self, body=b"", content_type="application/octet-stream"):
        self.body = body
        self.content_type = content_type
web.Response = Response
aiohttp.web = web
sys.modules.setdefault("aiohttp", aiohttp)
sys.modules.setdefault("aiohttp.web", web)
