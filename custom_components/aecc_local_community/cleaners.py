"""Physics-aware sensor value cleaners.

Some AECC devices emit 0 for SOC and power fields when the datalog gateway
loses sync with the BMS for tens of seconds to minutes. The JSON response
defaults missing fields to 0 rather than marking them unavailable, so bogus
zeros pass through to Home Assistant and pollute energy accumulators.

Each cleaner receives a CleanerContext and returns either the accepted value
or None to signal rejection. A None causes the coordinator to substitute the
last accepted value, preventing garbage readings from reaching entities.

Ported and simplified from the Aferiy-PS240-Local integration (MIT licence).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CleanerContext:
    key: str
    raw_value: float
    last_accepted_value: float | None
    last_accepted_at: float | None  # time.monotonic() epoch
    now: float                       # time.monotonic() of current poll
    wall_power_w: float | None       # total battery activity power (abs used only)
    profile: dict[str, Any]


def clean_soc(ctx: CleanerContext) -> float | None:
    """Reject SOC readings that contradict observable physics.

    Two checks:
    1. SOC == 0 while the battery is actively cycling above the threshold
       power — a gateway glitch, not a real empty-battery event.
    2. Rate of change exceeds the physical maximum for the battery chemistry
       — impossible jumps indicate a stale or corrupted reading.
    """
    raw = ctx.raw_value
    profile = ctx.profile
    threshold_w = float(profile.get("soc_zero_reject_during_active_w", 100))
    max_rate = float(profile.get("soc_max_rate_pct_per_min", 8.0))

    if raw == 0 and ctx.wall_power_w is not None and abs(ctx.wall_power_w) > threshold_w:
        return None

    if (
        ctx.last_accepted_value is not None
        and ctx.last_accepted_at is not None
        and ctx.now > ctx.last_accepted_at
    ):
        elapsed_s = ctx.now - ctx.last_accepted_at
        if elapsed_s >= 1.0:  # ignore sub-second gaps between same-poll calls
            change_per_min = abs(raw - ctx.last_accepted_value) / (elapsed_s / 60.0)
            if change_per_min > max_rate:
                return None

    return raw


# Default profile for generic AECC devices.
# Tuned conservatively — accept most readings, only reject clear glitches.
DEFAULT_PROFILE: dict[str, Any] = {
    "soc_zero_reject_during_active_w": 100,
    "soc_max_rate_pct_per_min": 8.0,
}

# ── Storage_list frame checks ─────────────────────────────────────────────────
# The gateway can briefly return a frame where a battery unit is missing, the
# whole Storage_list is empty, or an online unit reports 0% SOC at startup.


def storage_units(data: dict | None) -> dict[str, dict]:
    """Storage_list entries keyed by StorageSN (entries without an SN are skipped)."""
    units = (data or {}).get("Storage_list") or []
    return {
        str(u["StorageSN"]): u
        for u in units
        if isinstance(u, dict) and u.get("StorageSN")
    }


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def startup_zero_soc(data: dict) -> bool:
    """True if any unit that isn't reported offline (StorageStatus 0) shows 0% SOC."""
    for unit in (data.get("Storage_list") or []):
        if not isinstance(unit, dict):
            continue
        if _as_float(unit.get("BatterySoc")) == 0 and _as_float(unit.get("StorageStatus")) != 0:
            return True
    return False


def frame_suspect_reason(data: dict, last_good: dict | None) -> str | None:
    """Why this frame looks like a partial snapshot, or None if it looks complete."""
    last = storage_units(last_good)
    if not last:
        return None
    new = storage_units(data)
    if not new:
        return "Storage_list empty after previously reporting battery units"
    # Count only: this string lands in diagnostics, where StorageSN is redacted.
    missing = len(set(last) - set(new))
    if missing:
        return f"{missing} of {len(last)} unit(s) missing from Storage_list"
    return None


def fill_missing_soc(data: dict, last_good: dict | None) -> None:
    """Carry a unit's last BatterySoc forward when a poll omits just that field."""
    last = storage_units(last_good)
    for sn, unit in storage_units(data).items():
        if unit.get("BatterySoc") is None and last.get(sn, {}).get("BatterySoc") is not None:
            unit["BatterySoc"] = last[sn]["BatterySoc"]


# Map canonical field name → cleaner function.
# Fields absent from this map are passed through unfiltered.
CLEANERS: dict[str, Any] = {
    "BatterySoc": clean_soc,
    "AverageBatteryAverageSOC": clean_soc,
}
