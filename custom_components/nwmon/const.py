"""Constants for the Network Monitor integration."""

DOMAIN = "nwmon"

# Configuration keys
CONF_NETWORKS = "networks"
CONF_FULL_SCAN_INTERVAL = "full_scan_interval"
CONF_CHECK_INTERVAL = "check_interval"
CONF_PING_TIMEOUT = "ping_timeout"
CONF_OFFLINE_THRESHOLD = "offline_threshold"
CONF_PING_COUNT = "ping_count"

# Default values
DEFAULT_FULL_SCAN_INTERVAL = 60  # minutes
DEFAULT_CHECK_INTERVAL = 1  # minutes
DEFAULT_PING_TIMEOUT = 1  # seconds
DEFAULT_OFFLINE_THRESHOLD = 3  # failed checks before marking offline
DEFAULT_PING_COUNT = 1  # pings per check

# Platforms
PLATFORMS = ["binary_sensor", "sensor"]

# Attributes
ATTR_IP_ADDRESS = "ip_address"
ATTR_MAC_ADDRESS = "mac_address"
ATTR_HOSTNAME = "hostname"
ATTR_VENDOR = "vendor"
ATTR_FIRST_SEEN = "first_seen"
ATTR_LAST_SEEN = "last_seen"
ATTR_FAILED_CHECKS = "failed_checks"

# Storage
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_devices"

# New attributes
ATTR_LATENCY = "latency_ms"
ATTR_NICKNAME = "nickname"
ATTR_WATCHED = "watched"

# Service names
SERVICE_FULL_SCAN = "full_scan"
SERVICE_FORGET_DEVICE = "forget_device"
SERVICE_WATCH_DEVICE = "watch_device"

# Service parameter
ATTR_DEVICE_ID = "device_id"

# Event names
EVENT_DEVICE_OFFLINE = f"{DOMAIN}_device_offline"
EVENT_DEVICE_ONLINE = f"{DOMAIN}_device_online"
EVENT_WATCHED_DEVICE_OFFLINE = f"{DOMAIN}_watched_device_offline"
