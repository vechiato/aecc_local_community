"""AECC Local (Community) integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
from .coordinator import AECCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _LOGGER.info("Setting up AECC device entry %s", config_entry.data)

    host = config_entry.data["device_ip"]
    port = config_entry.data["device_port"]
    poll_interval = config_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    coordinator = AECCDataUpdateCoordinator(hass, host, port, poll_interval)
    await coordinator.async_config_entry_first_refresh()

    # Read min/max SOC from device so sliders reflect actual state
    await coordinator.async_read_initial_state()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {
        "coordinator": coordinator,
        "config_entry": config_entry,
    }

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
    if coordinator and hasattr(coordinator, "client"):
        await coordinator.client.disconnect()

    hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
