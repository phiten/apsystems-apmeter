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

UNKNOWN_MODEL_NAME = "SEM"
