"""Run: python3 tests/test_battery_power.py (no Home Assistant needed; HA is mocked)."""
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

for name in ("homeassistant", "homeassistant.components", "homeassistant.components.sensor",
             "homeassistant.helpers", "homeassistant.helpers.entity_registry", "homeassistant.helpers.entity",
             "homeassistant.helpers.update_coordinator", "homeassistant.helpers.restore_state",
             "homeassistant.core", "homeassistant.util", "homeassistant.const"):
    sys.modules[name] = MagicMock()
# Entity base classes must be real classes to subclass.
sys.modules["homeassistant.components.sensor"].SensorEntity = type("SensorEntity", (), {})
sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = type("CoordinatorEntity", (), {})
sys.modules["homeassistant.helpers.restore_state"].RestoreEntity = type("RestoreEntity", (), {})
_pkg = types.ModuleType("aecc")
_pkg.__path__ = [str(Path(__file__).parents[1] / "custom_components/aecc_local_community")]
sys.modules["aecc"] = _pkg
sensor = importlib.import_module("aecc.sensor")


def test_battery_power_from_energy_balance():
    # Real PS240 poll: PV 217 W, 392 W out of the grid socket -> discharging 175 W.
    summary = {"TotalPVPower": 217, "TotalGridOutputPower": 392, "TotalBackUpPower": 0,
               "TotalBatteryOutputPower": 258, "TotalChargePower": 0}
    assert sensor.battery_power_w(summary) == -175.0
    # Grid charging: the grid socket runs backwards.
    assert sensor.battery_power_w({"TotalPVPower": 0, "TotalGridOutputPower": -2000}) == 2000.0
    # Backup load is a way out too, not charge.
    assert sensor.battery_power_w({"TotalPVPower": 500, "TotalGridOutputPower": 0, "TotalBackUpPower": 300}) == 200.0
    assert sensor.battery_power_w({"TotalPVPower": 500}) is None
    assert sensor.battery_power_w(None) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
