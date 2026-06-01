import asyncio
import time
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    DEFAULT_POLL_INTERVAL,
    FAILURE_TOLERANCE,
    DATA_HOLD_SECONDS,
    REG_EMS_ENABLE,
    REG_CONTROL_TIME1,
    REG_SCHEDULE_MODE,
    REG_AI_SMART_CHARGE,
    REG_AI_SMART_DISC,
    REG_CUSTOM_MODE,
    REG_MIN_SOC,
    REG_MAX_SOC,
    MODE_SELF_CONSUMPTION,
    MODE_CUSTOM,
    SLOT_DISABLED,
)
from .cleaners import CleanerContext, DEFAULT_PROFILE, CLEANERS
from .tcp_client import AECCDeviceClient
import logging

_LOGGER = logging.getLogger(__name__)

_SOC_FIELDS = [
    ("SSumInfoList", None, "AverageBatteryAverageSOC"),
    ("Storage_list", "StorageSN", "BatterySoc"),
]

_WRITE_VERIFY_DELAY = 0.5  # seconds between SET and readback


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

        # Poll health tracking
        self._consecutive_failures: int = 0
        self._last_good_data: dict | None = None
        self._last_good_time: datetime | None = None
        self._cleaner_state: dict = {}

        # Control state — reflects the last commanded values
        self._commanded_min_soc: int = 10
        self._commanded_max_soc: int = 98
        self._commanded_direction: str = "Idle"
        self.commanded_operating_mode: str | None = None
        self.commanded_charge_power: int = 800
        self.commanded_discharge_power: int = 800

        # Read from device on first setup
        self.initial_min_soc: int | None = None
        self.initial_max_soc: int | None = None

    # ── Diagnostic properties ─────────────────────────────────────────────────

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def last_successful_update(self) -> datetime | None:
        return self._last_good_time

    # ── SOC cleaning ──────────────────────────────────────────────────────────

    def _get_wall_power(self, data: dict) -> float | None:
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

    # ── Poll ──────────────────────────────────────────────────────────────────

    async def _fetch_with_reconnect(self) -> dict | None:
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

    # ── Register write helpers ────────────────────────────────────────────────

    async def _write_registers(self, payload: dict[str, str], operation: str) -> bool:
        """Write a set of control registers and optionally verify the write."""
        resp = await self.client.set_control_parameters(payload)
        if resp is None:
            _LOGGER.warning("SET %s — no response from device", operation)
            return False

        _LOGGER.debug("SET %s response: %s", operation, resp)

        await asyncio.sleep(_WRITE_VERIFY_DELAY)

        try:
            reg_addrs = [int(k) for k in payload.keys() if k != REG_CONTROL_TIME1]
            if reg_addrs:
                verify = await self.client.get_control_parameters(reg_addrs)
                if verify:
                    params = (
                        verify.get("ControlInfo")
                        or verify.get("GetParameters")
                        or {}
                    )
                    for reg, expected in payload.items():
                        if reg == REG_CONTROL_TIME1:
                            continue
                        actual = params.get(reg) or params.get(int(reg))
                        if actual is not None and str(actual).strip() != str(expected).strip():
                            _LOGGER.warning(
                                "Write verify mismatch for %s: register %s expected %r, got %r",
                                operation, reg, expected, actual,
                            )
        except Exception as e:
            _LOGGER.debug("Write verify for %s failed: %s", operation, e)

        return True

    # ── Control API ───────────────────────────────────────────────────────────

    async def async_set_min_soc(self, value: int) -> bool:
        self._commanded_min_soc = value
        return await self._write_registers({REG_MIN_SOC: str(value)}, f"min_soc({value}%)")

    async def async_set_max_soc(self, value: int) -> bool:
        self._commanded_max_soc = value
        return await self._write_registers({REG_MAX_SOC: str(value)}, f"max_soc({value}%)")

    async def async_set_battery_control(self, direction: str, power_w: int) -> bool:
        has_storage = bool(self.data and self.data.get("Storage_list"))
        field7 = 5 if has_storage else 4

        charge_soc = self._commanded_max_soc
        discharge_soc = self._commanded_min_soc

        if direction == "Idle" or power_w == 0:
            slot1 = f"0,00:00,00:00,0,0,0,0,0,0,{charge_soc},{discharge_soc}"
        else:
            reg_power = -power_w if direction == "Charge" else power_w
            slot1 = f"1,00:00,23:59,{reg_power},0,6,{field7},0,0,{charge_soc},{discharge_soc}"

        payload = {
            REG_EMS_ENABLE: "1",
            REG_SCHEDULE_MODE: "6",
            REG_AI_SMART_CHARGE: "0",
            REG_AI_SMART_DISC: "0",
            REG_CUSTOM_MODE: "1",
            REG_CONTROL_TIME1: slot1,
        }

        _LOGGER.info(
            "SET battery_control direction=%s power=%dW -> 3003=%r",
            direction, power_w, slot1,
        )

        success = await self._write_registers(payload, f"battery_control({direction}, {power_w}W)")
        if success:
            self._commanded_direction = direction
            if direction == "Charge" and power_w > 0:
                self.commanded_charge_power = power_w
            elif direction == "Discharge" and power_w > 0:
                self.commanded_discharge_power = power_w
        return success

    async def async_restore_self_consumption(self) -> bool:
        """Return battery to AI self-consumption mode (schedule-3 pattern)."""
        clear_payload = {
            REG_CONTROL_TIME1: SLOT_DISABLED,
            REG_CUSTOM_MODE: "0",
        }
        restore_payload = {
            REG_EMS_ENABLE: "1",
            REG_SCHEDULE_MODE: "3",
            REG_AI_SMART_CHARGE: "0",
            REG_AI_SMART_DISC: "1",
            REG_CUSTOM_MODE: "0",
            REG_CONTROL_TIME1: SLOT_DISABLED,
        }

        for attempt in range(1, 4):
            await self._write_registers(clear_payload, f"self_consumption(clear #{attempt})")
            await asyncio.sleep(0.75)
            ok = await self._write_registers(restore_payload, f"self_consumption(restore #{attempt})")
            if ok:
                self._commanded_direction = "Idle"
                self.commanded_operating_mode = "Self-Gen/Zero Export"
                return True
            if attempt < 3:
                _LOGGER.warning("Self-consumption restore attempt %d failed; retrying", attempt)
                await asyncio.sleep(2)

        return False

    async def async_read_initial_state(self) -> None:
        """Read Min/Max SOC from device on startup so sliders reflect actual state."""
        resp = await self.client.get_control_parameters(
            [int(REG_MIN_SOC), int(REG_MAX_SOC)]
        )
        if resp is None:
            _LOGGER.debug("Initial state read: no response (device may not support it)")
            return

        params = (
            resp.get("ControlInfo")
            or resp.get("GetParameters")
            or resp.get("Parameters")
            or {}
        )
        if not isinstance(params, dict):
            return

        def _int(key: str) -> int | None:
            val = params.get(key) or params.get(int(key))
            if val is None:
                return None
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        min_soc = _int(REG_MIN_SOC)
        max_soc = _int(REG_MAX_SOC)

        if min_soc is not None:
            self.initial_min_soc = min_soc
            self._commanded_min_soc = min_soc
            _LOGGER.info("Read initial min SOC: %d%%", min_soc)

        if max_soc is not None:
            self.initial_max_soc = max_soc
            self._commanded_max_soc = max_soc
            _LOGGER.info("Read initial max SOC: %d%%", max_soc)
