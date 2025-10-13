# options_flow.py
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT


class HeliosOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Helios EC-Pro integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values from options (if set) or fall back to data
        current_host = self.config_entry.options.get(
            "host", self.config_entry.data.get("host", DEFAULT_HOST)
        )
        current_port = self.config_entry.options.get(
            "port", self.config_entry.data.get("port", DEFAULT_PORT)
        )

        schema = vol.Schema({
            vol.Required("host", default=current_host): str,
            vol.Required("port", default=current_port): int,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
