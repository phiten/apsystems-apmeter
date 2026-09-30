"""Coordinator for APmeter SEM devices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_ALARM_NOTIFICATIONS,
    CONF_BATTERY_SYSTEM,
    CONF_DETAIL_POLL,
    CONF_DEVICE_NAME,
    CONF_LIFETIME_OFFSET_P1,
    CONF_LIFETIME_OFFSET_P2,
    CONF_POLLING_INTERVAL,
    CONF_SHOWN_OFFSET_P1,
    CONF_SHOWN_OFFSET_P2,
    CONF_SLOW_DETAIL_POLL,
    LOGGER,
    POLLING_INTERVAL,
    STORE_KEY,
    STORE_VERSION,
)


@dataclass
class ApMeterOutputData:
    """Normalized APmeter output payload."""

    p1: float = 0.0
    p2: float = 0.0
    p3: float = 0.0
    p: float = 0.0
    q1: float = 0.0
    q2: float = 0.0
    q3: float = 0.0
    q: float = 0.0
    s1: float = 0.0
    s2: float = 0.0
    s3: float = 0.0
    s: float = 0.0
    v1: float = 0.0
    v2: float = 0.0
    v3: float = 0.0
    c1: float = 0.0
    c2: float = 0.0
    c3: float = 0.0
    iE1: float = 0.0
    iE2: float = 0.0
    iE3: float = 0.0
    iE: float = 0.0
    eE1: float = 0.0
    eE2: float = 0.0
    eE3: float = 0.0
    eE: float = 0.0
    pf1: float = 0.0
    pf2: float = 0.0
    pf3: float = 0.0
    pf: float = 0.0


@dataclass
class ApMeterDeviceInfo:
    """Minimal normalized device metadata."""

    deviceId: str = "unknown"
    type: str = "SEM"
    devVer: str = "unknown"
    ssid: str = "unknown"
    ip: str = "unknown"
    CT: str = "120"
    CTDirection: str = "0"


@dataclass
class ApMeterSensorData:
    """Normalized APmeter sensor data."""

    output_data: ApMeterOutputData
    device_info: ApMeterDeviceInfo


@dataclass
class ApMeterData:
    """Store runtime data."""

    coordinator: ApMeterDataCoordinator
    device_id: str


type ApMeterConfigEntry = ConfigEntry[ApMeterData]


class APmeterClient:
    """Very small HTTP client for the APmeter SEM device."""

    def __init__(self, ip_address: str, port: int, session: aiohttp.ClientSession, timeout: int = 10) -> None:
        self.ip_address = ip_address
        self.port = port
        self.session = session
        self.timeout = timeout
        self.max_power = 0.0
        self.min_power = 0.0

    @property
    def base_url(self) -> str:
        return f"http://{self.ip_address}:{self.port}"

    async def _request(self, endpoint: str) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint}"
        async with self.session.get(url, timeout=self.timeout) as resp:
            payload = await resp.json(content_type=None)
            if resp.status >= 400:
                raise ValueError(f"HTTP {resp.status} from {url}")
            return payload

    async def get_device_info(self) -> ApMeterDeviceInfo:
        raw = await self._request("getDeviceInfo")
        data = raw.get("data", {})
        return ApMeterDeviceInfo(
            deviceId=str(data.get("deviceId") or raw.get("deviceId") or "unknown"),
            type=str(data.get("type") or "SEM"),
            devVer=str(data.get("devVer") or "unknown"),
            ssid=str(data.get("ssid") or "unknown"),
            ip=str(data.get("ip") or "unknown"),
            CT=str(data.get("CT") or "120"),
            CTDirection=str(data.get("CTDirection") or "0"),
        )

    async def get_output_data(self) -> ApMeterOutputData:
        raw = await self._request("getOutputData")
        data = raw.get("data", {})

        def _num(key: str, default: float = 0.0) -> float:
            value = data.get(key)
            if value in (None, "", "null"):
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        return ApMeterOutputData(
            p1=_num("p1"),
            p2=_num("p2"),
            p3=_num("p3"),
            p=_num("p"),
            q1=_num("q1"),
            q2=_num("q2"),
            q3=_num("q3"),
            q=_num("q"),
            s1=_num("s1"),
            s2=_num("s2"),
            s3=_num("s3"),
            s=_num("s"),
            v1=_num("v1"),
            v2=_num("v2"),
            v3=_num("v3"),
            c1=_num("c1"),
            c2=_num("c2"),
            c3=_num("c3"),
            iE1=_num("iE1"),
            iE2=_num("iE2"),
            iE3=_num("iE3"),
            iE=_num("iE"),
            eE1=_num("eE1"),
            eE2=_num("eE2"),
            eE3=_num("eE3"),
            eE=_num("eE"),
            pf1=_num("pf1"),
            pf2=_num("pf2"),
            pf3=_num("pf3"),
            pf=_num("pf"),
        )


class ApMeterDataCoordinator(DataUpdateCoordinator[ApMeterSensorData]):
    """Coordinator for APmeter SEM data."""

    config_entry: ApMeterConfigEntry
    device_version: str
    device_ip: str
    inverter_reachable: bool = False

    def __init__(self, hass: HomeAssistant, config_entry: ApMeterConfigEntry, api: APmeterClient) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name="APmeter Data",
            update_interval=timedelta(seconds=config_entry.data.get(CONF_POLLING_INTERVAL, POLLING_INTERVAL)),
        )
        self.api = api
        self.device_version = "unknown"
        self.device_ip = config_entry.data.get(CONF_IP_ADDRESS, "unknown")
        self._fallback_data = ApMeterSensorData(
            output_data=ApMeterOutputData(),
            device_info=ApMeterDeviceInfo(),
        )

    @property
    def _log_id(self) -> str:
        return self.config_entry.data.get(CONF_IP_ADDRESS, self.device_ip)

    @property
    def detected_model(self) -> str:
        return "SEM"

    async def _async_setup(self) -> None:
        try:
            info = await self.api.get_device_info()
            self.device_version = info.devVer or "unknown"
            self.device_ip = info.ip or self.config_entry.data.get(CONF_IP_ADDRESS, "unknown")
            self._fallback_data = ApMeterSensorData(output_data=ApMeterOutputData(), device_info=info)
            LOGGER.info("[%s] APmeter connected – type=%s, firmware=%s", self._log_id, info.type, self.device_version)
        except Exception as err:  # noqa: BLE001
            LOGGER.debug("[%s] APmeter not reachable during setup: %s", self._log_id, err)

    async def _async_update_data(self) -> ApMeterSensorData:
        try:
            device_info = await self.api.get_device_info()
            self.device_version = device_info.devVer or "unknown"
            self.device_ip = device_info.ip or self.config_entry.data.get(CONF_IP_ADDRESS, "unknown")
            output_data = await self.api.get_output_data()
            self.inverter_reachable = True
            result = ApMeterSensorData(output_data=output_data, device_info=device_info)
            self._fallback_data = result
            return result
        except Exception as err:  # noqa: BLE001
            LOGGER.debug("[%s] APmeter update failed: %s", self._log_id, err)
            self.inverter_reachable = False
            return self._fallback_data


def _make_fallback_meter() -> ApMeterSensorData:
    return ApMeterSensorData(output_data=ApMeterOutputData(), device_info=ApMeterDeviceInfo())
