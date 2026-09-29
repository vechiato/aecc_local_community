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


def test_startup_zero_soc():
    assert c.startup_zero_soc(frame({**A, "BatterySoc": 0}))
    assert c.startup_zero_soc(frame({**A, "BatterySoc": "0", "StorageStatus": None}))
    assert not c.startup_zero_soc(frame({**A, "BatterySoc": 0, "StorageStatus": 0}))  # offline
    assert not c.startup_zero_soc(frame(A, B))
    assert not c.startup_zero_soc({})


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
