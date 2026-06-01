"""Number platform — SOC limit sliders and passive power target sliders."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_CHARGE_POWER_W, MAX_DISCHARGE_POWER_W
from .coordinator import AECCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AECCDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    device_sn = config_entry.data["device_sn"]

    async_add_entities([
        AECCMinSoc(coordinator, config_entry, device_sn),
        AECCMaxSoc(coordinator, config_entry, device_sn),
        AECCChargePowerSlider(coordinator, config_entry, device_sn),
        AECCDischargePowerSlider(coordinator, config_entry, device_sn),
    ])


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


class AECCMinSoc(CoordinatorEntity, NumberEntity, RestoreEntity):
    """Minimum discharge SOC slider — writes register 3023 on change."""

    _attr_has_entity_name = True
    _attr_name = "Discharge Limit"
    _attr_icon = "mdi:battery-arrow-down"
    _attr_device_class = NumberDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 5
    _attr_native_max_value = 50
    _attr_native_step = 5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: AECCDataUpdateCoordinator, config_entry: ConfigEntry, device_sn: str) -> None:
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"aecc_{device_sn}_min_soc"
        self._commanded: float = 10

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if self.coordinator.initial_min_soc is not None:
            self._commanded = self.coordinator.initial_min_soc
            return

        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._commanded = _clamp(
                    float(last_state.state),
                    self._attr_native_min_value,
                    self._attr_native_max_value,
                )
            except (TypeError, ValueError):
                pass

    @property
    def native_value(self) -> float:
        return self._commanded

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._device_sn)}, "name": self._device_sn, "manufacturer": "AECC"}

    async def async_set_native_value(self, value: float) -> None:
        soc = int(value)
        success = await self.coordinator.async_set_min_soc(soc)
        if success:
            self._commanded = soc
            self.async_write_ha_state()
        else:
            _LOGGER.warning("Failed to set discharge limit to %d%%", soc)


class AECCMaxSoc(CoordinatorEntity, NumberEntity, RestoreEntity):
    """Maximum charge SOC slider — writes register 3024 on change."""

    _attr_has_entity_name = True
    _attr_name = "Charge Limit"
    _attr_icon = "mdi:battery-arrow-up"
    _attr_device_class = NumberDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: AECCDataUpdateCoordinator, config_entry: ConfigEntry, device_sn: str) -> None:
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"aecc_{device_sn}_max_soc"
        self._commanded: float = 98

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if self.coordinator.initial_max_soc is not None:
            self._commanded = self.coordinator.initial_max_soc
            return

        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._commanded = _clamp(
                    float(last_state.state),
                    self._attr_native_min_value,
                    self._attr_native_max_value,
                )
            except (TypeError, ValueError):
                pass

    @property
    def native_value(self) -> float:
        return self._commanded

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._device_sn)}, "name": self._device_sn, "manufacturer": "AECC"}

    async def async_set_native_value(self, value: float) -> None:
        soc = int(value)
        success = await self.coordinator.async_set_max_soc(soc)
        if success:
            self._commanded = soc
            self.async_write_ha_state()
        else:
            _LOGGER.warning("Failed to set charge limit to %d%%", soc)


class _PassivePowerSlider(CoordinatorEntity, NumberEntity, RestoreEntity):
    """Base for charge/discharge power sliders. Stores value locally; does not send a command."""

    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_step = 100
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    _coordinator_attr: str = ""
    _default: int = 800

    def __init__(self, coordinator: AECCDataUpdateCoordinator, config_entry: ConfigEntry, device_sn: str) -> None:
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._commanded: float = self._default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._commanded = _clamp(
                    float(last_state.state),
                    self._attr_native_min_value,
                    self._attr_native_max_value,
                )
            except (TypeError, ValueError):
                pass
        setattr(self.coordinator, self._coordinator_attr, int(self._commanded))

    @property
    def native_value(self) -> float:
        return self._commanded

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._device_sn)}, "name": self._device_sn, "manufacturer": "AECC"}

    async def async_set_native_value(self, value: float) -> None:
        power = int(_clamp(value, self._attr_native_min_value, self._attr_native_max_value))
        self._commanded = power
        setattr(self.coordinator, self._coordinator_attr, power)
        self.async_write_ha_state()


class AECCChargePowerSlider(_PassivePowerSlider):
    """Charge power target (passive — applied when mode → Charge)."""

    _attr_name = "Charge Power"
    _attr_icon = "mdi:battery-charging"
    _attr_native_min_value = 100
    _attr_native_max_value = MAX_CHARGE_POWER_W
    _coordinator_attr = "commanded_charge_power"
    _default = 800

    def __init__(self, coordinator, config_entry, device_sn):
        super().__init__(coordinator, config_entry, device_sn)
        self._attr_unique_id = f"aecc_{device_sn}_charge_power_target"


class AECCDischargePowerSlider(_PassivePowerSlider):
    """Discharge power target (passive — applied when mode → Discharge)."""

    _attr_name = "Discharge Power"
    _attr_icon = "mdi:battery-minus"
    _attr_native_min_value = 100
    _attr_native_max_value = MAX_DISCHARGE_POWER_W
    _coordinator_attr = "commanded_discharge_power"
    _default = 800

    def __init__(self, coordinator, config_entry, device_sn):
        super().__init__(coordinator, config_entry, device_sn)
        self._attr_unique_id = f"aecc_{device_sn}_discharge_power_target"
