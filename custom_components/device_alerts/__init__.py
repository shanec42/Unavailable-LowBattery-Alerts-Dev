from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, PLATFORMS
from .coordinator import DeviceAlertsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = DeviceAlertsCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Pre-populate notify helpers from config entry if they are empty
    await _prepopulate_helpers(hass, entry.data)

    # Register services (only on first entry — services are domain-global)
    if not hass.services.has_service(DOMAIN, "run_check"):
        _register_services(hass, coordinator)

    # Z-Wave dead node listener
    @callback
    def _zwave_listener(event) -> None:
        entity_id = event.data.get("entity_id", "")
        new_state = event.data.get("new_state")
        if (entity_id.endswith("_node_status")
                and new_state is not None
                and new_state.state == "dead"):
            hass.async_create_task(
                coordinator.async_handle_zwave_dead(entity_id, new_state)
            )

    entry.async_on_unload(hass.bus.async_listen("state_changed", _zwave_listener))

    # Delayed first run — wait 60 s for HA to finish booting
    @callback
    def _startup_callback(_now=None) -> None:
        hass.async_create_task(coordinator.async_refresh())

    entry.async_on_unload(async_call_later(hass, 60, _startup_callback))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # Remove services only when last entry is gone
        if not hass.data.get(DOMAIN):
            for svc in ("run_check", "add_snooze", "clear_snooze",
                        "quick_snooze", "quick_ignore", "set_battery_threshold"):
                hass.services.async_remove(DOMAIN, svc)
    return unload_ok


# ---- Helpers -----------------------------------------------------------------

async def _prepopulate_helpers(hass: HomeAssistant, config: dict) -> None:
    """Set notify input_text helpers from config entry data if they are currently empty."""
    mapping = {
        "input_text.device_alerts_notify_mobile_services": config.get("mobile_services", ""),
        "input_text.device_alerts_notify_gate_entity":     config.get("gate_entity", ""),
        "input_text.device_alerts_smtp_service":           config.get("smtp_service", ""),
        "input_text.device_alerts_smtp_targets":           config.get("smtp_targets", ""),
    }
    for entity_id, value in mapping.items():
        if not value:
            continue
        state = hass.states.get(entity_id)
        if state is None or state.state not in ("", "unknown"):
            continue
        try:
            await hass.services.async_call(
                "input_text", "set_value",
                {"entity_id": entity_id, "value": value},
                blocking=True,
            )
        except Exception:  # noqa: BLE001
            pass


def _register_services(hass: HomeAssistant, coordinator: DeviceAlertsCoordinator) -> None:

    async def handle_run_check(call: ServiceCall) -> None:
        await coordinator.async_refresh()

    async def handle_add_snooze(call: ServiceCall) -> None:
        await coordinator.async_add_snooze()

    async def handle_clear_snooze(call: ServiceCall) -> None:
        await coordinator.async_clear_snooze()

    async def handle_quick_snooze(call: ServiceCall) -> None:
        await coordinator.async_quick_snooze(
            uuid=call.data.get("uuid"),
            days=call.data.get("days", 7),
        )

    async def handle_quick_ignore(call: ServiceCall) -> None:
        await coordinator.async_quick_ignore(uuid=call.data.get("uuid"))

    async def handle_set_battery_threshold(call: ServiceCall) -> None:
        await coordinator.async_set_battery_threshold(
            entity_id=call.data.get("entity_id"),
            threshold=call.data.get("threshold"),
        )

    hass.services.async_register(DOMAIN, "run_check", handle_run_check)
    hass.services.async_register(DOMAIN, "add_snooze", handle_add_snooze)
    hass.services.async_register(DOMAIN, "clear_snooze", handle_clear_snooze)
    hass.services.async_register(
        DOMAIN, "quick_snooze", handle_quick_snooze,
        schema=vol.Schema({
            vol.Required("uuid"): cv.string,
            vol.Optional("days", default=7): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=365)
            ),
        }),
    )
    hass.services.async_register(
        DOMAIN, "quick_ignore", handle_quick_ignore,
        schema=vol.Schema({vol.Required("uuid"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN, "set_battery_threshold", handle_set_battery_threshold,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.entity_id,
            vol.Required("threshold"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=100)
            ),
        }),
    )
