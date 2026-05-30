"""Diagnostics support for AECC Local (Community)."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_TO_REDACT = {"host", "device_ip", "device_sn", "friendlyName"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    return {
        "config_entry": async_redact_data(dict(entry.data), _TO_REDACT),
        "options": dict(entry.options),
        "coordinator": {
            "consecutive_failures": coordinator.consecutive_failures,
            "last_successful_update": coordinator.last_successful_update.isoformat()
            if coordinator.last_successful_update
            else None,
            "data_keys": list(coordinator.data.keys()) if coordinator.data else [],
        },
    }
