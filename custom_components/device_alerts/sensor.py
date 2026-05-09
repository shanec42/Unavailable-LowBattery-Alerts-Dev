# 2026/05/08 - Phase 8: add DeviceAlertsConfigSensor exposing ignore/override state
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeviceAlertsCoordinator

_DEVICE_INFO = {
    "identifiers": {(DOMAIN, "device_alerts")},
    "name": "Device Alerts",
    "manufacturer": "shanec42",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DeviceAlertsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        DeviceAlertsUnavailableSensor(coordinator, entry.entry_id),
        DeviceAlertsLowBatterySensor(coordinator, entry.entry_id),
        DeviceAlertsConfigSensor(coordinator, entry.entry_id),
    ])


class DeviceAlertsUnavailableSensor(CoordinatorEntity, SensorEntity):
    """Count of currently unavailable devices.

    entity_id: sensor.device_alerts_unavailable
    attributes.devices: dict of uuid → device info
    """

    _attr_has_entity_name = True
    _attr_name = "Unavailable"
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator: DeviceAlertsCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_unavailable"

    @property
    def native_value(self) -> int:
        if self.coordinator.data is None:
            return 0
        return len(self.coordinator.data.get("unavail", {}))

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {"devices": {}}
        return {"devices": self.coordinator.data.get("unavail", {})}

    @property
    def device_info(self) -> dict:
        return _DEVICE_INFO


class DeviceAlertsLowBatterySensor(CoordinatorEntity, SensorEntity):
    """Count of devices with low battery.

    entity_id: sensor.device_alerts_low_battery
    attributes.devices: dict of entity_id → battery info
    """

    _attr_has_entity_name = True
    _attr_name = "Low Battery"
    _attr_icon = "mdi:battery-alert"

    def __init__(self, coordinator: DeviceAlertsCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_low_battery"

    @property
    def native_value(self) -> int:
        if self.coordinator.data is None:
            return 0
        return len(self.coordinator.data.get("battery", {}))

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {"devices": {}}
        return {"devices": self.coordinator.data.get("battery", {})}

    @property
    def device_info(self) -> dict:
        return _DEVICE_INFO


class DeviceAlertsConfigSensor(CoordinatorEntity, SensorEntity):
    """Current ignore/override configuration exposed as sensor attributes.

    entity_id: sensor.device_alerts_config
    attributes.ignore_patterns: list of glob patterns
    attributes.ignore_uuids: list of device UUIDs
    attributes.threshold_overrides: dict of entity_id → threshold
    """

    _attr_has_entity_name = True
    _attr_name = "Config"
    _attr_icon = "mdi:cog"

    def __init__(self, coordinator: DeviceAlertsCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_config"

    @property
    def native_value(self) -> str:
        return "active"

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {"ignore_patterns": [], "ignore_uuids": [], "threshold_overrides": {}}
        cfg = self.coordinator.data.get("config", {})
        return {
            "ignore_patterns":     cfg.get("ignore_patterns", []),
            "ignore_uuids":        cfg.get("ignore_uuids", []),
            "threshold_overrides": cfg.get("threshold_overrides", {}),
        }

    @property
    def device_info(self) -> dict:
        return _DEVICE_INFO
