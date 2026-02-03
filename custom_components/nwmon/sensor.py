"""Sensor platform for Network Monitor."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NetworkMonitorCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up summary sensors."""
    coordinator = entry.runtime_data

    _LOGGER.debug(
        "Setting up sensors: coordinator has %d devices, last_update_success=%s",
        len(coordinator.devices),
        coordinator.last_update_success,
    )

    async_add_entities(
        [
            DevicesOnlineSensor(coordinator, entry.entry_id),
            DevicesTotalSensor(coordinator, entry.entry_id),
            LastFullScanSensor(coordinator, entry.entry_id),
        ]
    )


class NetworkMonitorSensor(
    CoordinatorEntity[NetworkMonitorCoordinator], SensorEntity
):
    """Base class for Network Monitor sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NetworkMonitorCoordinator,
        entry_id: str,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
        }


class DevicesOnlineSensor(NetworkMonitorSensor):
    """Sensor showing number of online devices."""

    _attr_name = "Devices Online"
    _attr_icon = "mdi:devices"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "devices"

    def __init__(
        self, coordinator: NetworkMonitorCoordinator, entry_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id, "devices_online")

    @property
    def native_value(self) -> int:
        """Return the number of online devices."""
        return len(self.coordinator.online_devices)


class DevicesTotalSensor(NetworkMonitorSensor):
    """Sensor showing total number of known devices."""

    _attr_name = "Total Devices"
    _attr_icon = "mdi:lan"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "devices"

    def __init__(
        self, coordinator: NetworkMonitorCoordinator, entry_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id, "devices_total")

    @property
    def native_value(self) -> int:
        """Return the total number of known devices."""
        return len(self.coordinator.devices)


class LastFullScanSensor(NetworkMonitorSensor):
    """Sensor showing when the last full scan was performed."""

    _attr_name = "Last Full Scan"
    _attr_icon = "mdi:radar"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: NetworkMonitorCoordinator, entry_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry_id, "last_full_scan")

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last full scan."""
        return self.coordinator.last_full_scan
