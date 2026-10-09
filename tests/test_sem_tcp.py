"""Tests for the APmeter SEM port-3333 protocol module."""

from __future__ import annotations

import asyncio
import math

import pytest

from sem_fakes import FAKE_METER_ID, FakeSemServer, FakeSleep, build_frame, unused_port, wait_for
from sem_tcp import (
    FRAME_LEN,
    MIN_TCP_INTERVAL,
    REQUEST,
    FrameError,
    InvalidFrameError,
    SemFrame,
    SemTcpClient,
    SemTcpConnectionError,
    SemTcpPoller,
    SemTcpTimeout,
    backoff_delay,
    check_meter_id,
    is_device_identity,
    is_fresh,
    parse_frame,
    probe,
)


# --- parse_frame -------------------------------------------------------------


def test_constants_match_protocol() -> None:
    assert REQUEST == bytes.fromhex("02040113")
    assert FRAME_LEN == 44
    assert MIN_TCP_INTERVAL == 0.5


def test_parse_valid_frame() -> None:
    frame = parse_frame(build_frame(l1=812.5, l2=-120.25, l3=33.0, total=727.0))
    assert frame.l1 == 812.5
    assert frame.l2 == -120.25
    assert frame.l3 == 33.0
    assert frame.p == 727.0
    assert frame.meter_id == FAKE_METER_ID
    assert frame.checksum_ok


def test_parse_uses_total_not_sum_of_phases() -> None:
    # The meter reads the registers separately, so total may differ from L1+L2+L3.
    frame = parse_frame(build_frame(l1=100.0, l2=100.0, l3=100.0, total=303.0))
    assert frame.p == 303.0


@pytest.mark.parametrize("length", [0, 4, 43, 45, 88])
def test_parse_wrong_length(length: int) -> None:
    data = (build_frame() * 2)[:length]
    with pytest.raises(FrameError):
        parse_frame(data)


def test_frame_error_is_value_error() -> None:
    assert issubclass(FrameError, ValueError)


def test_parse_bad_checksum() -> None:
    frame = parse_frame(build_frame(checksum=12345.0))
    assert not frame.checksum_ok


def test_parse_checksum_tolerance() -> None:
    exact = 259764 + 2  # header constants, all power values zero
    assert parse_frame(build_frame(l1=0, l2=0, l3=0, total=0, checksum=exact + 0.0625)).checksum_ok
    assert not parse_frame(build_frame(l1=0, l2=0, l3=0, total=0, checksum=exact + 0.25)).checksum_ok


def test_parse_non_finite_values_fail_checksum() -> None:
    frame = parse_frame(build_frame(l1=math.nan, checksum=259766.0))
    assert not frame.checksum_ok
    frame = parse_frame(build_frame(l2=math.inf, checksum=math.inf))
    assert not frame.checksum_ok


def test_parse_meter_id_padding() -> None:
    assert parse_frame(build_frame(meter_id="M0123")).meter_id == "M0123"
    # A 16-character ID has no terminating zero byte.
    assert parse_frame(build_frame(meter_id="M012345678901234")).meter_id == "M012345678901234"


# --- helpers -----------------------------------------------------------------


def test_backoff_sequence() -> None:
    assert [backoff_delay(n) for n in range(1, 9)] == [1, 2, 4, 8, 16, 30, 30, 30]


def test_is_fresh() -> None:
    assert not is_fresh(None, 100.0)
    assert is_fresh(100.0, 100.0)
    assert is_fresh(100.0, 109.9)
    assert not is_fresh(100.0, 110.0)
    assert not is_fresh(100.0, 150.0)
    assert is_fresh(100.0, 103.0, max_age=5.0)


@pytest.mark.parametrize(
    ("device_id", "expected"),
    [(FAKE_METER_ID, True), (None, False), ("", False), ("Unknown", False), ("192.0.2.10", False), ("2001:db8::1", False)],
)
def test_is_device_identity(device_id: str | None, expected: bool) -> None:
    assert is_device_identity(device_id) is expected


@pytest.mark.parametrize(
    ("frame_id", "device_id", "expected"),
    [
        (FAKE_METER_ID, FAKE_METER_ID, True),
        (FAKE_METER_ID, " m01234567890 ", True),
        (FAKE_METER_ID, "M09999999999", False),
        (FAKE_METER_ID, None, None),
        (FAKE_METER_ID, "", None),
        (FAKE_METER_ID, "unknown", None),
        (FAKE_METER_ID, "192.0.2.10", None),
        ("", FAKE_METER_ID, False),
    ],
)
def test_check_meter_id(frame_id: str, device_id: str | None, expected: bool | None) -> None:
    assert check_meter_id(frame_id, device_id) is expected


# --- client ------------------------------------------------------------------


async def test_client_sends_exact_request_and_reads_frame() -> None:
    async with FakeSemServer() as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        try:
            frame = await client.request()
        finally:
            await client.close()
    assert isinstance(frame, SemFrame)
    assert frame.p == 75.0
    assert server.requests == [REQUEST]
    assert client.stats.frames_ok == 1


async def test_client_reuses_one_connection() -> None:
    async with FakeSemServer() as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        try:
            for _ in range(5):
                await client.request()
        finally:
            await client.close()
    assert server.connections == 1
    assert server.requests == [REQUEST] * 5
    assert client.stats.connects == 1


async def test_client_handles_split_segments() -> None:
    async with FakeSemServer(script=["split", "split"]) as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        try:
            first = await client.request()
            second = await client.request()
        finally:
            await client.close()
    assert first.p == second.p == 75.0
    assert server.connections == 1


async def test_client_rejects_bad_checksum_and_recovers() -> None:
    async with FakeSemServer(script=["bad_checksum"]) as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        try:
            with pytest.raises(InvalidFrameError) as err:
                await client.request()
            assert err.value.reason == "checksum"
            assert client.stats.invalid_checksum == 1
            assert client.stats.frames_ok == 0
            frame = await client.request()
        finally:
            await client.close()
    assert frame.checksum_ok
    # The stream is resynchronised by reconnecting.
    assert server.connections == 2


async def test_client_rejects_wrong_meter_id() -> None:
    async with FakeSemServer(script=["other_id"]) as server:
        client = SemTcpClient("127.0.0.1", server.port, expected_id=FAKE_METER_ID, sleep=FakeSleep())
        try:
            with pytest.raises(InvalidFrameError) as err:
                await client.request()
            assert err.value.reason == "id"
            assert client.stats.invalid_id == 1
            assert (await client.request()).meter_id == FAKE_METER_ID
        finally:
            await client.close()


async def test_client_locks_on_first_meter_id() -> None:
    async with FakeSemServer(script=["ok", "other_id"]) as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        try:
            await client.request()
            assert client.expected_id == FAKE_METER_ID
            with pytest.raises(InvalidFrameError):
                await client.request()
        finally:
            await client.close()


async def test_client_connection_closed_mid_frame() -> None:
    async with FakeSemServer(script=["partial"]) as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        try:
            with pytest.raises(SemTcpConnectionError):
                await client.request()
            assert client.stats.invalid_length == 1
            assert not client.connected
            frame = await client.request()
        finally:
            await client.close()
    assert frame.checksum_ok
    assert server.connections == 2
    assert client.stats.connects == 2


async def test_client_connection_closed_without_answer() -> None:
    async with FakeSemServer(script=["close"]) as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        try:
            with pytest.raises(SemTcpConnectionError):
                await client.request()
            assert (await client.request()).checksum_ok
        finally:
            await client.close()


async def test_client_timeout() -> None:
    async with FakeSemServer(script=["silent"]) as server:
        client = SemTcpClient("127.0.0.1", server.port, timeout=0.2, sleep=FakeSleep())
        try:
            with pytest.raises(SemTcpTimeout):
                await client.request()
            assert client.stats.timeouts == 1
            assert not client.connected
        finally:
            await client.close()


def test_timeout_is_connection_error() -> None:
    assert issubclass(SemTcpTimeout, SemTcpConnectionError)


def test_client_default_timeout() -> None:
    assert SemTcpClient("192.0.2.10").timeout == 3.0


async def test_client_connection_refused() -> None:
    port = await unused_port()
    client = SemTcpClient("127.0.0.1", port, timeout=0.3, sleep=FakeSleep())
    with pytest.raises(SemTcpConnectionError):
        await client.request()
    assert client.stats.connection_errors + client.stats.timeouts == 1


async def test_client_enforces_minimum_spacing() -> None:
    sleep = FakeSleep()
    async with FakeSemServer() as server:
        client = SemTcpClient("127.0.0.1", server.port, min_interval=0.01, sleep=sleep)
        try:
            await client.request()
            await client.request()
        finally:
            await client.close()
    # min_interval is clamped to 0.5 s, so the second request had to wait.
    assert len(sleep.calls) == 1
    assert 0.4 < sleep.calls[0] <= MIN_TCP_INTERVAL


async def test_client_requests_are_serialised() -> None:
    async with FakeSemServer(script=["split", "split", "split"]) as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        try:
            frames = await asyncio.gather(*(client.request() for _ in range(3)))
        finally:
            await client.close()
    assert all(f.checksum_ok for f in frames)
    assert server.connections == 1


# --- probe -------------------------------------------------------------------


async def test_probe_returns_frame_and_disconnects() -> None:
    async with FakeSemServer() as server:
        frame = await probe("127.0.0.1", server.port)
        await asyncio.wait_for(server.disconnected.wait(), 2)
    assert frame.meter_id == FAKE_METER_ID
    assert server.requests == [REQUEST]


async def test_probe_invalid_frame() -> None:
    async with FakeSemServer(script=["bad_checksum"]) as server:
        with pytest.raises(InvalidFrameError):
            await probe("127.0.0.1", server.port)


async def test_probe_unreachable() -> None:
    port = await unused_port()
    with pytest.raises(SemTcpConnectionError):
        await probe("127.0.0.1", port, timeout=0.3)


# --- poller ------------------------------------------------------------------


def test_poller_clamps_interval() -> None:
    client = SemTcpClient("192.0.2.10")
    assert SemTcpPoller(client, 0.1, on_frame=lambda f: None).interval == MIN_TCP_INTERVAL
    assert SemTcpPoller(client, 2.0, on_frame=lambda f: None).interval == 2.0


async def test_poller_delivers_frames_at_interval() -> None:
    sleep = FakeSleep()
    frames: list[SemFrame] = []
    async with FakeSemServer() as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        poller = SemTcpPoller(client, 1.0, on_frame=frames.append, sleep=sleep)
        task = asyncio.create_task(poller.run())
        try:
            await wait_for(lambda: len(frames) >= 3)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await asyncio.wait_for(server.disconnected.wait(), 2)
    assert server.connections == 1
    assert server.max_open_connections == 1
    # Pacing sleeps fill up the remaining interval and never exceed it.
    pacing = sleep.calls[:2]
    assert all(0.9 <= d <= 1.0 for d in pacing)
    assert not client.connected


async def test_poller_reconnects_with_backoff_and_drops_invalid_frames() -> None:
    sleep = FakeSleep()
    frames: list[SemFrame] = []
    errors: list[tuple[Exception, int, float]] = []
    script = ["ok", "close", "partial", "bad_checksum", "ok"]
    async with FakeSemServer(script=script) as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        poller = SemTcpPoller(
            client,
            1.0,
            on_frame=frames.append,
            on_error=lambda err, n, delay: errors.append((err, n, delay)),
            sleep=sleep,
        )
        task = asyncio.create_task(poller.run())
        try:
            await wait_for(lambda: len(frames) >= 2)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert all(f.checksum_ok for f in frames)
    assert [n for _, n, _ in errors] == [1, 2, 3]
    assert [d for _, _, d in errors] == [1, 2, 4]
    assert isinstance(errors[2][0], InvalidFrameError)
    assert client.stats.invalid_checksum == 1
    assert client.stats.invalid_length == 1
    # Each failure closed the connection; the next request opened a new one.
    assert server.connections == 4
    assert server.max_open_connections == 1
    for delay in (1, 2, 4):
        assert delay in sleep.calls


async def test_poller_backoff_caps_at_30s_when_unreachable() -> None:
    sleep = FakeSleep()
    errors: list[float] = []
    port = await unused_port()
    client = SemTcpClient("127.0.0.1", port, timeout=0.3, sleep=FakeSleep())
    poller = SemTcpPoller(
        client,
        1.0,
        on_frame=lambda f: pytest.fail("no frame expected"),
        on_error=lambda err, n, delay: errors.append(delay),
        sleep=sleep,
    )
    task = asyncio.create_task(poller.run())
    try:
        await wait_for(lambda: len(errors) >= 7, timeout=20)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert errors[:7] == [1, 2, 4, 8, 16, 30, 30]


async def test_poller_survives_callback_exception() -> None:
    sleep = FakeSleep()
    calls = 0

    def on_frame(frame: SemFrame) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    async with FakeSemServer() as server:
        client = SemTcpClient("127.0.0.1", server.port, sleep=FakeSleep())
        task = asyncio.create_task(SemTcpPoller(client, 1.0, on_frame=on_frame, sleep=sleep).run())
        try:
            await wait_for(lambda: calls >= 2)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert server.connections == 1
