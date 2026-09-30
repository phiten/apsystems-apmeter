"""Constants for the APmeter SEM APsystems local API integration."""

import logging

DOMAIN = "apsystemsSEM"
DEFAULT_PORT = 80
DEFAULT_DEVICE_NAME = "APmeter SEM"
CONF_DEVICE_NAME = "device_name"
LOGGER = logging.getLogger(__name__)

# Polling interval in seconds.
POLLING_INTERVAL = 10
CONF_POLLING_INTERVAL = "polling_interval"
MIN_POLLING_INTERVAL = 5
MAX_POLLING_INTERVAL = 60

# Retained for compatibility with the existing config-flow screen, but not used
# by the APmeter device itself.
CONF_LIFETIME_OFFSET_P1 = "lifetime_offset_p1"
CONF_LIFETIME_OFFSET_P2 = "lifetime_offset_p2"
CONF_SHOWN_OFFSET_P1 = "shown_offset_p1"
CONF_SHOWN_OFFSET_P2 = "shown_offset_p2"
STORE_KEY = "apsystems_lifetime_offset"
STORE_VERSION = 1

CONF_BATTERY_SYSTEM = "battery_system"
CONF_DETAIL_POLL = "detail_poll"
CONF_SLOW_DETAIL_POLL = "slow_detail_poll"
CONF_ALARM_NOTIFICATIONS = "alarm_notifications"

MODEL_BY_MAX_POWER: dict[int, str] = {}
UNKNOWN_MODEL_NAME = "SEM"
