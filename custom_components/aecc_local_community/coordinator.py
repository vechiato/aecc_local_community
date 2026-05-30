import time
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_POLL_INTERVAL, FAILURE_TOLERANCE, DATA_HOLD_SECONDS
from .cleaners import CleanerContext, DEFAULT_PROFILE, CLEANERS
from .tcp_client import AECCDeviceClient
import logging

_LOGGER = logging.getLogger(__name__)

# (data_type, sn_key_or_None, field) triples for all SOC fields to clean.
_SOC_FIELDS = [
    ("SSumInfoList", None, "AverageBatteryAverageSOC"),
    ("Storage_list", "StorageSN", "BatterySoc"),
]


class AECCDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host, port, poll_interval: int = DEFAULT_POLL_INTERVAL):
        super().__init__(
            hass,
            _LOGGER,
            name="AECC Device Coordinator",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = AECCDeviceClient(host, port)
        self.devices = {}
        self._consecutive_failures: int = 0
        self._last_good_data: dict | None = None
        self._last_good_time: datetime | None = None
        # Per-field cleaner state: {state_key: {last_accepted_value, last_accepted_at}}
        self._cleaner_state: dict = {}

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def last_successful_update(self) -> datetime | None:
        return self._last_good_time

    def _get_wall_power(self, data: dict) -> float | None:
        """Return total battery activity (W) for SOC cleaner context."""
        summary = data.get("SSumInfoList")
        if not isinstance(summary, dict):
            return None
        try:
            charge = float(summary.get("TotalChargePower") or 0)
            discharge = float(summary.get("TotalBatteryOutputPower") or 0)
            return charge + discharge
        except (ValueError, TypeError):
            return None

    def _apply_soc_cleaners(self, data: dict) -> dict:
        """Run SOC fields through physics cleaners, substituting last good value on rejection."""
        now = time.monotonic()
        wall_power = self._get_wall_power(data)

        for data_type, sn_key, field in _SOC_FIELDS:
            cleaner = CLEANERS.get(field)
            if cleaner is None:
                continue
            raw_data = data.get(data_type)
            if raw_data is None:
                continue
            items = raw_data if isinstance(raw_data, list) else [raw_data]
            for item in items:
                raw_val = item.get(field)
                if raw_val is None:
                    continue
                try:
                    raw_val = float(raw_val)
                except (ValueError, TypeError):
                    continue

                sn = item.get(sn_key) if sn_key else "_system"
                state_key = f"{data_type}.{sn}.{field}"
                state = self._cleaner_state.get(state_key, {})

                ctx = CleanerContext(
                    key=state_key,
                    raw_value=raw_val,
                    last_accepted_value=state.get("last_accepted_value"),
                    last_accepted_at=state.get("last_accepted_at"),
                    now=now,
                    wall_power_w=wall_power,
                    profile=DEFAULT_PROFILE,
                )
                result = cleaner(ctx)
                if result is None:
                    _LOGGER.debug(
                        "SOC cleaner rejected %s=%.1f for %s; holding last accepted=%.1f",
                        field, raw_val, sn,
                        state.get("last_accepted_value", float("nan")),
                    )
                    if state.get("last_accepted_value") is not None:
                        item[field] = state["last_accepted_value"]
                else:
                    self._cleaner_state[state_key] = {
                        "last_accepted_value": result,
                        "last_accepted_at": now,
                    }
                    item[field] = result

        return data

    async def _fetch_with_reconnect(self) -> dict | None:
        """Attempt fetch, reconnect once on connection error."""
        try:
            data = await self.client.fetch_data()
            if data:
                return dict(data)
            _LOGGER.warning("No data returned on first attempt, retrying after reconnect...")
        except (ConnectionError, ConnectionResetError, OSError) as e:
            _LOGGER.warning("Connection error during fetch_data: %s, attempting reconnect...", e)

        try:
            await self.client.disconnect()
            await self.client.connect()
            _LOGGER.info("Reconnected to AECC device")
            data = await self.client.fetch_data()
            if data:
                return dict(data)
            _LOGGER.error("No data returned even after reconnect")
        except Exception as e:
            _LOGGER.error("Failed to fetch data after reconnect: %s", e)

        return None

    async def _async_update_data(self):
        data = await self._fetch_with_reconnect()

        if data:
            data = self._apply_soc_cleaners(data)
            self._consecutive_failures = 0
            self._last_good_data = data
            self._last_good_time = dt_util.utcnow()
            return data

        self._consecutive_failures += 1

        if (
            self._last_good_data is not None
            and self._consecutive_failures < FAILURE_TOLERANCE
        ):
            _LOGGER.debug(
                "Holding last good data (failure %d/%d)",
                self._consecutive_failures,
                FAILURE_TOLERANCE,
            )
            return self._last_good_data

        if self._last_good_data is not None and self._last_good_time is not None:
            elapsed = (dt_util.utcnow() - self._last_good_time).total_seconds()
            if elapsed < DATA_HOLD_SECONDS:
                _LOGGER.warning(
                    "Failure tolerance exceeded but within hold window (%.0fs); keeping last data",
                    elapsed,
                )
                return self._last_good_data

        _LOGGER.error(
            "AECC device unreachable after %d consecutive failures; marking unavailable",
            self._consecutive_failures,
        )
        return {}
