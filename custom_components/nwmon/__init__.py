"""Network Monitor integration for Home Assistant."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_DEVICE_ID,
    ATTR_NICKNAME,
    ATTR_WATCHED,
    DOMAIN,
    PLATFORMS,
    SERVICE_CONFIGURE_DEVICE,
    SERVICE_FORGET_DEVICE,
    SERVICE_FULL_SCAN,
)
from .coordinator import NetworkMonitorCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_FULL_SCAN_SCHEMA = vol.Schema({})
SERVICE_FORGET_DEVICE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): str}
)
SERVICE_CONFIGURE_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): str,
        vol.Optional(ATTR_NICKNAME): str,
        vol.Optional(ATTR_WATCHED): bool,
    }
)


def _get_coordinators(hass: HomeAssistant) -> list[NetworkMonitorCoordinator]:
    """Get all active coordinators."""
    coordinators: list[NetworkMonitorCoordinator] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if hasattr(entry, "runtime_data") and entry.runtime_data:
            coordinators.append(entry.runtime_data)
    return coordinators


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Network Monitor from a config entry."""
    _LOGGER.debug("Setting up Network Monitor integration")
    coordinator = NetworkMonitorCoordinator(hass, entry)

    # Load stored device data
    await coordinator.async_load_devices()
    _LOGGER.debug("After load: %d devices", len(coordinator.devices))

    # Perform initial refresh
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug(
        "After first refresh: %d devices, last_update_success=%s",
        len(coordinator.devices),
        coordinator.last_update_success,
    )

    # Store coordinator in runtime data
    entry.runtime_data = coordinator

    # Register the integration device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Network Monitor",
        manufacturer="nwmon",
        model="Network Scanner",
    )

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Register services (only once per domain)
    if not hass.services.has_service(DOMAIN, SERVICE_FULL_SCAN):

        async def handle_full_scan(call: ServiceCall) -> None:
            """Handle full_scan service call."""
            for coord in _get_coordinators(hass):
                await coord.async_trigger_full_scan()

        async def handle_forget_device(call: ServiceCall) -> None:
            """Handle forget_device service call."""
            device_id = call.data[ATTR_DEVICE_ID]
            for coord in _get_coordinators(hass):
                if await coord.async_forget_device(device_id):
                    return

        async def handle_configure_device(call: ServiceCall) -> None:
            """Handle configure_device service call."""
            device_id = call.data[ATTR_DEVICE_ID]
            nickname = call.data.get(ATTR_NICKNAME)
            watched = call.data.get(ATTR_WATCHED)
            for coord in _get_coordinators(hass):
                if await coord.async_configure_device(
                    device_id, nickname=nickname, watched=watched
                ):
                    return

        hass.services.async_register(
            DOMAIN, SERVICE_FULL_SCAN, handle_full_scan, SERVICE_FULL_SCAN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_FORGET_DEVICE,
            handle_forget_device,
            SERVICE_FORGET_DEVICE_SCHEMA,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_CONFIGURE_DEVICE,
            handle_configure_device,
            SERVICE_CONFIGURE_DEVICE_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove services if this is the last config entry
    if unload_ok:
        remaining = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id
        ]
        if not remaining:
            hass.services.async_remove(DOMAIN, SERVICE_FULL_SCAN)
            hass.services.async_remove(DOMAIN, SERVICE_FORGET_DEVICE)
            hass.services.async_remove(DOMAIN, SERVICE_CONFIGURE_DEVICE)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
