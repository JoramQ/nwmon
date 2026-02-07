# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Network Monitor (`nwmon`) is a Home Assistant custom integration (HACS-installable) that discovers and monitors devices on local networks using ICMP ping. It provides device discovery via CIDR network scanning, online/offline tracking with configurable thresholds, ping latency measurement, MAC vendor identification, and persistent state across HA restarts.

## Development Notes

- **No build system or test suite.** This is a pure Python HA integration with no compilation, bundling, linting config, or automated tests. Manual test procedures are in `TESTPLAN.md`.
- **Dependencies:** `icmplib>=3.0` (async ICMP ping) and `mac-vendor-lookup>=0.1.12` (MAC vendor ID). Declared in `custom_components/nwmon/manifest.json`.
- **HA version requirement:** 2024.1.0+
- **To test:** Install into a Home Assistant instance by copying `custom_components/nwmon/` into the HA `custom_components/` directory and restart HA.

## Architecture

All source lives under `custom_components/nwmon/`. The integration follows standard HA patterns:

### Core Components

- **`scanner.py`** — `NetworkScanner` class and `DeviceInfo` dataclass. Handles async ICMP ping (via `icmplib`), CIDR network expansion, MAC resolution (reads `/proc/net/arp` or falls back to `arp -an`), reverse DNS hostname lookup, and vendor identification. Uses semaphore-limited concurrency (50 concurrent pings). Has two modes: `full_scan()` for entire subnets and `check_devices()` for quick checks of known devices.

- **`coordinator.py`** — `NetworkMonitorCoordinator` extends HA's `DataUpdateCoordinator`. Manages dual-interval scheduling (infrequent full scans + frequent quick checks), device state dictionary, offline threshold logic (device goes offline after N consecutive failed checks), persistent JSON storage via HA's `Store` helper, and fires events on state transitions (`nwmon_device_online`, `nwmon_device_offline`, `nwmon_watched_device_offline`). Also handles service logic (full_scan, forget_device, watch_device).

- **`config_flow.py`** — Two-step UI config: network CIDR input → interval/threshold settings. Also provides an options flow for reconfiguration after setup. Validates CIDR notation via Python's `ipaddress` module.

- **`__init__.py`** — Integration setup entry point. Creates the integration device in HA's device registry, registers global services (once per domain), and coordinates multi-entry support (multiple network ranges/VLANs).

- **`binary_sensor.py`** — Per-device connectivity entities (`DeviceBinarySensor`). Each discovered device gets a binary sensor showing online/off with extra state attributes (IP, MAC, hostname, vendor, latency, first/last seen, etc.).

- **`sensor.py`** — Summary sensors (devices online count, total count, last full scan timestamp) linked to the main integration device, plus per-device ping latency sensors.

- **`const.py`** — All constants, defaults, attribute keys, service names, and event types.

### Key Patterns

- **Dual-interval scheduling:** Full network scans run every N quick-check cycles (calculated as `full_scan_interval / check_interval`). First update after startup always triggers a full scan.
- **Device identification:** Devices are keyed by MAC address when available, falling back to IP. The `DeviceInfo.identifier` property handles this.
- **Device ID resolution in services:** `_resolve_device_id()` in coordinator flexibly matches by MAC (with/without colons), IP, or exact key — enabling services to accept various identifier formats.
- **Entity creation for new devices:** `async_add_listener` callbacks in the sensor/binary_sensor platforms detect newly discovered devices and dynamically add entities.
- **Multi-VLAN support:** The integration can be added multiple times. Services iterate all coordinator instances via `hass.data[DOMAIN]`.
- **Persistence:** Device state is saved to HA's `.storage/` directory as versioned JSON, loaded on startup to preserve history across restarts.
