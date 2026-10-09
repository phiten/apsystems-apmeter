"""Frame builder and a fake APmeter SEM TCP server for tests (127.0.0.1 only)."""

from __future__ import annotations

import asyncio
import struct

FAKE_METER_ID = "M01234567890"
H1 = 259764
H2 = 2


def build_frame(
    l1: float = 100.0,
    l2: float = -50.0,
    l3: float = 25.0,
    total: float = 75.0,
    meter_id: str = FAKE_METER_ID,
    *,
    checksum: float | None = None,
    h1: int = H1,
    h2: int = H2,
) -> bytes:
    """Build a 44-byte response frame like the meter sends it."""
    if checksum is None:
        checksum = h1 + h2 + l1 + l2 + l3 + total
    raw_id = meter_id.encode("latin1")[:16]
    return (
        struct.pack("<II", h1, h2)
        + struct.pack("<5f", l1, l2, l3, total, checksum)
        + raw_id.ljust(16, b"\0")
    )


class FakeSemServer:
    """TCP server that answers the 4-byte request with scripted behaviour.

    Each received request consumes one action from ``script``; when the script is
    empty, a valid frame is sent. Actions:
      "ok"           valid frame
      "split"        valid frame in several small TCP segments
      "bad_checksum" frame with a wrong checksum
      "other_id"     valid frame from a different meter
      "partial"      first 20 bytes, then close the connection
      "close"        close the connection without answering
      "silent"       never answer
    """

    def __init__(self, script: list[str] | None = None, frame: bytes | None = None) -> None:
        self.script = list(script or [])
        self.frame = frame or build_frame()
        self.requests: list[bytes] = []
        self.connections = 0
        self.open_connections = 0
        self.max_open_connections = 0
        self.disconnected = asyncio.Event()
        self._server: asyncio.base_events.Server | None = None
        self.port = 0

    async def __aenter__(self) -> FakeSemServer:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        self.open_connections += 1
        self.max_open_connections = max(self.max_open_connections, self.open_connections)
        try:
            while True:
                try:
                    request = await reader.readexactly(4)
                except (asyncio.IncompleteReadError, ConnectionError):
                    return
                self.requests.append(request)
                action = self.script.pop(0) if self.script else "ok"
                if action == "ok":
                    writer.write(self.frame)
                elif action == "split":
                    for start, end in ((0, 3), (3, 17), (17, 30), (30, 44)):
                        writer.write(self.frame[start:end])
                        await writer.drain()
                        await asyncio.sleep(0.01)
                elif action == "bad_checksum":
                    writer.write(build_frame(checksum=1.0))
                elif action == "other_id":
                    writer.write(build_frame(meter_id="M09999999999"))
                elif action == "partial":
                    writer.write(self.frame[:20])
                    await writer.drain()
                    return
                elif action == "close":
                    return
                elif action == "silent":
                    # Never answer; return once the client gives up and disconnects.
                    await reader.read()
                    return
                else:  # pragma: no cover - test bug
                    raise AssertionError(f"unknown action {action}")
                await writer.drain()
        finally:
            self.open_connections -= 1
            writer.close()
            self.disconnected.set()


class FakeSleep:
    """Records requested delays instead of waiting (still yields to the loop)."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.calls.append(delay)
        await asyncio.sleep(0)


async def wait_for(condition, timeout: float = 5.0) -> None:
    """Poll ``condition`` until it is true or fail after ``timeout`` seconds."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


async def unused_port() -> int:
    """Return a localhost port with nothing listening on it."""
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    return port
