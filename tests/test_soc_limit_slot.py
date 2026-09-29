"""Run: python3 tests/test_soc_limit_slot.py (no Home Assistant needed; HA is stubbed)."""
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


class FakeClient:
    def __init__(self):
        self.writes = []

    async def set_control_parameters(self, payload):
        self.writes.append(dict(payload))
        return {"ok": 1}

    async def get_control_parameters(self, regs):
        last = self.writes[-1]
        return {"ControlInfo": {r: last.get(r) for r in last}}


def make():
    c = coordinator.AECCDataUpdateCoordinator(None, "h", 1)
    c.client = FakeClient()
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            asyncio.run(fn())
    print("ok")
