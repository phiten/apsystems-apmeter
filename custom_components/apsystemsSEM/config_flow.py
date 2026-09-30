"""Config flow for APmeter SEM integration."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_DEVICE_NAME, DEFAULT_PORT, DOMAIN, LOGGER


class ApMeterFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for APmeter SEM."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input[CONF_IP_ADDRESS]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            device_name = (
                user_input.get("device_name", DEFAULT_DEVICE_NAME).strip()
                or DEFAULT_DEVICE_NAME
            )
            LOGGER.debug("[%s:%s] Validating APmeter SEM connection for config flow", ip, port)

            session = async_get_clientsession(self.hass)
            try:
                async with session.get(
                    f"http://{ip}:{port}/getDeviceInfo",
                    timeout=10,
                ) as resp:
                    if resp.status >= 400:
                        raise ValueError(f"HTTP {resp.status}")
                    payload = await resp.json(content_type=None)
                if not payload.get("data"):
                    raise ValueError("empty payload")
            except (aiohttp.ClientError, TimeoutError, ValueError, TypeError) as err:
                LOGGER.warning("[%s:%s] APmeter SEM validation failed: %s", ip, port, err)
                errors["base"] = "cannot_connect"
            else:
                uid = str(payload.get("deviceId") or payload.get("data", {}).get("deviceId") or ip)
                LOGGER.info("[%s:%s] APmeter SEM validation successful. Device ID: %s", ip, port, uid)
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=device_name,
                    data={
                        CONF_IP_ADDRESS: ip,
                        CONF_PORT: port,
                        "device_name": device_name,
                        "polling_interval": user_input.get("polling_interval", 10),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP_ADDRESS): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional("device_name", default=DEFAULT_DEVICE_NAME): str,
                    vol.Optional("polling_interval", default=10): int,
                }
            ),
            errors=errors,
        )
