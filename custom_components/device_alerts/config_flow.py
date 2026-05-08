from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_NOTIFY_FIELDS = vol.Schema({
    vol.Optional("mobile_services", default=""): str,
    vol.Optional("smtp_service",    default=""): str,
    vol.Optional("smtp_targets",    default=""): str,
    vol.Optional("gate_entity",     default=""): str,
})


class DeviceAlertsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            return self.async_create_entry(
                title="Unavailable & Low Battery Alerts",
                data=user_input,
            )

        return self.async_show_form(step_id="user", data_schema=_NOTIFY_FIELDS)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DeviceAlertsOptionsFlow(config_entry)


class DeviceAlertsOptionsFlow(OptionsFlow):

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("mobile_services", default=current.get("mobile_services", "")): str,
                vol.Optional("smtp_service",    default=current.get("smtp_service",    "")): str,
                vol.Optional("smtp_targets",    default=current.get("smtp_targets",    "")): str,
                vol.Optional("gate_entity",     default=current.get("gate_entity",     "")): str,
            }),
        )
