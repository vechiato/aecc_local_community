"""Run: python3 tests/test_modbus_telemetry.py (no Home Assistant needed).

Drives the real Modbus read against a local asyncio TCP server.
"""
import asyncio
import importlib
import struct
import sys
import types
from pathlib import Path

_pkg = types.ModuleType("aecc")
_pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components/aecc_local_community")]
sys.modules["aecc"] = _pkg
tcp_client = importlib.import_module("aecc.tcp_client")
tcp_manager = importlib.import_module("aecc.tcp_manager")
tcp_client._MODBUS_TIMEOUT = 0.3

# Captured from a PS240 on 2026-11-21.
PS240_BLOCK = [13, 65521, 0, 3200, 0, 1200, 24, 4000, 1, 0, 0, 0, 0, 0, 0, 1, 63263, 0, 0, 0, 0, 0, 0]


async def serve(answer):
    """Server answering one Modbus request per connection: words, an exception code, or nothing."""
    async def on_conn(reader, writer):
        tid, _proto, _len, unit, fc, start, count = struct.unpack(">HHHBBHH", await reader.readexactly(12))
        if isinstance(answer, list):
            body = struct.pack(">BBB", unit, fc, 2 * count) + struct.pack(f">{count}H", *answer)
        elif isinstance(answer, int):
            body = struct.pack(">BBB", unit, fc | 0x80, answer)
        else:
            await asyncio.sleep(1)  # silent
            body = b""
        if body:
            writer.write(struct.pack(">HHH", tid, 0, len(body)) + body)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(on_conn, "127.0.0.1", 0)
    tcp_manager.TCPClientManager._connections.clear()
    return server, server.sockets[0].getsockname()[1]


async def read(answer):
    server, port = await serve(answer)
    async with server:
        return await tcp_client.AECCDeviceClient("127.0.0.1", port).get_telemetry()


def test_decode_ps240_block():
    t = tcp_client.decode_telemetry(PS240_BLOCK)
    assert t == {"fault": 0, "alarm_flags": 0, "nominal_power": 1200,
                 "reg_65030": 13, "reg_65031": -15, "reg_65036": 24}, t


def test_alarm_flags_low_word_first():
    words = list(PS240_BLOCK)
    words[65051 - 65030], words[65052 - 65030] = 0x0002, 0x0001
    assert tcp_client.decode_telemetry(words)["alarm_flags"] == 0x00010002


async def test_reads_block_over_tcp():
    t = await read(PS240_BLOCK)
    assert t["nominal_power"] == 1200 and t["fault"] == 0


async def test_refused_or_silent_is_none():
    assert await read(4) is None  # exception 4, as the PS240 answers unsupported blocks
    assert await read(None) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            r = fn()
            if asyncio.iscoroutine(r):
                asyncio.run(r)
    print("ok")
