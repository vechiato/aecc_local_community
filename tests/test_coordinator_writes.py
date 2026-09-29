"""Run: python3 tests/test_coordinator_writes.py (no Home Assistant needed; HA is stubbed)."""
import asyncio
import importlib
import sys
import types
from pathlib import Path

# Minimal HA stubs, just enough to import the coordinator.
for name in ("homeassistant", "homeassistant.util", "homeassistant.helpers",
             "homeassistant.util.dt", "homeassistant.helpers.update_coordinator"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["homeassistant.util"].dt = sys.modules["homeassistant.util.dt"]


class _Coordinator:
    def __init__(self, *args, **kwargs):
        self.data = None


sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = _Coordinator
_pkg = types.ModuleType("aecc")
_pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components/aecc_local_community")]
sys.modules["aecc"] = _pkg
coordinator = importlib.import_module("aecc.coordinator")
const = importlib.import_module("aecc.const")
coordinator._WRITE_VERIFY_DELAY = 0
coordinator._WRITE_RETRY_DELAY = 0


class FakeClient:
    def __init__(self, drop=0, streak=0, delay=0.0):
        self.writes = []
        self.drop = drop  # how many sends come back unconfirmed first
        self.delay = delay
        self.tcp_manager = types.SimpleNamespace(consecutive_failures=streak)

    async def set_control_parameters(self, payload):
        self.writes.append(dict(payload))
        await asyncio.sleep(self.delay)
        if self.drop:
            self.drop -= 1
            return None
        return {"ok": 1}

    async def get_control_parameters(self, regs):
        last = self.writes[-1]
        return {"ControlInfo": {r: last.get(r) for r in last}}


def make(**client_kwargs):
    c = coordinator.AECCDataUpdateCoordinator(None, "h", 1)
    c.client = FakeClient(**client_kwargs)
    return c


async def test_limit_change_during_charge_resends_slot():
    c = make()
    assert await c.async_set_battery_control("Charge", 600)
    c.commanded_charge_power = 300  # passive slider moved; must not reach the device
    assert await c.async_set_max_soc(90)
    last = c.client.writes[-1]
    assert last[const.REG_MAX_SOC] == "90"
    assert last[const.REG_CONTROL_TIME1] == "1,00:00,23:59,-600,0,6,4,0,0,90,10", last


async def test_limit_change_during_discharge_carries_new_floor():
    c = make()
    assert await c.async_set_battery_control("Discharge", 500)
    assert await c.async_set_min_soc(25)
    assert c.client.writes[-1][const.REG_CONTROL_TIME1] == "1,00:00,23:59,500,0,6,4,0,0,98,25"


async def test_no_slot_when_not_under_manual_control():
    c = make()
    assert await c.async_set_min_soc(20)  # startup / Self-Gen: AI owns the slot
    assert const.REG_CONTROL_TIME1 not in c.client.writes[-1]
    assert await c.async_set_battery_control("Idle", 0)
    assert await c.async_set_max_soc(95)
    assert const.REG_CONTROL_TIME1 not in c.client.writes[-1]
    assert await c.async_set_battery_control("Charge", 600)
    assert await c.async_restore_self_consumption()
    assert await c.async_set_max_soc(80)
    assert const.REG_CONTROL_TIME1 not in c.client.writes[-1]


async def test_unconfirmed_write_is_resent():
    c = make(drop=1)
    assert await c.async_set_min_soc(20)
    assert len(c.client.writes) == 2
    assert c.write_history[-1]["attempts"] == 2 and c.write_history[-1]["response_received"]


async def test_gives_up_after_two_retries():
    c = make(drop=5)
    assert not await c.async_set_min_soc(20)
    assert len(c.client.writes) == 3
    assert c.write_history[-1]["attempts"] == 3


async def test_no_retry_during_outage():
    c = make(drop=5, streak=3)
    assert not await c.async_set_min_soc(20)
    assert len(c.client.writes) == 1


async def test_writes_serialize_and_superseded_verify_is_skipped():
    c = make(drop=1, delay=0.01)
    await asyncio.gather(c.async_set_min_soc(20), c.async_set_min_soc(30))
    # First write's retry landed before the second write: last value wins.
    assert [w[const.REG_MIN_SOC] for w in c.client.writes] == ["20", "20", "30"]
    first, second = c.write_history[-2:]
    assert first["verify_skipped"] == "superseded" and first["verify_result"] is None
    assert "verify_skipped" not in second and second["verify_result"]


class RssiClient:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    async def get_wifi_rssi(self):
        self.calls += 1
        return self.values.pop(0)


async def test_wifi_rssi_not_refreshed_when_unsupported():
    c = make()
    c.client = RssiClient([None])
    await c.async_probe_wifi_rssi()
    c._last_rssi_refresh -= 120
    await c._maybe_refresh_wifi_rssi()
    assert c.wifi_rssi is None and c.client.calls == 1


async def test_wifi_rssi_refresh_throttled_and_keeps_last_on_failure():
    c = make()
    c.client = RssiClient([-60, -55, None])
    await c.async_probe_wifi_rssi()
    await c._maybe_refresh_wifi_rssi()  # within 60s: skipped
    assert c.client.calls == 1
    c._last_rssi_refresh -= 61
    await c._maybe_refresh_wifi_rssi()
    assert c.wifi_rssi == -55
    c._last_rssi_refresh -= 61
    await c._maybe_refresh_wifi_rssi()  # failed read keeps the last value
    assert c.wifi_rssi == -55 and c.client.calls == 3


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            asyncio.run(fn())
    print("ok")
