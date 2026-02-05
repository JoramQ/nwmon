"""Tests for the three new nwmon features: services, latency, nicknames/watched."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.nwmon.scanner import DeviceInfo, NetworkScanner
from custom_components.nwmon.const import (
    ATTR_DEVICE_ID,
    ATTR_LATENCY,
    ATTR_NICKNAME,
    ATTR_WATCHED,
    DOMAIN,
    EVENT_DEVICE_OFFLINE,
    EVENT_WATCHED_DEVICE_OFFLINE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(
    ip: str = "192.168.1.10",
    mac: str | None = "aa:bb:cc:dd:ee:ff",
    hostname: str | None = "myhost",
    latency: float | None = 1.23,
    nickname: str | None = None,
    watched: bool = False,
    is_online: bool = True,
) -> DeviceInfo:
    now = datetime.now(timezone.utc)
    return DeviceInfo(
        ip_address=ip,
        mac_address=mac,
        hostname=hostname,
        is_online=is_online,
        first_seen=now,
        last_seen=now,
        last_latency_ms=latency,
        nickname=nickname,
        watched=watched,
    )


# ===================================================================
# Feature 1 — DeviceInfo: nickname, watched, latency fields
# ===================================================================


class TestDeviceInfoFields:
    """Test the new DeviceInfo dataclass fields."""

    def test_defaults(self):
        d = DeviceInfo(ip_address="10.0.0.1")
        assert d.last_latency_ms is None
        assert d.nickname is None
        assert d.watched is False

    def test_display_name_prefers_nickname(self):
        d = _make_device(nickname="My Server", hostname="server01")
        assert d.display_name == "My Server"

    def test_display_name_falls_back_to_hostname(self):
        d = _make_device(nickname=None, hostname="server01")
        assert d.display_name == "server01"

    def test_display_name_falls_back_to_mac(self):
        d = _make_device(nickname=None, hostname=None, mac="aa:bb:cc:dd:ee:ff")
        assert d.display_name == "aabbccddeeff"

    def test_display_name_falls_back_to_ip(self):
        d = _make_device(nickname=None, hostname=None, mac=None, ip="10.0.0.1")
        assert d.display_name == "10_0_0_1"


class TestDeviceInfoSerialization:
    """Test to_dict / from_dict round-trip for new fields."""

    def test_round_trip_with_new_fields(self):
        original = _make_device(latency=4.56, nickname="NAS", watched=True)
        data = original.to_dict()

        assert data["last_latency_ms"] == 4.56
        assert data["nickname"] == "NAS"
        assert data["watched"] is True

        restored = DeviceInfo.from_dict(data)
        assert restored.last_latency_ms == 4.56
        assert restored.nickname == "NAS"
        assert restored.watched is True

    def test_from_dict_backward_compat(self):
        """Old storage without new fields should load with safe defaults."""
        old_data = {
            "ip_address": "10.0.0.1",
            "mac_address": None,
            "hostname": None,
            "vendor": None,
            "is_online": True,
            "first_seen": "2025-01-01T00:00:00+00:00",
            "last_seen": "2025-01-01T00:00:00+00:00",
            "failed_checks": 0,
        }
        d = DeviceInfo.from_dict(old_data)
        assert d.last_latency_ms is None
        assert d.nickname is None
        assert d.watched is False


# ===================================================================
# Feature 2 — Ping latency capture
# ===================================================================


class TestPingLatency:
    """Test that _ping_host returns latency and it propagates."""

    @pytest.mark.asyncio
    async def test_ping_host_returns_latency_tuple(self):
        scanner = NetworkScanner(networks=["192.168.1.0/24"])

        mock_result = MagicMock()
        mock_result.is_alive = True
        mock_result.avg_rtt = 3.456

        with patch(
            "custom_components.nwmon.scanner.async_ping",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            alive, latency = await scanner._ping_host("192.168.1.1")

        assert alive is True
        assert latency == 3.46  # rounded to 2 decimals

    @pytest.mark.asyncio
    async def test_ping_host_offline_returns_none_latency(self):
        scanner = NetworkScanner(networks=["192.168.1.0/24"])

        mock_result = MagicMock()
        mock_result.is_alive = False

        with patch(
            "custom_components.nwmon.scanner.async_ping",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            alive, latency = await scanner._ping_host("192.168.1.1")

        assert alive is False
        assert latency is None

    @pytest.mark.asyncio
    async def test_ping_host_exception_returns_false_none(self):
        scanner = NetworkScanner(networks=["192.168.1.0/24"])

        with patch(
            "custom_components.nwmon.scanner.async_ping",
            new_callable=AsyncMock,
            side_effect=Exception("boom"),
        ):
            alive, latency = await scanner._ping_host("192.168.1.1")

        assert alive is False
        assert latency is None

    @pytest.mark.asyncio
    async def test_check_devices_returns_latency_tuples(self):
        scanner = NetworkScanner(networks=["192.168.1.0/24"])
        device = _make_device(ip="192.168.1.10", mac="aa:bb:cc:dd:ee:ff")

        mock_result = MagicMock()
        mock_result.is_alive = True
        mock_result.avg_rtt = 2.5

        with patch(
            "custom_components.nwmon.scanner.async_ping",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            status = await scanner.check_devices([device])

        identifier = device.identifier
        assert identifier in status
        is_online, latency = status[identifier]
        assert is_online is True
        assert latency == 2.5


# ===================================================================
# Feature 3 — Nicknames, watched status, watched event
# ===================================================================


class TestConfigureDevice:
    """Test the coordinator's async_configure_device method."""

    def _make_coordinator_stub(self, devices: dict[str, DeviceInfo]):
        """Create a minimal coordinator-like object for unit testing."""
        coord = MagicMock()
        coord._devices = devices
        coord._async_save_devices = AsyncMock()
        coord.async_set_updated_data = MagicMock()

        # Bind the real method
        from custom_components.nwmon.coordinator import NetworkMonitorCoordinator
        coord.async_configure_device = (
            NetworkMonitorCoordinator.async_configure_device.__get__(coord)
        )
        return coord

    @pytest.mark.asyncio
    async def test_set_nickname(self):
        device = _make_device()
        coord = self._make_coordinator_stub({device.identifier: device})

        result = await coord.async_configure_device(device.identifier, nickname="NAS")
        assert result is True
        assert device.nickname == "NAS"
        assert device.display_name == "NAS"
        coord._async_save_devices.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_nickname_with_empty_string(self):
        device = _make_device(nickname="OldName")
        coord = self._make_coordinator_stub({device.identifier: device})

        result = await coord.async_configure_device(device.identifier, nickname="")
        assert result is True
        assert device.nickname is None

    @pytest.mark.asyncio
    async def test_set_watched(self):
        device = _make_device(watched=False)
        coord = self._make_coordinator_stub({device.identifier: device})

        result = await coord.async_configure_device(device.identifier, watched=True)
        assert result is True
        assert device.watched is True

    @pytest.mark.asyncio
    async def test_unknown_device_returns_false(self):
        coord = self._make_coordinator_stub({})
        result = await coord.async_configure_device("nonexistent", nickname="X")
        assert result is False


class TestWatchedEvent:
    """Test that watched devices fire the extra offline event."""

    def test_watched_device_fires_extra_event(self):
        from custom_components.nwmon.coordinator import NetworkMonitorCoordinator

        device = _make_device(watched=True, is_online=False)

        coord = MagicMock(spec=NetworkMonitorCoordinator)
        coord.hass = MagicMock()
        coord.hass.bus = MagicMock()

        # Call the real _fire_state_change_event
        NetworkMonitorCoordinator._fire_state_change_event(coord, device, EVENT_DEVICE_OFFLINE)

        calls = coord.hass.bus.async_fire.call_args_list
        event_types = [c[0][0] for c in calls]

        assert EVENT_DEVICE_OFFLINE in event_types
        assert EVENT_WATCHED_DEVICE_OFFLINE in event_types

    def test_unwatched_device_does_not_fire_extra_event(self):
        from custom_components.nwmon.coordinator import NetworkMonitorCoordinator

        device = _make_device(watched=False, is_online=False)

        coord = MagicMock(spec=NetworkMonitorCoordinator)
        coord.hass = MagicMock()
        coord.hass.bus = MagicMock()

        NetworkMonitorCoordinator._fire_state_change_event(coord, device, EVENT_DEVICE_OFFLINE)

        calls = coord.hass.bus.async_fire.call_args_list
        event_types = [c[0][0] for c in calls]

        assert EVENT_DEVICE_OFFLINE in event_types
        assert EVENT_WATCHED_DEVICE_OFFLINE not in event_types

    def test_watched_device_online_does_not_fire_watched_event(self):
        from custom_components.nwmon.coordinator import NetworkMonitorCoordinator
        from custom_components.nwmon.const import EVENT_DEVICE_ONLINE

        device = _make_device(watched=True, is_online=True)

        coord = MagicMock(spec=NetworkMonitorCoordinator)
        coord.hass = MagicMock()
        coord.hass.bus = MagicMock()

        NetworkMonitorCoordinator._fire_state_change_event(coord, device, EVENT_DEVICE_ONLINE)

        calls = coord.hass.bus.async_fire.call_args_list
        event_types = [c[0][0] for c in calls]

        assert EVENT_DEVICE_ONLINE in event_types
        assert EVENT_WATCHED_DEVICE_OFFLINE not in event_types


class TestLatencyClearedOnOffline:
    """Test that latency is set to None when device goes offline."""

    def test_handle_device_not_responding_clears_latency(self):
        from custom_components.nwmon.coordinator import NetworkMonitorCoordinator

        device = _make_device(latency=5.0, is_online=True)
        device.failed_checks = 2  # one below threshold

        coord = MagicMock(spec=NetworkMonitorCoordinator)
        coord._offline_threshold = 3
        coord.hass = MagicMock()
        coord.hass.bus = MagicMock()

        NetworkMonitorCoordinator._handle_device_not_responding(coord, device)

        assert device.is_online is False
        assert device.last_latency_ms is None
