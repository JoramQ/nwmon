# Network Monitor for Home Assistant

A Home Assistant integration that discovers and monitors devices on your local network. Performs periodic network scans to detect devices and tracks their online/offline status.

## Features

- **Network Discovery**: Scans specified network ranges (CIDR notation) to find devices
- **Dual Scan Intervals**: Full network scans (default: hourly) and quick device checks (default: every minute)
- **Extended Device Info**: Tracks IP address, MAC address, hostname, and vendor
- **Configurable Offline Threshold**: Mark devices offline only after N consecutive failed checks
- **Persistent Storage**: Remembers discovered devices across Home Assistant restarts
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

### Per Device (Binary Sensor)

Each discovered device creates a binary sensor:

- **Entity ID**: `binary_sensor.nwmon_<hostname>` or `binary_sensor.nwmon_<mac>`
- **State**: `on` (online) / `off` (offline)
- **Device class**: `connectivity`
- **Attributes**:
  - `ip_address`: Current IP address
  - `mac_address`: MAC address (if available)
  - `hostname`: Resolved hostname
  - `vendor`: Device vendor (from MAC address)
  - `first_seen`: When device was first discovered
  - `last_seen`: Last time device was online
  - `failed_checks`: Current consecutive failed check count

### Summary Sensors

- `sensor.nwmon_devices_online`: Number of currently online devices
- `sensor.nwmon_devices_total`: Total number of known devices
- `sensor.nwmon_last_full_scan`: Timestamp of last full network scan

## Example Automations

### Notify when new device joins network

```yaml
automation:
  - alias: "New device on network"
    trigger:
      - platform: state
        entity_id: sensor.nwmon_devices_total
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
    action:
      - service: notify.mobile_app
        data:
          message: "New device detected on network!"
```

### Notify when specific device goes offline

```yaml
automation:
  - alias: "Server offline alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.nwmon_server
        to: "off"
        for:
          minutes: 5
    action:
      - service: notify.mobile_app
        data:
          message: "Server has been offline for 5 minutes!"
```

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

- MAC addresses are only available for devices on the same network segment
- The ARP cache is used, so devices must have recently communicated with the HA host

### Permission errors

- On some systems, ICMP ping requires elevated privileges
- The integration tries unprivileged mode first, then falls back to privileged mode

## License

MIT License - see LICENSE file for details
