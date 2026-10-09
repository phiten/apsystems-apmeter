"""Push coordinator for the fast power values on TCP port 3333."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta
import time

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER, TCP_STALE_CHECK_INTERVAL
from .coordinator import ApMeterConfigEntry, ApMeterDataCoordinator
from .sem_tcp import SemFrame, SemTcpClient, SemTcpPoller, is_fresh


class ApMeterTcpCoordinator(DataUpdateCoordinator[SemFrame | None]):
    """Holds the latest valid port-3333 frame; updated by a background poller."""

    config_entry: ApMeterConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ApMeterConfigEntry,
        http_coordinator: ApMeterDataCoordinator,
        host: str,
        port: int,
        interval: float,
        expected_id: str | None,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name="APmeter TCP power",
            update_interval=None,
        )
        self.http_coordinator = http_coordinator
        self.client = SemTcpClient(host, port, expected_id=expected_id)
        self._poller = SemTcpPoller(
            self.client, interval, on_frame=self._handle_frame, on_error=self._handle_error
        )
        self._received_at: float | None = None
        self._active = False
        self._task: asyncio.Task[None] | None = None
        self._unsub_stale_check = None

    @property
    def _log_id(self) -> str:
        return f"{self.client.host}:{self.client.port}"

    async def _async_update_data(self) -> SemFrame | None:
        # Data is pushed by the poller; nothing to fetch on demand.
        return self.data

    @callback
    def async_start(self) -> None:
        """Start the poller task and the staleness check."""
        LOGGER.info(
            "[%s] Starting fast power polling every %.1fs", self._log_id, self._poller.interval
        )
        self._task = self.config_entry.async_create_background_task(
            self.hass, self._poller.run(), f"{DOMAIN} port {self.client.port} poller"
        )
        self._unsub_stale_check = async_track_time_interval(
            self.hass, self._async_check_stale, timedelta(seconds=TCP_STALE_CHECK_INTERVAL)
        )

    async def async_stop(self) -> None:
        """Stop polling and close the connection."""
        if self._unsub_stale_check is not None:
            self._unsub_stale_check()
            self._unsub_stale_check = None
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.client.close()
        stats = self.client.stats
        LOGGER.debug(
            "[%s] Fast power polling stopped: %s valid, %s invalid frames, %s connects",
            self._log_id,
            stats.frames_ok,
            stats.frames_invalid,
            stats.connects,
        )

    def fresh_frame(self) -> SemFrame | None:
        """The latest frame if it is recent enough to replace the HTTP values."""
        if self.data is None or not is_fresh(self._received_at, time.monotonic()):
            return None
        return self.data

    @callback
    def _handle_frame(self, frame: SemFrame) -> None:
        self._received_at = time.monotonic()
        if not self._active:
            self._active = True
            self.http_coordinator.set_tcp_active(True)
        self.async_set_updated_data(frame)

    @callback
    def _handle_error(self, err: Exception, failures: int, delay: float) -> None:
        stats = self.client.stats
        # Warn once per outage, then keep quiet while backing off.
        log = LOGGER.warning if failures == 1 else LOGGER.debug
        log(
            "[%s] Fast power request failed (%s); reconnecting in %.0fs "
            "(%s invalid frames so far)",
            self._log_id,
            err,
            delay,
            stats.frames_invalid,
        )

    @callback
    def _async_check_stale(self, _now: datetime) -> None:
        if self._active and self.fresh_frame() is None:
            self._active = False
            self.http_coordinator.set_tcp_active(False)
            # Let the power sensors switch back to the HTTP values.
            self.async_update_listeners()
