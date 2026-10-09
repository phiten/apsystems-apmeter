"""The APmeter SEM local API integration."""

from __future__ import annotations

from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_TCP_ENABLED,
    CONF_TCP_INTERVAL,
    CONF_TCP_METER_ID,
    CONF_TCP_PORT,
    DEFAULT_PORT,
    DEFAULT_TCP_ENABLED,
    LOGGER,
)
from .coordinator import (
    APmeterClient,
    ApMeterConfigEntry,
    ApMeterData,
    ApMeterDataCoordinator,
    get_entry_value,
)
from .sem_tcp import DEFAULT_TCP_INTERVAL, DEFAULT_TCP_PORT, is_device_identity
from .tcp_coordinator import ApMeterTcpCoordinator

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
    tcp_coordinator: ApMeterTcpCoordinator | None = None
    if get_entry_value(entry, CONF_TCP_ENABLED, DEFAULT_TCP_ENABLED):
        # Only accept frames from this meter. Entries set up before the port-3333
        # channel existed have no stored meter ID; then the device ID is used.
        expected_id = get_entry_value(entry, CONF_TCP_METER_ID)
        if not expected_id and is_device_identity(entry.unique_id):
            expected_id = entry.unique_id
        tcp_coordinator = ApMeterTcpCoordinator(
            hass,
            entry,
            coordinator,
            host=ip_addr,
            port=get_entry_value(entry, CONF_TCP_PORT, DEFAULT_TCP_PORT),
            interval=get_entry_value(entry, CONF_TCP_INTERVAL, DEFAULT_TCP_INTERVAL),
            expected_id=expected_id,
        )

    entry.runtime_data = ApMeterData(
        coordinator=coordinator, device_id=entry.unique_id, tcp_coordinator=tcp_coordinator
    )
    LOGGER.debug("[%s:%s] Forwarding sensor platform for entry %s", ip_addr, port, entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if tcp_coordinator is not None:
        tcp_coordinator.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    LOGGER.info("[%s:%s] APmeter SEM integration setup completed for entry %s", ip_addr, port, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ApMeterConfigEntry) -> bool:
    """Unload a config entry."""
    LOGGER.info("[%s] Unloading APmeter SEM integration entry %s", entry.data.get(CONF_IP_ADDRESS, "unknown"), entry.entry_id)
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data.tcp_coordinator is not None:
        await entry.runtime_data.tcp_coordinator.async_stop()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ApMeterConfigEntry) -> None:
    """Apply changed options."""
    await hass.config_entries.async_reload(entry.entry_id)
