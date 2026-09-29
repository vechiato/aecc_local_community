"""Run: python3 tests/test_tcp_transport.py (no Home Assistant needed).

Drives the real client against a local asyncio TCP server.
"""
import asyncio
import importlib
import json
import sys
import types
from pathlib import Path

# Import the transport modules without running the package __init__ (needs HA).
_pkg = types.ModuleType("aecc")
_pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components/aecc_local_community")]
sys.modules["aecc"] = _pkg
tcp_client = importlib.import_module("aecc.tcp_client")
tcp_manager = importlib.import_module("aecc.tcp_manager")
tcp_client._REPLY_TIMEOUT = 0.3


def reply(req, **extra):
    return (json.dumps({"SerialNumber": req["SerialNumber"], "Echo": req.get("Get") or req.get("Set"), **extra}) + "\n").encode()


async def serve(handler):
    """Start a server whose per-connection logic is handler(requests, writer)."""
    conns = []

    async def on_conn(reader, writer):
        conns.append(writer)
        queue = asyncio.Queue()

        async def pump():
            while line := await reader.readline():
                await queue.put(json.loads(line))
        pump_task = asyncio.create_task(pump())
        try:
            await handler(queue, writer)
        finally:
            pump_task.cancel()

    server = await asyncio.start_server(on_conn, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    tcp_manager.TCPClientManager._connections.clear()
    return server, port, conns


async def test_late_reply_is_discarded():
    async def handler(q, w):
        first = await q.get()
        await asyncio.sleep(0.5)  # miss the client's timeout
        second = await q.get()
        stale = reply(first)
        w.write(stale[:10])  # partial frame first, rest together with the real reply
        await w.drain()
        await asyncio.sleep(0.05)
        w.write(stale[10:] + reply(second, Ok=1))
        await w.drain()
        await asyncio.sleep(1)

    server, port, _ = await serve(handler)
    c = tcp_client.AECCDeviceClient("127.0.0.1", port)
    assert await c.fetch_data() is None
    got = await c.get_control_parameters([3023])
    assert got["SerialNumber"] == 2 and got["Ok"] == 1, got
    await c.disconnect()
    server.close()


async def test_concurrent_requests_do_not_cross():
    async def handler(q, w):
        while True:
            req = await q.get()
            await asyncio.sleep(0.02)
            w.write(reply(req))
            await w.drain()

    server, port, _ = await serve(handler)
    c = tcp_client.AECCDeviceClient("127.0.0.1", port)
    a, b = await asyncio.gather(c.fetch_data(), c.set_control_parameters({"3023": "10"}))
    assert a["Echo"] == "EnergyParameter" and b["Echo"] == "Energycontrolparameters", (a, b)
    await c.disconnect()
    server.close()


async def test_silent_socket_is_recycled():
    async def handler(q, w):
        await asyncio.sleep(10)  # accept requests, never answer

    server, port, conns = await serve(handler)
    c = tcp_client.AECCDeviceClient("127.0.0.1", port)
    for _ in range(tcp_manager.READ_TIMEOUT_SUSPECT_THRESHOLD):
        assert await c.fetch_data() is None
    assert c.tcp_manager.writer is None  # closed after the 3rd silent read
    await c.fetch_data()
    assert len(conns) == 2  # next request opened a fresh socket
    await c.disconnect()
    server.close()


def test_backoff():
    m = tcp_manager.TCPClientManager("h", 1)
    seen = []
    for _ in range(8):
        seen.append(m.current_cooldown())
        m.note_failure()
    assert seen == [2, 4, 8, 16, 32, 60, 60, 60], seen
    m.note_success()
    assert m.current_cooldown() == 2


async def test_refused_connection_returns_none():
    tcp_manager.TCPClientManager._connections.clear()
    tcp_manager.RECONNECT_BASE_COOLDOWN = 0.01
    c = tcp_client.AECCDeviceClient("127.0.0.1", 1)  # nothing listens on port 1
    assert await c.fetch_data() is None
    assert c.tcp_manager.consecutive_failures == 1
    tcp_manager.RECONNECT_BASE_COOLDOWN = 2.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            result = fn()
            if asyncio.iscoroutine(result):
                asyncio.run(result)
    print("ok")
