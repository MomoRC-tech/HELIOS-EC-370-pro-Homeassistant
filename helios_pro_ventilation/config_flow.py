# config_flow.py
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT

class HeliosConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Helios EC-Pro Ventilation", data=user_input)

        schema = vol.Schema({
            vol.Required("host", default=DEFAULT_HOST): str,
            vol.Required("port", default=DEFAULT_PORT): int,
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_import(self, data) -> FlowResult:
        # Merge/replace any existing import entry
        existing = next((e for e in self._async_current_entries() if e.source == config_entries.SOURCE_IMPORT), None)
        if existing:
            return self.async_update_entry(existing, data=data)
        return self.async_create_entry(title="Helios EC-Pro Ventilation", data=data)
