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

# Map canonical field name → cleaner function.
# Fields absent from this map are passed through unfiltered.
CLEANERS: dict[str, Any] = {
    "BatterySoc": clean_soc,
    "AverageBatteryAverageSOC": clean_soc,
}
