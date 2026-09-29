"""Run: python3 tests/test_storage_frames.py (no Home Assistant needed)."""
import importlib.util
import sys
from pathlib import Path

_path = Path(__file__).parents[1] / "custom_components/aecc_local_community/cleaners.py"
_spec = importlib.util.spec_from_file_location("cleaners", _path)
c = sys.modules["cleaners"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)


def frame(*units):
    return {"Storage_list": [dict(u) for u in units]}


A = {"StorageSN": "A", "BatterySoc": 60, "StorageStatus": 1}
B = {"StorageSN": "B", "BatterySoc": 55, "StorageStatus": 1}


def soc(raw, *, elapsed, last=None, power=0.0):
    return c.clean_soc(c.CleanerContext(
        key="k", raw_value=raw, last_accepted_value=last,
        last_accepted_at=0.0 if last is not None else None, now=elapsed,
        wall_power_w=power, profile=c.DEFAULT_PROFILE, seconds_since_first_poll=elapsed,
    ))


def test_startup_zero_soc_window():
    assert soc(0, elapsed=0) is None  # warm-up frame withheld
    assert soc(0, elapsed=20) is None  # measured warm-up still reporting 0 after several polls
    assert soc(0, elapsed=60) == 0  # genuinely empty pack publishes after the window
    assert soc(12, elapsed=0) == 12  # real value accepted immediately
    assert soc(0, elapsed=30, last=1) == 0  # once a value is accepted, a slow 1%->0% passes


def test_frame_suspect_reason():
    good = frame(A, B)
    assert c.frame_suspect_reason(good, None) is None  # startup: nothing to compare
    assert c.frame_suspect_reason(good, good) is None
    assert c.frame_suspect_reason(frame(B, A), good) is None  # reorder is fine
    assert c.frame_suspect_reason(frame(A, B, {"StorageSN": "C"}), good) is None  # added unit
    assert c.frame_suspect_reason(frame(A), good) == "1 of 2 unit(s) missing from Storage_list"
    assert "empty" in c.frame_suspect_reason({"Storage_list": []}, good)
    assert "empty" in c.frame_suspect_reason({}, good)
    assert "A" not in c.frame_suspect_reason(frame(B), good)  # no serials in diagnostics


def test_fill_missing_soc():
    data = frame({"StorageSN": "A", "StorageStatus": 1}, {**B, "BatterySoc": 40})
    c.fill_missing_soc(data, frame(A, B))
    assert data["Storage_list"][0]["BatterySoc"] == 60
    assert data["Storage_list"][1]["BatterySoc"] == 40  # present values untouched


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
