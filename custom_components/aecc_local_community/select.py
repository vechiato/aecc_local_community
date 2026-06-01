"""Select platform — Operating Mode control."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODE_SELF_CONSUMPTION, MODE_CUSTOM
from .coordinator import AECCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

OPERATING_MODE_SELF_GEN = "Self-Gen/Zero Export"
OPERATING_MODE_OPTIONS = [OPERATING_MODE_SELF_GEN, "Idle", "Charge", "Discharge"]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AECCDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    device_sn = config_entry.data["device_sn"]
    async_add_entities([AECCOperatingModeSelect(coordinator, config_entry, device_sn)])


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


class AECCOperatingModeSelect(CoordinatorEntity, SelectEntity, RestoreEntity):
    """Operating mode selector.

    Self-Gen/Zero Export  → AI self-consumption (safe default)
    Idle                  → manual idle (no charge or discharge)
    Charge                → force charge at Charge Power slider value
    Discharge             → force discharge at Discharge Power slider value
    """

    _attr_has_entity_name = True
    _attr_name = "Operating Mode"
    _attr_icon = "mdi:battery-sync"
    _attr_options = OPERATING_MODE_OPTIONS

    def __init__(
        self,
        coordinator: AECCDataUpdateCoordinator,
        config_entry: ConfigEntry,
        device_sn: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"aecc_{device_sn}_operating_mode"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.commanded_operating_mode is None:
            last_state = await self.async_get_last_state()
            if last_state and last_state.state in OPERATING_MODE_OPTIONS:
                self.coordinator.commanded_operating_mode = last_state.state

    @property
    def current_option(self) -> str | None:
        mode = self.coordinator.commanded_operating_mode
        if mode in OPERATING_MODE_OPTIONS:
            return mode
        direction = self.coordinator._commanded_direction
        if direction in OPERATING_MODE_OPTIONS:
            return direction
        return "Idle"

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._device_sn)}, "name": self._device_sn, "manufacturer": "AECC"}

    async def async_select_option(self, option: str) -> None:
        _LOGGER.info("Operating mode selected: %s", option)

        if option == OPERATING_MODE_SELF_GEN:
            success = await self.coordinator.async_restore_self_consumption()
            if not success:
                _LOGGER.error("Failed to restore self-consumption mode")
            return

        if option == "Idle":
            success = await self.coordinator.async_set_battery_control("Idle", 0)
            if success:
                self.coordinator.commanded_operating_mode = "Idle"
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to set Idle mode")
            return

        if option == "Charge":
            power = _clamp(int(self.coordinator.commanded_charge_power or 800), 100, 1200)
            success = await self.coordinator.async_set_battery_control("Charge", power)
            if success:
                self.coordinator.commanded_operating_mode = "Charge"
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to set Charge mode")
            return

        if option == "Discharge":
            power = _clamp(int(self.coordinator.commanded_discharge_power or 800), 100, 1200)
            success = await self.coordinator.async_set_battery_control("Discharge", power)
            if success:
                self.coordinator.commanded_operating_mode = "Discharge"
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to set Discharge mode")
