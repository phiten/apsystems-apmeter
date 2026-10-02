"""Coordinator for APmeter SEM devices."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
import json
import math
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_POLLING_INTERVAL,
    LOGGER,
    POLLING_INTERVAL,
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
                value = float(value)
            except (TypeError, ValueError):
                return default
            if not math.isfinite(value):
                return default
            return value

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
    max_failed_updates = 10

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
        self._last_good_data = self._fallback_data
        self._failed_update_count = 0
        self._is_data_available = True

    @property
    def _log_id(self) -> str:
        return self.config_entry.data.get(CONF_IP_ADDRESS, self.device_ip)

    @property
    def detected_model(self) -> str:
        return "SEM"

    @property
    def is_data_available(self) -> bool:
        return self._is_data_available

    def _sanitize_energy_counters(self, new_data: ApMeterOutputData) -> ApMeterOutputData:
        """Reject suspicious drops in cumulative energy values. The APmeter can occasionally return an invalid zero during a transient response; keep the previous valid total instead."""
        if self._last_good_data is None:
            return new_data

        previous = self._last_good_data.output_data
        sanitized = new_data
        energy_keys = ("iE1", "iE2", "iE3", "iE", "eE1", "eE2", "eE3", "eE")

        for key in energy_keys:
            current_value = float(getattr(new_data, key, 0.0))
            previous_value = float(getattr(previous, key, 0.0))
            if not math.isfinite(current_value) or not math.isfinite(previous_value):
                continue
            if previous_value > 0 and current_value <= previous_value:
                LOGGER.warning(
                    "[%s] Rejecting invalid APmeter energy counter drop for %s: %.3f -> %.3f. Keeping last valid value.",
                    self._log_id,
                    key,
                    previous_value,
                    current_value,
                )
                sanitized = replace(sanitized, **{key: previous_value})

        return sanitized

    async def _async_setup(self) -> None:
        try:
            info = await self.api.get_device_info()
            self.device_version = info.devVer or "unknown"
            self.device_ip = info.ip or self.config_entry.data.get(CONF_IP_ADDRESS, "unknown")
            self._fallback_data = ApMeterSensorData(output_data=ApMeterOutputData(), device_info=info)
            self._last_good_data = self._fallback_data
            LOGGER.info("[%s] APmeter connected – type=%s, firmware=%s", self._log_id, info.type, self.device_version)
        except Exception as err:  # noqa: BLE001
            LOGGER.debug("[%s] APmeter not reachable during setup: %s", self._log_id, err)

    async def _async_update_data(self) -> ApMeterSensorData:
        try:
            device_info = await self.api.get_device_info()
            self.device_version = device_info.devVer or "unknown"
            self.device_ip = device_info.ip or self.config_entry.data.get(CONF_IP_ADDRESS, "unknown")
            output_data = await self.api.get_output_data()
            output_data = self._sanitize_energy_counters(output_data)
            self.inverter_reachable = True
            self._failed_update_count = 0
            self._is_data_available = True
            result = ApMeterSensorData(output_data=output_data, device_info=device_info)
            self._last_good_data = result
            self._fallback_data = result
            LOGGER.debug(
                "[%s] APmeter poll successful: p=%.3f, p1=%.3f, p2=%.3f, p3=%.3f, iE=%.3f, eE=%.3f",
                self._log_id,
                output_data.p,
                output_data.p1,
                output_data.p2,
                output_data.p3,
                output_data.iE,
                output_data.eE,
            )
            return result
        except Exception as err:  # noqa: BLE001
            self.inverter_reachable = False
            self._failed_update_count += 1
            if self._failed_update_count >= self.max_failed_updates:
                self._is_data_available = False
                self.last_update_success = False
                LOGGER.warning(
                    "[%s] APmeter update failed %s/%s times; marking sensor data unavailable. Last valid values retained.",
                    self._log_id,
                    self._failed_update_count,
                    self.max_failed_updates,
                )
            else:
                self._is_data_available = True
                self.last_update_success = True
                LOGGER.debug(
                    "[%s] APmeter update failed (%s/%s). Retaining last valid data: p=%.3f, iE=%.3f, eE=%.3f",
                    self._log_id,
                    self._failed_update_count,
                    self.max_failed_updates,
                    self._last_good_data.output_data.p,
                    self._last_good_data.output_data.iE,
                    self._last_good_data.output_data.eE,
                )
            LOGGER.debug("[%s] APmeter update error details: %s", self._log_id, err)
            return self._last_good_data


def _make_fallback_meter() -> ApMeterSensorData:
    return ApMeterSensorData(output_data=ApMeterOutputData(), device_info=ApMeterDeviceInfo())
