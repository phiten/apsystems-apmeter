"""Config flow for APmeter SEM integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DEVICE_NAME,
    CONF_POLLING_INTERVAL,
    CONF_TCP_ENABLED,
    CONF_TCP_INTERVAL,
    CONF_TCP_METER_ID,
    CONF_TCP_PORT,
    DEFAULT_DEVICE_NAME,
    DEFAULT_PORT,
    DEFAULT_TCP_ENABLED,
    DOMAIN,
    LOGGER,
    POLLING_INTERVAL,
)
from .coordinator import get_entry_value
from .sem_tcp import (
    DEFAULT_TCP_INTERVAL,
    DEFAULT_TCP_PORT,
    MAX_TCP_INTERVAL,
    MIN_TCP_INTERVAL,
    InvalidFrameError,
    SemFrame,
    SemTcpError,
    check_meter_id,
    probe,
)

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

TCP_SCHEMA: dict[Any, Any] = {
    vol.Optional(CONF_TCP_ENABLED, default=DEFAULT_TCP_ENABLED): bool,
    vol.Optional(CONF_TCP_PORT, default=DEFAULT_TCP_PORT): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=65535)
    ),
    vol.Optional(CONF_TCP_INTERVAL, default=DEFAULT_TCP_INTERVAL): vol.All(
        vol.Coerce(float), vol.Range(min=MIN_TCP_INTERVAL, max=MAX_TCP_INTERVAL)
    ),
}

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_DEVICE_NAME, default=DEFAULT_DEVICE_NAME): str,
        vol.Optional(CONF_POLLING_INTERVAL, default=POLLING_INTERVAL): int,
        **TCP_SCHEMA,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_POLLING_INTERVAL, default=POLLING_INTERVAL): int,
        **TCP_SCHEMA,
    }
)


async def _async_get_device_info(hass: HomeAssistant, ip: str, port: int) -> dict[str, Any]:
    """Read /getDeviceInfo; raises on any failure."""
    session = async_get_clientsession(hass)
    async with session.get(f"http://{ip}:{port}/getDeviceInfo", timeout=10) as resp:
        if resp.status >= 400:
            raise ValueError(f"HTTP {resp.status}")
        payload = await resp.json(content_type=None)
    if not payload.get("data"):
        raise ValueError("empty payload")
    return payload


async def _async_validate_tcp(
    ip: str, port: int, device_id: str | None
) -> tuple[str | None, SemFrame | None]:
    """Try port 3333 once. Returns (error key, frame)."""
    try:
        frame = await probe(ip, port)
    except InvalidFrameError as err:
        LOGGER.warning("[%s:%s] Port %s sent an invalid frame: %s", ip, port, port, err)
        return "tcp_invalid_frame", None
    except SemTcpError as err:
        LOGGER.warning("[%s:%s] Port %s not reachable: %s", ip, port, port, err)
        return "tcp_cannot_connect", None
    if check_meter_id(frame.meter_id, device_id) is False:
        LOGGER.warning(
            "[%s:%s] Meter ID on port %s (%s) does not match the device ID via HTTP (%s)",
            ip,
            port,
            port,
            frame.meter_id,
            device_id,
        )
        return "tcp_id_mismatch", frame
    return None, frame


class ApMeterFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for APmeter SEM."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ApMeterOptionsFlow:
        """Return the options flow."""
        return ApMeterOptionsFlow()

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Handle a meter found via mDNS (_http._tcp, company=apsystems)."""
        properties = {str(k).lower(): str(v).lower() for k, v in (discovery_info.properties or {}).items()}
        if properties.get("company") != "apsystems":
            return self.async_abort(reason="not_apmeter")
        host = str(discovery_info.ip_address) if discovery_info.ip_address else discovery_info.host
        LOGGER.debug("[%s] APmeter SEM discovered via zeroconf: %s", host, discovery_info.name)

        try:
            payload = await _async_get_device_info(self.hass, host, DEFAULT_PORT)
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError) as err:
            # The integration needs HTTP anyway; ignore devices that do not answer.
            LOGGER.debug("[%s] Discovered device did not answer via HTTP: %s", host, err)
            return self.async_abort(reason="cannot_connect")
        uid = str(payload.get("deviceId") or payload.get("data", {}).get("deviceId") or host)
        await self.async_set_unique_id(uid)
        # A known meter that got a new address keeps working.
        self._abort_if_unique_id_configured(updates={CONF_IP_ADDRESS: host})

        self._discovered_host = host
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input[CONF_IP_ADDRESS]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            device_name = (
                user_input.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME).strip()
                or DEFAULT_DEVICE_NAME
            )
            LOGGER.debug("[%s:%s] Validating APmeter SEM connection for config flow", ip, port)

            try:
                payload = await _async_get_device_info(self.hass, ip, port)
            except (aiohttp.ClientError, TimeoutError, ValueError, TypeError) as err:
                LOGGER.warning("[%s:%s] APmeter SEM validation failed: %s", ip, port, err)
                errors["base"] = "cannot_connect"
            else:
                uid = str(payload.get("deviceId") or payload.get("data", {}).get("deviceId") or ip)
                LOGGER.info("[%s:%s] APmeter SEM validation successful. Device ID: %s", ip, port, uid)
                await self.async_set_unique_id(uid, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                data = {
                    CONF_IP_ADDRESS: ip,
                    CONF_PORT: port,
                    CONF_DEVICE_NAME: device_name,
                    CONF_POLLING_INTERVAL: user_input.get(CONF_POLLING_INTERVAL, POLLING_INTERVAL),
                    CONF_TCP_ENABLED: user_input.get(CONF_TCP_ENABLED, DEFAULT_TCP_ENABLED),
                    CONF_TCP_PORT: user_input.get(CONF_TCP_PORT, DEFAULT_TCP_PORT),
                    CONF_TCP_INTERVAL: user_input.get(CONF_TCP_INTERVAL, DEFAULT_TCP_INTERVAL),
                }
                if data[CONF_TCP_ENABLED]:
                    error, frame = await _async_validate_tcp(ip, data[CONF_TCP_PORT], uid)
                    if error:
                        errors["base"] = error
                    else:
                        assert frame is not None
                        data[CONF_TCP_METER_ID] = frame.meter_id

                if not errors:
                    return self.async_create_entry(title=device_name, data=data)

        suggested = user_input or ({CONF_IP_ADDRESS: self._discovered_host} if self._discovered_host else {})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
        )


class ApMeterOptionsFlow(OptionsFlow):
    """Change polling and the port-3333 channel."""

    @property
    def _entry(self) -> ConfigEntry:
        entry = self.hass.config_entries.async_get_entry(self.handler)
        assert entry is not None
        return entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and validate the options."""
        entry = self._entry
        errors: dict[str, str] = {}

        if user_input is not None:
            options = dict(user_input)
            if options.get(CONF_TCP_ENABLED, DEFAULT_TCP_ENABLED):
                ip = entry.data[CONF_IP_ADDRESS]
                tcp_port = options.get(CONF_TCP_PORT, DEFAULT_TCP_PORT)
                error, frame = None, self._running_frame(tcp_port)
                if frame is not None:
                    # Reuse the open connection instead of opening a second one.
                    if check_meter_id(frame.meter_id, entry.unique_id) is False:
                        error = "tcp_id_mismatch"
                else:
                    error, frame = await _async_validate_tcp(ip, tcp_port, entry.unique_id)
                if error:
                    errors["base"] = error
                else:
                    assert frame is not None
                    options[CONF_TCP_METER_ID] = frame.meter_id
            if not errors:
                return self.async_create_entry(title="", data=options)

        suggested = user_input or {
            CONF_POLLING_INTERVAL: get_entry_value(entry, CONF_POLLING_INTERVAL, POLLING_INTERVAL),
            CONF_TCP_ENABLED: get_entry_value(entry, CONF_TCP_ENABLED, DEFAULT_TCP_ENABLED),
            CONF_TCP_PORT: get_entry_value(entry, CONF_TCP_PORT, DEFAULT_TCP_PORT),
            CONF_TCP_INTERVAL: get_entry_value(entry, CONF_TCP_INTERVAL, DEFAULT_TCP_INTERVAL),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, suggested),
            errors=errors,
        )

    def _running_frame(self, tcp_port: int) -> SemFrame | None:
        """A fresh frame from the already running poller on the same port, if any."""
        runtime_data = getattr(self._entry, "runtime_data", None)
        tcp = getattr(runtime_data, "tcp_coordinator", None)
        if tcp is None or tcp.client.port != tcp_port:
            return None
        return tcp.fresh_frame()
