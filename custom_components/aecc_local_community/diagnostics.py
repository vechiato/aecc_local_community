"""Diagnostics support for AECC Local (Community).

Produces a single JSON dump for bug triage:
- Integration identity and version
- Live coordinator state (commanded values, failure tracking)
- Cleaner state snapshot (last accepted SOC values)
- Last raw poll response (PII redacted)
- Fresh control-register dump 3000–3130 fetched at download time
- Last 20 control writes with payloads and verify outcomes
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    REG_AI_SMART_CHARGE,
    REG_AI_SMART_DISC,
    REG_CONTROL_TIME1,
    REG_CUSTOM_MODE,
    REG_EMS_ENABLE,
    REG_MAX_SOC,
    REG_MIN_SOC,
    REG_SCHEDULE_MODE,
)
from .coordinator import AECCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_REDACT_KEYS = {
    # Known AECC protocol fields
    "host", "serial", "device_serial", "StorageSN", "datalogSn", "deviceSn",
    "device_ip", "device_sn", "friendlyName",
    # Defensive: prevent leaking credentials if future firmware returns them
    "password", "Password", "token", "Token", "secret", "api_key", "apiKey",
    "email", "ssid", "SSID", "wifi_password", "wifiPassword", "WifiPassword",
    "mac", "MAC", "mac_address", "macAddress", "latitude", "longitude",
}

_KEY_REGISTER_LABELS: dict[str, str] = {
    REG_EMS_ENABLE: "EMS enable (3000)",
    REG_CONTROL_TIME1: "Control time slot 1 (3003)",
    REG_SCHEDULE_MODE: "Schedule mode (3020)",
    REG_AI_SMART_CHARGE: "AI smart charge (3021)",
    REG_AI_SMART_DISC: "AI smart discharge (3022)",
    REG_MIN_SOC: "Min SOC (3023)",
    REG_MAX_SOC: "Max SOC (3024)",
    REG_CUSTOM_MODE: "Custom mode (3030)",
}

_REGISTER_RANGE = list(range(3000, 3131))
_REGISTER_RANGE_FALLBACK = list(range(3000, 3040))


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    coordinator: AECCDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    poll_seconds: int | None = None
    if coordinator.update_interval is not None:
        poll_seconds = int(coordinator.update_interval.total_seconds())

    payload: dict[str, Any] = {
        "integration": {
            "domain": DOMAIN,
            "version": await _read_integration_version(hass),
        },
        "device": {
            "host": coordinator.client.host,
            "port": coordinator.client.port,
            "device_sn": entry.data.get("device_sn"),
            "device_type": entry.data.get("device_type"),
        },
        "config": {
            "poll_interval_seconds": poll_seconds,
            "options": dict(entry.options),
        },
        "live_state": {
            "last_update_success": coordinator.last_update_success,
            "consecutive_failures": coordinator.consecutive_failures,
            "last_successful_update": (
                coordinator.last_successful_update.isoformat()
                if coordinator.last_successful_update else None
            ),
            "last_failed_update": (
                coordinator.last_failed_update.isoformat()
                if coordinator.last_failed_update else None
            ),
            "last_failure_reason": coordinator.last_failure_reason,
            "commanded_operating_mode": coordinator.commanded_operating_mode,
            "commanded_direction": coordinator._commanded_direction,
            "commanded_min_soc": coordinator._commanded_min_soc,
            "commanded_max_soc": coordinator._commanded_max_soc,
            "commanded_charge_power": coordinator.commanded_charge_power,
            "commanded_discharge_power": coordinator.commanded_discharge_power,
            "initial_min_soc": coordinator.initial_min_soc,
            "initial_max_soc": coordinator.initial_max_soc,
        },
        "cleaner_state": {
            state_key: {
                "last_accepted_value": state.get("last_accepted_value"),
                "last_accepted_at": state.get("last_accepted_at"),
            }
            for state_key, state in coordinator._cleaner_state.items()
        },
        "last_poll": coordinator.data or coordinator._last_good_data or {},
        "control_registers": await _fetch_control_registers(coordinator),
        "write_history": coordinator.write_history,
    }

    return async_redact_data(payload, _REDACT_KEYS)


async def _fetch_control_registers(
    coordinator: AECCDataUpdateCoordinator,
) -> dict[str, Any]:
    """Read the full control-register range from the device at download time."""
    section: dict[str, Any] = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "registers": {},
        "key_registers": {},
        "range": [_REGISTER_RANGE[0], _REGISTER_RANGE[-1]],
        "error": None,
    }

    try:
        resp = await coordinator.client.get_control_parameters(_REGISTER_RANGE)
    except Exception as exc:
        section["error"] = f"wide read failed: {exc}"
        resp = None

    if resp is None:
        if section["error"] is None:
            section["error"] = "wide read returned no response"
        try:
            resp = await coordinator.client.get_control_parameters(_REGISTER_RANGE_FALLBACK)
            section["range"] = [_REGISTER_RANGE_FALLBACK[0], _REGISTER_RANGE_FALLBACK[-1]]
        except Exception as exc:
            section["error"] = f"{section['error']}; fallback also failed: {exc}"
            return section
        if resp is None:
            section["error"] = f"{section['error']}; fallback returned no response"
            return section

    params = resp.get("ControlInfo") or resp.get("GetParameters") or resp.get("Parameters") or {}
    if not isinstance(params, dict):
        section["error"] = f"unexpected response shape: {type(params).__name__}"
        return section

    normalised = {str(k): v for k, v in params.items()}
    section["registers"] = normalised
    section["key_registers"] = {
        label: normalised.get(reg)
        for reg, label in _KEY_REGISTER_LABELS.items()
        if reg in normalised
    }
    return section


async def _read_integration_version(hass: HomeAssistant) -> str | None:
    try:
        integration = await async_get_integration(hass, DOMAIN)
        return integration.version
    except Exception as exc:
        _LOGGER.debug("Could not read integration version for diagnostics: %s", exc)
        return None
