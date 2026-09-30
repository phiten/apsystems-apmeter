"""The APmeter SEM local API integration."""

from __future__ import annotations

from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_PORT, LOGGER
from .coordinator import (
    APmeterClient,
    ApMeterConfigEntry,
    ApMeterData,
    ApMeterDataCoordinator,
)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ApMeterConfigEntry) -> bool:
    """Set up this integration using UI."""
    ip_addr = entry.data[CONF_IP_ADDRESS]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    LOGGER.info("[%s:%s] Setting up APmeter SEM integration entry %s", ip_addr, port, entry.entry_id)
    api = APmeterClient(
        ip_address=ip_addr,
        port=port,
        timeout=10,
        session=async_get_clientsession(hass),
    )
    coordinator = ApMeterDataCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:  # noqa: BLE001
        LOGGER.exception("[%s:%s] Initial APmeter refresh failed during setup for entry %s", ip_addr, port, entry.entry_id)
        raise

    assert entry.unique_id
    entry.runtime_data = ApMeterData(coordinator=coordinator, device_id=entry.unique_id)
    LOGGER.debug("[%s:%s] Forwarding sensor platform for entry %s", ip_addr, port, entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    LOGGER.info("[%s:%s] APmeter SEM integration setup completed for entry %s", ip_addr, port, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ApMeterConfigEntry) -> bool:
    """Unload a config entry."""
    LOGGER.info("[%s] Unloading APmeter SEM integration entry %s", entry.data.get(CONF_IP_ADDRESS, "unknown"), entry.entry_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
