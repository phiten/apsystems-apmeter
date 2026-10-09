"""Fast local power channel of the APmeter SEM on TCP port 3333.

This is the protocol the EZHI inverter uses in "Local Control" mode to read the
meter. The meter is a plain TCP server (no encryption, no login). One request of
exactly four bytes returns one 44-byte frame:

    offset  type      content
    0       uint32    constant (259764, meaning unknown)
    4       uint32    constant (2, meaning unknown)
    8       float32   power L1 in W (positive = grid import)
    12      float32   power L2 in W
    16      float32   power L3 in W
    20      float32   total power in W (same as "p" via HTTP)
    24      float32   checksum = sum of the six values above
    28      char[16]  meter ID, zero padded

The client is read-only: it only ever sends the known request, keeps a single
connection and never asks faster than every 0.5 s.

This module must not import Home Assistant so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
import ipaddress
import logging
import math
import struct
import time

_LOGGER = logging.getLogger(__name__)

REQUEST = bytes.fromhex("02040113")
FRAME_LEN = 44

DEFAULT_TCP_PORT = 3333
DEFAULT_TCP_INTERVAL = 1.0
MIN_TCP_INTERVAL = 0.5
# Frames older than STALE_AFTER are ignored, so the interval must stay well below it.
MAX_TCP_INTERVAL = 5.0
READ_TIMEOUT = 3.0
BACKOFF_MIN = 1.0
BACKOFF_MAX = 30.0
STALE_AFTER = 10.0
CHECKSUM_TOLERANCE = 0.1

Sleep = Callable[[float], Awaitable[None]]


class SemTcpError(Exception):
    """Base error of the port-3333 channel."""


class SemTcpConnectionError(SemTcpError):
    """Connecting, sending or receiving failed."""


class SemTcpTimeout(SemTcpConnectionError):
    """The meter did not answer in time."""


class FrameError(ValueError):
    """Data that cannot be parsed as a frame."""


class InvalidFrameError(SemTcpError):
    """A complete frame was received but must not be used."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class SemFrame:
    """One decoded 44-byte frame."""

    l1: float
    l2: float
    l3: float
    p: float
    meter_id: str
    checksum_ok: bool


@dataclass(slots=True)
class SemTcpStats:
    """Counters for diagnostics."""

    frames_ok: int = 0
    invalid_length: int = 0
    invalid_checksum: int = 0
    invalid_id: int = 0
    timeouts: int = 0
    connection_errors: int = 0
    connects: int = 0

    @property
    def frames_invalid(self) -> int:
        return self.invalid_length + self.invalid_checksum + self.invalid_id


def parse_frame(data: bytes) -> SemFrame:
    """Decode a frame. Raises FrameError on wrong length; check ``checksum_ok``."""
    if len(data) != FRAME_LEN:
        raise FrameError(f"expected {FRAME_LEN} bytes, got {len(data)}")
    h1, h2 = struct.unpack("<II", data[:8])
    l1, l2, l3, total, check = struct.unpack("<5f", data[8:28])
    meter_id = data[28:].split(b"\0", 1)[0].decode("latin1").strip()
    values = (l1, l2, l3, total, check)
    ok = all(math.isfinite(v) for v in values) and (
        abs(check - (h1 + h2 + l1 + l2 + l3 + total)) <= CHECKSUM_TOLERANCE
    )
    return SemFrame(l1=l1, l2=l2, l3=l3, p=total, meter_id=meter_id, checksum_ok=ok)


def backoff_delay(failures: int) -> float:
    """Reconnect delay after ``failures`` consecutive failures: 1, 2, 4 ... 30 s."""
    return min(BACKOFF_MIN * 2 ** max(failures - 1, 0), BACKOFF_MAX)


def is_fresh(received_at: float | None, now: float, max_age: float = STALE_AFTER) -> bool:
    """Whether a frame received at monotonic time ``received_at`` may still be used."""
    return received_at is not None and now - received_at < max_age


def is_device_identity(device_id: str | None) -> bool:
    """Whether ``device_id`` identifies a meter (not missing, "unknown" or an IP fallback)."""
    if not device_id or device_id.strip().lower() == "unknown":
        return False
    try:
        ipaddress.ip_address(device_id.strip())
    except ValueError:
        return True
    return False


def check_meter_id(frame_id: str, device_id: str | None) -> bool | None:
    """Compare the frame's meter ID with the device identity; None if not comparable."""
    if not is_device_identity(device_id):
        return None
    assert device_id is not None
    return frame_id.strip().upper() == device_id.strip().upper()


class SemTcpClient:
    """One persistent connection to the meter's port 3333."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_TCP_PORT,
        *,
        expected_id: str | None = None,
        timeout: float = READ_TIMEOUT,
        min_interval: float = MIN_TCP_INTERVAL,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.host = host
        self.port = port
        self.expected_id = expected_id or None
        self.timeout = timeout
        self.stats = SemTcpStats()
        self._min_interval = max(min_interval, MIN_TCP_INTERVAL)
        self._sleep = sleep
        self._clock = clock
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_request: float | None = None

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def request(self) -> SemFrame:
        """Send the request and return a validated frame."""
        async with self._lock:
            if self._last_request is not None:
                wait = self._last_request + self._min_interval - self._clock()
                if wait > 0:
                    await self._sleep(wait)
            if self._writer is None:
                await self._connect()
            assert self._reader is not None and self._writer is not None
            self._last_request = self._clock()
            try:
                self._writer.write(REQUEST)
                await asyncio.wait_for(self._writer.drain(), self.timeout)
                data = await asyncio.wait_for(self._reader.readexactly(FRAME_LEN), self.timeout)
            except asyncio.IncompleteReadError as err:
                if err.partial:
                    self.stats.invalid_length += 1
                else:
                    self.stats.connection_errors += 1
                await self.close()
                raise SemTcpConnectionError(
                    f"connection closed after {len(err.partial)} of {FRAME_LEN} bytes"
                ) from err
            except TimeoutError as err:
                self.stats.timeouts += 1
                await self.close()
                raise SemTcpTimeout(f"no answer within {self.timeout} s") from err
            except OSError as err:
                self.stats.connection_errors += 1
                await self.close()
                raise SemTcpConnectionError(str(err) or type(err).__name__) from err

            frame = parse_frame(data)
            if not frame.checksum_ok:
                self.stats.invalid_checksum += 1
                # A bad frame may mean the stream is out of step; start over.
                await self.close()
                raise InvalidFrameError("checksum", "frame checksum mismatch")
            if self.expected_id is not None and frame.meter_id != self.expected_id:
                self.stats.invalid_id += 1
                await self.close()
                raise InvalidFrameError(
                    "id", f"frame from meter {frame.meter_id!r}, expected {self.expected_id!r}"
                )
            if self.expected_id is None:
                self.expected_id = frame.meter_id
            self.stats.frames_ok += 1
            return frame

    async def _connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except TimeoutError as err:
            self.stats.timeouts += 1
            raise SemTcpTimeout(f"connect to {self.host}:{self.port} timed out") from err
        except OSError as err:
            self.stats.connection_errors += 1
            raise SemTcpConnectionError(
                f"connect to {self.host}:{self.port} failed: {err or type(err).__name__}"
            ) from err
        self.stats.connects += 1
        _LOGGER.debug("Connected to %s:%s", self.host, self.port)

    async def close(self) -> None:
        """Close the connection; the next request reconnects."""
        writer, self._reader, self._writer = self._writer, None, None
        if writer is None:
            return
        writer.close()
        with suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), 1.0)


async def probe(
    host: str,
    port: int = DEFAULT_TCP_PORT,
    *,
    expected_id: str | None = None,
    timeout: float = READ_TIMEOUT,
) -> SemFrame:
    """Connect once, read one valid frame and disconnect."""
    client = SemTcpClient(host, port, expected_id=expected_id, timeout=timeout)
    try:
        return await client.request()
    finally:
        await client.close()


class SemTcpPoller:
    """Polls a SemTcpClient at a fixed interval and reconnects with backoff.

    Only valid frames reach ``on_frame``. ``on_error(err, failures, delay)`` is told
    about every failure before the backoff delay starts.
    """

    def __init__(
        self,
        client: SemTcpClient,
        interval: float = DEFAULT_TCP_INTERVAL,
        *,
        on_frame: Callable[[SemFrame], None],
        on_error: Callable[[Exception, int, float], None] | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.interval = max(float(interval), MIN_TCP_INTERVAL)
        self._on_frame = on_frame
        self._on_error = on_error
        self._sleep = sleep
        self._clock = clock

    async def run(self) -> None:
        """Poll until cancelled. The connection is closed on exit."""
        failures = 0
        try:
            while True:
                started = self._clock()
                try:
                    frame = await self.client.request()
                except SemTcpError as err:
                    failures += 1
                    await self.client.close()
                    delay = backoff_delay(failures)
                    self._notify_error(err, failures, delay)
                    await self._sleep(delay)
                    continue
                failures = 0
                try:
                    self._on_frame(frame)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Error in frame callback")
                elapsed = self._clock() - started
                await self._sleep(max(self.interval - elapsed, 0.0))
        finally:
            await self.client.close()

    def _notify_error(self, err: Exception, failures: int, delay: float) -> None:
        if self._on_error is None:
            _LOGGER.debug("Port %s request failed (%s), retry in %.0f s", self.client.port, err, delay)
            return
        try:
            self._on_error(err, failures, delay)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Error in error callback")
