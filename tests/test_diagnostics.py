"""Run: python3 tests/test_diagnostics.py (no Home Assistant needed; HA is stubbed)."""
import asyncio
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

for name in ("homeassistant", "homeassistant.components", "homeassistant.components.diagnostics",
             "homeassistant.config_entries", "homeassistant.core", "homeassistant.loader",
             "homeassistant.util", "homeassistant.util.dt", "homeassistant.helpers",
             "homeassistant.helpers.update_coordinator"):
    sys.modules[name] = MagicMock()


async def _version(hass, domain):
    return types.SimpleNamespace(version="9.9.9")


sys.modules["homeassistant.loader"].async_get_integration = _version
_pkg = types.ModuleType("aecc")
_pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components/aecc_local_community")]
sys.modules["aecc"] = _pkg
diagnostics = importlib.import_module("aecc.diagnostics")


def test_unloaded_entry_does_not_crash():
    hass = types.SimpleNamespace(data={})  # integration never set up for this entry
    entry = types.SimpleNamespace(entry_id="x", state=types.SimpleNamespace(value="not_loaded"),
                                  disabled_by="user")
    out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))
    assert out["integration"]["version"] == "9.9.9"
    assert out["entry"] == {"state": "not_loaded", "disabled_by": "user"}


if __name__ == "__main__":
    test_unloaded_entry_does_not_crash()
    print("ok")
