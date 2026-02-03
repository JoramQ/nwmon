# Network Monitor - Home Assistant Integration (HACS)

## Overview

A custom Home Assistant integration that discovers and monitors devices on specified network ranges. Installable via HACS.

## Architecture Decisions

| Decision | Choice |
|----------|--------|
| Deployment | Native HA integration (HACS) |
| Scanning Method | ICMP Ping |
| Concurrency | asyncio (HA's event loop) |
| State Transitions | Configurable failure threshold |
| Device Information | Extended (IP, MAC, hostname, vendor, timestamps) |
| Configuration | HA Config Flow (UI-based) |
| Storage | HA's built-in storage helpers |

## Project Structure

```
nwmon/
├── custom_components/
│   └── nwmon/
│       ├── __init__.py           # Integration setup
│       ├── manifest.json         # HACS/HA metadata
│       ├── config_flow.py        # UI configuration
│       ├── const.py              # Constants
│       ├── coordinator.py        # DataUpdateCoordinator (scheduling)
│       ├── scanner.py            # Async network scanner
│       ├── binary_sensor.py      # Device presence entities
│       ├── sensor.py             # Summary sensors (online count, etc.)
│       ├── device_tracker.py     # Alternative: device_tracker entities
│       ├── strings.json          # UI strings
│       └── translations/
│           └── en.json           # English translations
├── hacs.json                     # HACS repository config
├── README.md
└── LICENSE
```

## Home Assistant Entities

### Per-Device (Binary Sensor or Device Tracker)
Each discovered device becomes an entity:

**Binary Sensor approach:**
- Entity ID: `binary_sensor.nwmon_<hostname>` or `binary_sensor.nwmon_<mac>`
- State: `on` (online) / `off` (offline)
- Device class: `connectivity`
- Attributes:
  - `ip_address`
  - `mac_address`
  - `hostname`
  - `vendor`
  - `first_seen`
  - `last_seen`

**Device Tracker approach (alternative):**
- Entity ID: `device_tracker.nwmon_<mac>`
- State: `home` / `not_home`
- Same attributes

### Summary Sensors
- `sensor.nwmon_devices_online` - Count of online devices
- `sensor.nwmon_devices_total` - Total known devices
- `sensor.nwmon_last_scan` - Timestamp of last full scan

## Configuration Flow (UI)

### Step 1: Network Ranges
```
┌─────────────────────────────────────┐
│ Network Monitor Setup               │
├─────────────────────────────────────┤
│ Network ranges to scan (one per     │
│ line, CIDR notation):               │
│ ┌─────────────────────────────────┐ │
│ │ 192.168.1.0/24                  │ │
│ │ 10.0.0.0/24                     │ │
│ └─────────────────────────────────┘ │
│                                     │
│              [Submit]               │
└─────────────────────────────────────┘
```

### Step 2: Scan Settings
```
┌─────────────────────────────────────┐
│ Scan Settings                       │
├─────────────────────────────────────┤
│ Full scan interval:    [60] minutes │
│ Quick check interval:  [1] minutes  │
│ Ping timeout:          [1] seconds  │
│ Offline threshold:     [3] checks   │
│                                     │
│              [Submit]               │
└─────────────────────────────────────┘
```

### Options Flow
Users can modify settings after setup via integration options.

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                  Home Assistant                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │            DataUpdateCoordinator                 │    │
│  │  ┌─────────────┐    ┌─────────────────────────┐ │    │
│  │  │  Scheduler  │───▶│   Network Scanner       │ │    │
│  │  │ (60m / 1m)  │    │  (async ICMP ping)      │ │    │
│  │  └─────────────┘    └───────────┬─────────────┘ │    │
│  │                                 │               │    │
│  │                     ┌───────────▼─────────────┐ │    │
│  │                     │   Device State Store    │ │    │
│  │                     │   (HA storage helper)   │ │    │
│  │                     └───────────┬─────────────┘ │    │
│  └─────────────────────────────────┼───────────────┘    │
│                                    │                     │
│  ┌──────────────┐  ┌──────────────┐│┌──────────────┐    │
│  │binary_sensor │  │binary_sensor │││   sensor     │    │
│  │  device_1    │  │  device_2    │││ online_count │    │
│  └──────────────┘  └──────────────┘│└──────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Integration Skeleton
- [ ] Create manifest.json with metadata
- [ ] Basic `__init__.py` with async_setup_entry
- [ ] Constants file
- [ ] Config flow (network ranges input)
- [ ] HACS configuration (hacs.json)

### Phase 2: Network Scanner
- [ ] Async ICMP ping using `icmplib` (pure Python, no root needed)
- [ ] IP range expansion from CIDR
- [ ] MAC address resolution (ARP cache via /proc/net/arp)
- [ ] Hostname resolution (reverse DNS)
- [ ] Vendor lookup (oui database)

### Phase 3: Coordinator & State Management
- [ ] DataUpdateCoordinator for scheduled updates
- [ ] Dual interval logic (full scan vs quick check)
- [ ] State transition with configurable threshold
- [ ] Persistent storage for known devices

### Phase 4: Entities
- [ ] Binary sensor platform for each device
- [ ] Summary sensors (counts, last scan time)
- [ ] Device info for HA device registry
- [ ] Entity attributes (IP, MAC, vendor, etc.)

### Phase 5: Polish
- [ ] Options flow for changing settings
- [ ] Translations (strings.json)
- [ ] Service calls (trigger scan, forget device)
- [ ] README with installation instructions
- [ ] HACS submission requirements

## manifest.json

```json
{
  "domain": "nwmon",
  "name": "Network Monitor",
  "version": "1.0.0",
  "codeowners": ["@yourusername"],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/yourusername/nwmon",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/yourusername/nwmon/issues",
  "requirements": ["icmplib>=3.0", "mac-vendor-lookup>=0.1.12"]
}
```

## hacs.json

```json
{
  "name": "Network Monitor",
  "render_readme": true,
  "homeassistant": "2024.1.0"
}
```

## Dependencies

```
icmplib>=3.0              # Pure Python ICMP (works without root on most systems)
mac-vendor-lookup>=0.1.12 # Vendor identification from MAC
```

## Key HA Patterns Used

- **DataUpdateCoordinator**: Manages polling and distributes data to entities
- **ConfigEntry**: Stores user configuration persistently
- **async_forward_entry_setups**: Loads platforms (binary_sensor, sensor)
- **CoordinatorEntity**: Base class for entities that use coordinator data
- **Store**: Persists known devices across restarts

## Installation (via HACS)

1. Add custom repository in HACS: `https://github.com/yourusername/nwmon`
2. Install "Network Monitor"
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration
5. Search for "Network Monitor"
6. Enter network ranges and scan settings

## Notes

- **Privileges**: `icmplib` can run without root on Linux if `net.ipv4.ping_group_range` sysctl is set (HA typically handles this)
- **MAC resolution**: Only works for devices on the same L2 segment
- **HA restart**: Known devices persist, states are restored
- **Performance**: Uses HA's async event loop, won't block other integrations
