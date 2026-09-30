"""The APmeter SEM local API integration."""

from __future__ import annotations

from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_PORT
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
    api = APmeterClient(
        ip_address=entry.data[CONF_IP_ADDRESS],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        timeout=10,
        session=async_get_clientsession(hass),
    )
    coordinator = ApMeterDataCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    assert entry.unique_id
    entry.runtime_data = ApMeterData(coordinator=coordinator, device_id=entry.unique_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ApMeterConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
