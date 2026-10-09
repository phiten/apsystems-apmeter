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

# Fast power values over TCP port 3333 (see sem_tcp.py).
CONF_TCP_ENABLED = "tcp_enabled"
CONF_TCP_PORT = "tcp_port"
CONF_TCP_INTERVAL = "tcp_interval"
CONF_TCP_METER_ID = "tcp_meter_id"
DEFAULT_TCP_ENABLED = True
# HTTP polling interval in seconds while port 3333 delivers fresh power values.
TCP_HTTP_POLLING_INTERVAL = 15
# How often to check whether the port-3333 values went stale, in seconds.
TCP_STALE_CHECK_INTERVAL = 2
