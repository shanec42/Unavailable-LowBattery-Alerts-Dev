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
    "name": "Unavailable & Low Battery Alerts",
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
    ])


class DeviceAlertsUnavailableSensor(CoordinatorEntity, SensorEntity):
    """Sensor reporting count of currently unavailable devices.

    entity_id: sensor.device_alerts_unavailable
    attributes.devices: dict of uuid → device info
    """

    _attr_icon = "mdi:alert-circle"
    _attr_name = "Device Alerts Unavailable"

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
    """Sensor reporting count of devices with low battery.

    entity_id: sensor.device_alerts_low_battery
    attributes.devices: dict of entity_id → battery info
    """

    _attr_icon = "mdi:battery-alert"
    _attr_name = "Device Alerts Low Battery"

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
