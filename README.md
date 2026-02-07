<p align="center">
  <img src="images/logo.png" alt="nwmon logo">
</p>

# Network Monitor for Home Assistant

A Home Assistant integration that discovers and monitors devices on your local network. Performs periodic network scans to detect devices and tracks their online/offline status.

## Features

- **Network Discovery**: Scans specified network ranges (CIDR notation) to find devices
- **Dual Scan Intervals**: Full network scans (default: hourly) and quick device checks (default: every minute)
- **Extended Device Info**: Tracks IP address, MAC address, hostname, and vendor
- **Ping Latency**: Captures round-trip time for each device and exposes it as a per-device sensor
- **Watched Devices**: Mark important devices as "watched" to get a dedicated event when they go offline
- **HA Services**: Trigger scans, forget devices, and watch devices from automations or Developer Tools
- **Configurable Offline Threshold**: Mark devices offline only after N consecutive failed checks
- **Persistent Storage**: Remembers discovered devices (including watched status) across Home Assistant restarts
- **Multi-VLAN Support**: Add the integration multiple times for different network ranges — services automatically resolve which instance owns each device
- **UI Configuration**: Set up entirely through the Home Assistant UI

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL and select "Integration" as the category
5. Click "Add"
6. Find "Network Monitor" in the integration list and click "Download"
7. Restart Home Assistant

### Manual Installation

1. Download the `custom_components/nwmon` folder from this repository
2. Copy it to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Network Monitor"
4. Enter your network range(s) in CIDR notation (e.g., `192.168.1.0/24`)
5. Configure scan intervals and offline threshold

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| Network ranges | - | Networks to scan (CIDR notation, one per line) |
| Full scan interval | 60 min | How often to scan the entire network |
| Quick check interval | 1 min | How often to check known devices |
| Ping timeout | 1 sec | Timeout for each ping |
| Offline threshold | 3 | Failed checks before marking device offline |

## Entities

The integration creates two groups of entities on the Devices page:

### Network Monitor (Main Device)

Summary sensors for overall network status:

- `sensor.nwmon_devices_online`: Number of currently online devices
- `sensor.nwmon_devices_total`: Total number of known devices
- `sensor.nwmon_last_full_scan`: Timestamp of last full network scan

### Per-Device (Individual Devices)

Each discovered network device gets its own device entry with:

- **Device name**: Hostname (or MAC/IP if hostname unavailable)
- **Manufacturer**: Vendor name (from MAC address lookup)
- **Connectivity sensor**: `on` (online) / `off` (offline)
- **Ping Latency sensor**: Round-trip time in milliseconds (shown as "Unknown" when offline)
- **Attributes**:
  - `ip_address`: Current IP address
  - `mac_address`: MAC address (if available)
  - `hostname`: Resolved hostname (via reverse DNS)
  - `vendor`: Device vendor (from MAC address)
  - `first_seen`: When device was first discovered
  - `last_seen`: Last time device was online
  - `failed_checks`: Current consecutive failed check count
  - `latency_ms`: Last ping round-trip time in milliseconds
  - `watched`: Whether this device fires priority offline events

Devices are linked to the main Network Monitor via the "via_device" relationship, creating a clear hierarchy on the integration page.

### Device Identification and Cross-Integration Linking

Each discovered device is identified internally by its **MAC address** when available, falling back to its **IP address** if not.

When a MAC address is available, the integration registers it as a **connection** in Home Assistant's device registry. HA uses these connections to automatically **link devices across integrations** — for example, if your router integration (UniFi, Fritz!Box, etc.) already created a device for the same MAC address, HA will merge both under one device entry. This means entities from both integrations appear together on a single device page.

**MAC addresses are resolved from the system's ARP cache**, which only contains entries for devices on the same Layer 2 (broadcast) network segment as the Home Assistant host. This means:

- **Same subnet**: Devices get a MAC address → vendor identification works, cross-integration linking works, and the device is identified persistently even if its IP changes.
- **Remote subnet (different VLAN/routed network)**: The ARP table only contains the **router's MAC**, not the remote device's MAC. These devices will be tracked by **IP address only** — no vendor info, no cross-integration linking, and the device identity is tied to its IP. If the IP changes (e.g., DHCP renewal), it will appear as a new device.

This is an inherent limitation of ARP, not specific to this integration. If you use the multi-VLAN feature to scan remote subnets, keep in mind that those devices will have reduced functionality compared to devices on the local network.

## Services

All services are available in **Developer Tools > Services** and can be used in automations.

### `nwmon.full_scan`

Trigger a full network scan on all instances to discover new devices.

```yaml
service: nwmon.full_scan
```

### `nwmon.forget_device`

Remove a device from tracking. The `device_id` is the device's MAC address (e.g. `aa:bb:cc:dd:ee:ff`) or IP address. Accepts formats with or without separators.

```yaml
service: nwmon.forget_device
data:
  device_id: "aa:bb:cc:dd:ee:ff"
```

### `nwmon.watch_device`

Set the watched status on a device. The service automatically finds the correct integration instance.

```yaml
service: nwmon.watch_device
data:
  device_id: "aa:bb:cc:dd:ee:ff"
  watched: true
```

- **watched**: When `true`, the device fires an additional `nwmon_watched_device_offline` event when it goes offline, useful for priority alerting.

## Events

| Event | Description |
|-------|-------------|
| `nwmon_device_online` | Fired when any device comes back online |
| `nwmon_device_offline` | Fired when any device goes offline |
| `nwmon_watched_device_offline` | Fired **in addition to** `device_offline` when a watched device goes offline |

## Example Automations

### Notify when new device joins network

```yaml
alias: "New device on network"
triggers:
  - trigger: state
    entity_id: sensor.nwmon_devices_total
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
actions:
  - action: notify.mobile_app
    data:
      message: "New device detected on network!"
```

### Notify when specific device goes offline

```yaml
alias: "Server offline alert"
triggers:
  - trigger: state
    entity_id: binary_sensor.server_connectivity  # Check your actual entity ID
    to: "off"
    for:
      minutes: 5
actions:
  - action: notify.mobile_app
    data:
      message: "Server has been offline for 5 minutes!"
```

### Alert when a watched device goes offline

```yaml
alias: "Watched device offline"
triggers:
  - trigger: event
    event_type: nwmon_watched_device_offline
actions:
  - action: notify.mobile_app
    data:
      title: "Priority: Device Offline"
      message: "{{ trigger.event.data.display_name }} ({{ trigger.event.data.ip_address }}) went offline!"
```

> **Note**: Entity IDs are auto-generated by Home Assistant based on device name. Check **Settings → Devices & Services → Entities** for the actual entity ID of your device. The `device_id` for services is the MAC address (shown in the entity attributes) or the IP address.

## Requirements

- Home Assistant 2024.1.0 or newer
- Network access to devices being monitored
- For MAC address resolution: Devices must be on the same network segment (L2)

## Troubleshooting

### No devices found

- Ensure your network range is correct
- Check that Home Assistant can reach devices on that network
- Some devices may not respond to ICMP ping

### MAC addresses not showing

- MAC addresses are only available for devices on the same Layer 2 network segment — see [Device Identification and Cross-Integration Linking](#device-identification-and-cross-integration-linking) above
- The ARP cache is used, so devices must have recently communicated with the HA host
- ARP entries can expire; the integration will backfill the MAC on subsequent scans if the entry reappears

### Permission errors

- On some systems, ICMP ping requires elevated privileges
- The integration tries unprivileged mode first, then falls back to privileged mode

## License

MIT License - see LICENSE file for details
