"""Binary sensor platform for Network Monitor."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_FAILED_CHECKS,
    ATTR_FIRST_SEEN,
    ATTR_HOSTNAME,
    ATTR_IP_ADDRESS,
    ATTR_LAST_SEEN,
    ATTR_LATENCY,
    ATTR_MAC_ADDRESS,
    ATTR_NICKNAME,
    ATTR_VENDOR,
    ATTR_WATCHED,
    DOMAIN,
)
from .coordinator import NetworkMonitorCoordinator
from .scanner import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for discovered devices."""
    coordinator = entry.runtime_data

    # Track which entities we've created
    known_entities: set[str] = set()

    @callback
    def async_add_new_devices() -> None:
        """Add entities for newly discovered devices."""
        new_entities: list[DeviceBinarySensor] = []

        _LOGGER.debug(
            "async_add_new_devices called: %d devices in coordinator, %d known entities, last_update_success=%s",
            len(coordinator.devices),
            len(known_entities),
            coordinator.last_update_success,
        )

        for device in coordinator.devices.values():
            if device.identifier not in known_entities:
                _LOGGER.debug("Creating entity for device: %s (%s)", device.identifier, device.display_name)
                known_entities.add(device.identifier)
                new_entities.append(
                    DeviceBinarySensor(coordinator, entry.entry_id, device)
                )

        if new_entities:
            _LOGGER.info("Adding %d new device entities", len(new_entities))
            async_add_entities(new_entities)

    # Add initial devices
    async_add_new_devices()

    # Listen for coordinator updates to add new devices
    entry.async_on_unload(
        coordinator.async_add_listener(async_add_new_devices)
    )


class DeviceBinarySensor(
    CoordinatorEntity[NetworkMonitorCoordinator], BinarySensorEntity
):
    """Binary sensor representing a network device."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NetworkMonitorCoordinator,
        entry_id: str,
        device: DeviceInfo,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._device_identifier = device.identifier
        self._entry_id = entry_id

        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{device.identifier.replace(':', '')}"
        self._attr_name = "Connectivity"

        # Create a separate HA device for each network device
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"device_{device.identifier}")},
            "name": device.display_name,
            "manufacturer": device.vendor,
            "model": "Network Device",
            "via_device": (DOMAIN, entry_id),  # Link to main Network Monitor
        }
        if device.mac_address:
            self._attr_device_info["connections"] = {("mac", device.mac_address)}

    @property
    def _device(self) -> DeviceInfo | None:
        """Get the current device data from coordinator."""
        return self.coordinator.async_get_device(self._device_identifier)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._device is not None

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is online."""
        if device := self._device:
            return device.is_online
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return additional state attributes."""
        if not (device := self._device):
            return {}

        return {
            ATTR_IP_ADDRESS: device.ip_address,
            ATTR_MAC_ADDRESS: device.mac_address,
            ATTR_HOSTNAME: device.hostname,
            ATTR_VENDOR: device.vendor,
            ATTR_FIRST_SEEN: device.first_seen.isoformat(),
            ATTR_LAST_SEEN: device.last_seen.isoformat(),
            ATTR_FAILED_CHECKS: device.failed_checks,
            ATTR_LATENCY: device.last_latency_ms,
            ATTR_NICKNAME: device.nickname,
            ATTR_WATCHED: device.watched,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
