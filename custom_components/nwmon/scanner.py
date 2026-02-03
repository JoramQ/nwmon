"""Network scanner for discovering and checking devices."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from icmplib import NameLookupError, async_ping

if TYPE_CHECKING:
    from mac_vendor_lookup import AsyncMacLookup

_LOGGER = logging.getLogger(__name__)

# Regex for MAC address validation
MAC_REGEX = re.compile(r"^([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})$")


@dataclass
class DeviceInfo:
    """Information about a discovered device."""

    ip_address: str
    mac_address: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    is_online: bool = True
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    failed_checks: int = 0

    @property
    def identifier(self) -> str:
        """Return unique identifier for this device."""
        return self.mac_address or self.ip_address

    @property
    def display_name(self) -> str:
        """Return display name for this device."""
        if self.hostname:
            return self.hostname
        if self.mac_address:
            return self.mac_address.replace(":", "").lower()
        return self.ip_address.replace(".", "_")

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "hostname": self.hostname,
            "vendor": self.vendor,
            "is_online": self.is_online,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "failed_checks": self.failed_checks,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeviceInfo:
        """Create from dictionary."""
        first_seen = datetime.fromisoformat(data["first_seen"])
        last_seen = datetime.fromisoformat(data["last_seen"])
        # Ensure timezone awareness for datetimes loaded from old storage
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return cls(
            ip_address=data["ip_address"],
            mac_address=data.get("mac_address"),
            hostname=data.get("hostname"),
            vendor=data.get("vendor"),
            is_online=data.get("is_online", True),
            first_seen=first_seen,
            last_seen=last_seen,
            failed_checks=data.get("failed_checks", 0),
        )


class NetworkScanner:
    """Async network scanner using ICMP ping."""

    def __init__(
        self,
        networks: list[str],
        ping_timeout: float = 1.0,
        ping_count: int = 1,
        max_concurrent: int = 50,
    ) -> None:
        """Initialize the scanner."""
        self._networks = networks
        self._ping_timeout = ping_timeout
        self._ping_count = ping_count
        self._max_concurrent = max_concurrent
        self._mac_lookup: AsyncMacLookup | None = None
        self._arp_cache: dict[str, str] = {}

    async def _get_mac_lookup(self) -> AsyncMacLookup | None:
        """Get or create MAC lookup instance."""
        if self._mac_lookup is None:
            try:
                from mac_vendor_lookup import AsyncMacLookup

                self._mac_lookup = AsyncMacLookup()
                # Load the database
                await self._mac_lookup.load_vendors()
            except Exception as err:
                _LOGGER.warning("Failed to initialize MAC lookup: %s", err)
        return self._mac_lookup

    def _expand_networks(self) -> list[str]:
        """Expand CIDR networks to list of IP addresses."""
        ips: list[str] = []
        for network_str in self._networks:
            try:
                network = ipaddress.ip_network(network_str, strict=False)
                # Skip network and broadcast addresses for /24 and larger
                if network.prefixlen <= 30:
                    ips.extend(str(ip) for ip in network.hosts())
                else:
                    ips.extend(str(ip) for ip in network)
            except ValueError as err:
                _LOGGER.error("Invalid network %s: %s", network_str, err)
        return ips

    async def _refresh_arp_cache(self) -> None:
        """Refresh the ARP cache from system."""
        self._arp_cache = {}

        # Try Linux ARP cache first
        arp_path = Path("/proc/net/arp")
        if arp_path.exists():
            try:
                content = await asyncio.to_thread(arp_path.read_text)
                for line in content.splitlines()[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 4:
                        ip = parts[0]
                        mac = parts[3]
                        if mac != "00:00:00:00:00:00" and MAC_REGEX.match(mac):
                            self._arp_cache[ip] = mac.lower()
            except OSError as err:
                _LOGGER.debug("Failed to read ARP cache: %s", err)
            return

        # Fallback: try arp command
        try:
            proc = await asyncio.create_subprocess_exec(
                "arp",
                "-an",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode().splitlines():
                # Parse: ? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0
                match = re.search(
                    r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)", line
                )
                if match:
                    ip, mac = match.groups()
                    if mac != "00:00:00:00:00:00":
                        self._arp_cache[ip] = mac.lower()
        except OSError as err:
            _LOGGER.debug("Failed to run arp command: %s", err)

    async def _resolve_hostname(self, ip: str) -> str | None:
        """Resolve hostname for IP address via reverse DNS lookup."""
        try:
            result = await asyncio.to_thread(socket.gethostbyaddr, ip)
            hostname = result[0]
            _LOGGER.debug("Resolved %s -> %s", ip, hostname)
            # Remove domain if present, keep just the hostname
            if "." in hostname:
                # Check if it looks like a domain name vs IP-based name
                parts = hostname.split(".")
                if not all(p.isdigit() for p in parts):
                    hostname = parts[0]
            return hostname
        except (socket.herror, socket.gaierror, OSError) as err:
            _LOGGER.debug("Could not resolve hostname for %s: %s", ip, err)
            return None

    async def _resolve_vendor(self, mac: str) -> str | None:
        """Resolve vendor from MAC address."""
        if not mac:
            return None

        lookup = await self._get_mac_lookup()
        if not lookup:
            return None

        try:
            return await lookup.lookup(mac)
        except Exception:
            return None

    async def _ping_host(self, ip: str) -> bool:
        """Ping a single host and return True if online."""
        try:
            result = await async_ping(
                ip,
                count=self._ping_count,
                timeout=self._ping_timeout,
                privileged=False,  # Use unprivileged sockets if available
            )
            return result.is_alive
        except NameLookupError:
            return False
        except OSError as err:
            # May need privileged mode
            _LOGGER.debug("Ping failed for %s (may need privileges): %s", ip, err)
            try:
                result = await async_ping(
                    ip,
                    count=self._ping_count,
                    timeout=self._ping_timeout,
                    privileged=True,
                )
                return result.is_alive
            except Exception as err2:
                _LOGGER.debug("Privileged ping also failed for %s: %s", ip, err2)
                return False
        except Exception as err:
            _LOGGER.debug("Unexpected ping error for %s: %s", ip, err)
            return False

    async def _scan_host(self, ip: str) -> DeviceInfo | None:
        """Scan a single host and return DeviceInfo if online."""
        is_online = await self._ping_host(ip)
        if not is_online:
            return None

        # Get MAC from ARP cache
        mac = self._arp_cache.get(ip)

        # Resolve hostname
        hostname = await self._resolve_hostname(ip)

        # Resolve vendor
        vendor = await self._resolve_vendor(mac) if mac else None

        now = datetime.now(timezone.utc)
        return DeviceInfo(
            ip_address=ip,
            mac_address=mac,
            hostname=hostname,
            vendor=vendor,
            is_online=True,
            first_seen=now,
            last_seen=now,
            failed_checks=0,
        )

    async def full_scan(self) -> list[DeviceInfo]:
        """Perform a full network scan and return discovered devices."""
        _LOGGER.debug("Starting full network scan of %s", self._networks)

        # Refresh ARP cache before scanning
        await self._refresh_arp_cache()

        # Get all IPs to scan
        ips = self._expand_networks()
        _LOGGER.debug("Scanning %d IP addresses", len(ips))

        # Use semaphore to limit concurrent pings
        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def scan_with_limit(ip: str) -> DeviceInfo | None:
            async with semaphore:
                return await self._scan_host(ip)

        # Scan all IPs concurrently
        results = await asyncio.gather(
            *[scan_with_limit(ip) for ip in ips],
            return_exceptions=True,
        )

        # Filter successful results
        devices: list[DeviceInfo] = []
        for result in results:
            if isinstance(result, DeviceInfo):
                devices.append(result)
            elif isinstance(result, Exception):
                _LOGGER.debug("Scan error: %s", result)

        _LOGGER.info("Full scan complete: found %d online devices", len(devices))

        # Refresh ARP cache again after scanning to pick up new entries
        await self._refresh_arp_cache()

        # Update MAC addresses for devices that didn't have them
        for device in devices:
            if not device.mac_address and device.ip_address in self._arp_cache:
                device.mac_address = self._arp_cache[device.ip_address]
                device.vendor = await self._resolve_vendor(device.mac_address)

        return devices

    async def check_devices(self, devices: list[DeviceInfo]) -> dict[str, bool]:
        """Quick check if known devices are still online.

        Returns dict mapping device identifier to online status.
        """
        if not devices:
            return {}

        _LOGGER.debug("Quick check of %d devices", len(devices))

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def ping_with_limit(device: DeviceInfo) -> tuple[str, bool]:
            async with semaphore:
                is_online = await self._ping_host(device.ip_address)
                return device.identifier, is_online

        results = await asyncio.gather(
            *[ping_with_limit(d) for d in devices],
            return_exceptions=True,
        )

        status: dict[str, bool] = {}
        for result in results:
            if isinstance(result, tuple):
                identifier, is_online = result
                status[identifier] = is_online

        online_count = sum(1 for v in status.values() if v)
        _LOGGER.debug("Quick check complete: %d/%d online", online_count, len(devices))

        return status
