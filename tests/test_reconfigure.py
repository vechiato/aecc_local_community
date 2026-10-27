"""Run: python3 tests/test_reconfigure.py (no Home Assistant needed; HA is stubbed)."""
import asyncio
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

for name in ("homeassistant", "homeassistant.config_entries", "homeassistant.helpers",
             "homeassistant.helpers.service_info", "homeassistant.helpers.service_info.zeroconf", "voluptuous"):
    sys.modules[name] = MagicMock()


class _Flow:
    def __init_subclass__(cls, **kwargs):
        pass

    def async_show_form(self, **kw):
        return {"type": "form", **kw}

    def async_update_reload_and_abort(self, entry, data_updates):
        return {"type": "abort", "data_updates": data_updates}


sys.modules["homeassistant.config_entries"].ConfigFlow = _Flow
sys.modules["homeassistant.config_entries"].OptionsFlow = object
sys.modules["homeassistant"].config_entries = sys.modules["homeassistant.config_entries"]
_pkg = types.ModuleType("aecc")
_pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components/aecc_local_community")]
sys.modules["aecc"] = _pkg
flow_mod = importlib.import_module("aecc.config_flow")


def run(reply, ip="192.168.0.50"):
    class Client:
        def __init__(self, host, port):
            pass

        async def fetch_data(self):
            return reply

        async def disconnect(self):
            pass

    flow_mod.AECCDeviceClient = Client
    flow = flow_mod.AeccLocalPluginConfigFlow()
    entry = types.SimpleNamespace(data={"device_sn": "SN1", "device_ip": "192.168.0.219", "device_port": 8080})
    flow._get_reconfigure_entry = lambda: entry
    return asyncio.run(flow.async_step_reconfigure({"device_ip": f" {ip} ", "device_port": 8080}))


def test_reconfigure():
    ok = run({"Storage_list": [{"StorageSN": "SN1"}, {"StorageSN": "SN2"}]})
    assert ok["type"] == "abort"
    assert ok["data_updates"] == {"host": "192.168.0.50", "device_ip": "192.168.0.50", "port": 8080, "device_port": 8080}
    assert run(None)["errors"] == {"base": "cannot_connect"}
    assert run({"Storage_list": [{"StorageSN": "OTHER"}]})["errors"] == {"base": "wrong_device"}
    assert run({"PlugInfoList": []})["type"] == "abort"  # no storage list: nothing to cross-check


if __name__ == "__main__":
    test_reconfigure()
    print("ok")
