"""DataUpdateCoordinator for Network Monitor."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_CHECK_INTERVAL,
    CONF_FULL_SCAN_INTERVAL,
    CONF_NETWORKS,
    CONF_OFFLINE_THRESHOLD,
    CONF_PING_TIMEOUT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_FULL_SCAN_INTERVAL,
    DEFAULT_OFFLINE_THRESHOLD,
    DEFAULT_PING_TIMEOUT,
    DOMAIN,
    EVENT_DEVICE_OFFLINE,
    EVENT_DEVICE_ONLINE,
    EVENT_WATCHED_DEVICE_OFFLINE,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .scanner import DeviceInfo, NetworkScanner

_LOGGER = logging.getLogger(__name__)


class NetworkMonitorCoordinator(DataUpdateCoordinator[dict[str, DeviceInfo]]):
    """Coordinator for network monitoring with dual scan intervals."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self._entry = entry
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}"
        )

        # Get configuration
        networks = entry.data.get(CONF_NETWORKS, [])
        options = entry.options
        self._full_scan_interval = timedelta(
            minutes=options.get(CONF_FULL_SCAN_INTERVAL, DEFAULT_FULL_SCAN_INTERVAL)
        )
        self._check_interval = timedelta(
            minutes=options.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL)
        )
        self._offline_threshold = options.get(
            CONF_OFFLINE_THRESHOLD, DEFAULT_OFFLINE_THRESHOLD
        )
        ping_timeout = options.get(CONF_PING_TIMEOUT, DEFAULT_PING_TIMEOUT)

        # Initialize scanner
        self._scanner = NetworkScanner(
            networks=networks,
            ping_timeout=ping_timeout,
        )

        # Device tracking
        self._devices: dict[str, DeviceInfo] = {}
        self._last_full_scan: datetime | None = None
        self._update_count = 0
        self._needs_initial_scan = True  # Always full scan on first update after startup

        # Calculate when to do full scans (every N quick checks)
        full_scan_minutes = self._full_scan_interval.total_seconds() / 60
        check_minutes = self._check_interval.total_seconds() / 60
        self._full_scan_every = max(1, int(full_scan_minutes / check_minutes))

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self._check_interval,
        )

    @property
    def devices(self) -> dict[str, DeviceInfo]:
        """Return all known devices."""
        return self._devices

    @property
    def online_devices(self) -> list[DeviceInfo]:
        """Return online devices."""
        return [d for d in self._devices.values() if d.is_online]

    @property
    def offline_devices(self) -> list[DeviceInfo]:
        """Return offline devices."""
        return [d for d in self._devices.values() if not d.is_online]

    @property
    def last_full_scan(self) -> datetime | None:
        """Return timestamp of last full scan."""
        return self._last_full_scan

    async def async_load_devices(self) -> None:
        """Load devices from persistent storage."""
        _LOGGER.debug("Loading devices from storage")
        data = await self._store.async_load()
        _LOGGER.debug("Storage data: %s", "present" if data else "empty")
        if data and "devices" in data:
            for device_data in data["devices"]:
                try:
                    device = DeviceInfo.from_dict(device_data)
                    self._devices[device.identifier] = device
                except (KeyError, ValueError) as err:
                    _LOGGER.warning("Failed to load device: %s", err)

            if "last_full_scan" in data and data["last_full_scan"]:
                try:
                    loaded_dt = datetime.fromisoformat(data["last_full_scan"])
                    # Ensure timezone awareness for timestamp sensor
                    if loaded_dt.tzinfo is None:
                        loaded_dt = loaded_dt.replace(tzinfo=timezone.utc)
                    self._last_full_scan = loaded_dt
                except ValueError:
                    pass

            _LOGGER.info("Loaded %d devices from storage", len(self._devices))

    def _build_event_data(self, device: DeviceInfo) -> dict[str, Any]:
        """Build event data dictionary for a device."""
        identifier_clean = device.identifier.replace(":", "").replace(".", "_")
        entity_id = f"binary_sensor.{DOMAIN}_{identifier_clean}"

        return {
            "device_id": device.identifier,
            "ip_address": device.ip_address,
            "mac_address": device.mac_address,
            "hostname": device.hostname,
            "vendor": device.vendor,
            "display_name": device.display_name,
            "first_seen": device.first_seen.isoformat(),
            "last_seen": device.last_seen.isoformat(),
            "entity_id": entity_id,
            "latency_ms": device.last_latency_ms,
            "nickname": device.nickname,
            "watched": device.watched,
        }

    def _fire_state_change_event(self, device: DeviceInfo, event_type: str) -> None:
        """Fire an event for device state change."""
        event_data = self._build_event_data(device)
        self.hass.bus.async_fire(event_type, event_data)
        _LOGGER.debug("Fired event %s for device %s", event_type, device.display_name)

        if device.watched and event_type == EVENT_DEVICE_OFFLINE:
            self.hass.bus.async_fire(EVENT_WATCHED_DEVICE_OFFLINE, event_data)

    async def _async_save_devices(self) -> None:
        """Save devices to persistent storage."""
        # Deduplicate devices (same device may be stored under both IP and MAC keys)
        unique_devices = {id(d): d for d in self._devices.values()}
        data = {
            "devices": [d.to_dict() for d in unique_devices.values()],
            "last_full_scan": (
                self._last_full_scan.isoformat() if self._last_full_scan else None
            ),
        }
        await self._store.async_save(data)

    def _should_full_scan(self) -> bool:
        """Determine if we should do a full scan."""
        # Always full scan on first update after startup
        if self._needs_initial_scan:
            return True

        # Full scan every N updates
        return self._update_count % self._full_scan_every == 0

    async def _async_update_data(self) -> dict[str, DeviceInfo]:
        """Fetch data from network."""
        self._update_count += 1
        _LOGGER.debug(
            "Update #%d starting (devices: %d, full_scan: %s)",
            self._update_count,
            len(self._devices),
            self._should_full_scan(),
        )

        try:
            if self._should_full_scan():
                await self._do_full_scan()
            else:
                await self._do_quick_check()

            # Save to persistent storage
            await self._async_save_devices()

            _LOGGER.debug(
                "Update #%d complete (devices: %d, online: %d)",
                self._update_count,
                len(self._devices),
                len(self.online_devices),
            )
            return self._devices
        except Exception as err:
            _LOGGER.error("Update #%d failed: %s", self._update_count, err, exc_info=True)
            raise

    async def _do_full_scan(self) -> None:
        """Perform a full network scan."""
        _LOGGER.info("Performing full network scan")
        self._last_full_scan = datetime.now(timezone.utc)
        self._needs_initial_scan = False

        discovered = await self._scanner.full_scan()

        # Track which devices were found in this scan
        found_identifiers: set[str] = set()
        devices_needing_hostname: list[DeviceInfo] = []

        for device in discovered:
            identifier = device.identifier
            found_identifiers.add(identifier)

            # Check if we have an existing device - by MAC, or by IP if no MAC match
            existing = self._devices.get(identifier)
            if not existing and device.mac_address:
                # Check if we have this device stored by IP (before MAC was known)
                ip_entry = self._devices.get(device.ip_address)
                if ip_entry and ip_entry.mac_address is None:
                    existing = ip_entry
                    _LOGGER.info(
                        "Device %s now has MAC address: %s",
                        device.ip_address,
                        device.mac_address,
                    )
                    found_identifiers.add(device.ip_address)  # Don't mark old IP as not responding

            if existing:
                # Track if device was offline before this update
                was_offline = not existing.is_online
                # Update existing device
                existing.ip_address = device.ip_address
                existing.mac_address = device.mac_address or existing.mac_address
                existing.hostname = device.hostname or existing.hostname
                existing.vendor = device.vendor or existing.vendor
                existing.last_seen = device.last_seen
                existing.is_online = True
                existing.failed_checks = 0
                existing.last_latency_ms = device.last_latency_ms
                # Ensure device is accessible by current identifier (MAC if known)
                self._devices[existing.identifier] = existing
                # Fire online event if device came back online
                if was_offline:
                    _LOGGER.info(
                        "Device came back online: %s (%s)",
                        existing.display_name,
                        existing.ip_address,
                    )
                    self._fire_state_change_event(existing, EVENT_DEVICE_ONLINE)
                # Try to resolve hostname if still missing
                if not existing.hostname:
                    devices_needing_hostname.append(existing)
            else:
                # New device
                self._devices[identifier] = device
                _LOGGER.info(
                    "Discovered new device: %s (%s)",
                    device.display_name,
                    device.ip_address,
                )

        # Update devices not found in scan
        for identifier, device in self._devices.items():
            if identifier not in found_identifiers:
                self._handle_device_not_responding(device)

        # Retry hostname resolution for devices without hostnames
        if devices_needing_hostname:
            _LOGGER.debug(
                "Retrying hostname resolution for %d devices",
                len(devices_needing_hostname),
            )
            for device in devices_needing_hostname:
                hostname = await self._scanner._resolve_hostname(device.ip_address)
                if hostname:
                    device.hostname = hostname
                    _LOGGER.info(
                        "Resolved hostname for %s: %s",
                        device.ip_address,
                        hostname,
                    )

    async def _do_quick_check(self) -> None:
        """Perform a quick check of known online devices."""
        # Only check devices that are currently online
        devices_to_check = self.online_devices
        if not devices_to_check:
            _LOGGER.debug("No online devices to check")
            return

        _LOGGER.debug("Quick check of %d online devices", len(devices_to_check))

        results = await self._scanner.check_devices(devices_to_check)

        now = datetime.now(timezone.utc)
        for device in devices_to_check:
            result = results.get(device.identifier, (False, None))
            is_online, latency = result
            if is_online:
                device.last_seen = now
                device.failed_checks = 0
                device.last_latency_ms = latency
            else:
                self._handle_device_not_responding(device)

    def _handle_device_not_responding(self, device: DeviceInfo) -> None:
        """Handle a device that didn't respond to ping."""
        device.failed_checks += 1

        if device.failed_checks >= self._offline_threshold:
            if device.is_online:
                device.is_online = False
                device.last_latency_ms = None
                _LOGGER.info(
                    "Device went offline: %s (%s)",
                    device.display_name,
                    device.ip_address,
                )
                # Fire offline event
                self._fire_state_change_event(device, EVENT_DEVICE_OFFLINE)
        else:
            _LOGGER.debug(
                "Device %s not responding (%d/%d)",
                device.display_name,
                device.failed_checks,
                self._offline_threshold,
            )

    @callback
    def async_get_device(self, identifier: str) -> DeviceInfo | None:
        """Get a device by identifier."""
        return self._devices.get(identifier)

    @callback
    def resolve_device_id(self, device_id: str) -> str | None:
        """Resolve a user-provided device_id to a known device key.

        Tries exact match first, then matches by MAC or IP on each device.
        Accepts formats with or without colons/dots (e.g. aabbccddeeff).
        """
        # Exact match on dict key
        if device_id in self._devices:
            return device_id

        # Normalize: lowercase, strip colons/dashes/dots
        normalized = device_id.lower().replace(":", "").replace("-", "").replace(".", "")

        for key, device in self._devices.items():
            if device.mac_address:
                mac_clean = device.mac_address.lower().replace(":", "").replace("-", "")
                if normalized == mac_clean:
                    return key
            ip_clean = device.ip_address.replace(".", "")
            if normalized == ip_clean or device_id == device.ip_address:
                return key

        return None

    async def async_forget_device(self, identifier: str) -> bool:
        """Remove a device from tracking."""
        if identifier in self._devices:
            device = self._devices.pop(identifier)
            _LOGGER.info("Forgot device: %s", device.display_name)
            await self._async_save_devices()
            return True
        return False

    async def async_configure_device(
        self,
        identifier: str,
        nickname: str | None = None,
        watched: bool | None = None,
    ) -> bool:
        """Configure a device's nickname and/or watched status."""
        device = self._devices.get(identifier)
        if device is None:
            return False

        if nickname is not None:
            # Empty string clears the nickname
            device.nickname = nickname if nickname else None
        if watched is not None:
            device.watched = watched

        await self._async_save_devices()
        self.async_set_updated_data(self._devices)
        return True

    async def async_trigger_full_scan(self) -> None:
        """Trigger an immediate full scan."""
        await self._do_full_scan()
        await self._async_save_devices()
        self.async_set_updated_data(self._devices)
