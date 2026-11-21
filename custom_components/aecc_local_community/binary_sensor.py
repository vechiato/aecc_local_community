"""Fault binary sensor from the Modbus telemetry block."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    if coordinator.telemetry is not None:
        async_add_entities([AECCFaultSensor(coordinator, config_entry.data["device_sn"])])


class AECCFaultSensor(CoordinatorEntity, BinarySensorEntity):
    """On when the device reports a fault (register 65039)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Fault"

    def __init__(self, coordinator, device_sn: str) -> None:
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"aecc_{device_sn}_modbus_fault"

    @property
    def is_on(self) -> bool | None:
        telemetry = self.coordinator.telemetry
        return None if telemetry is None else telemetry["fault"] != 0

    @property
    def extra_state_attributes(self):
        telemetry = self.coordinator.telemetry or {}
        return {"alarm_flags": telemetry.get("alarm_flags")}

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self._device_sn)}, "name": self._device_sn, "manufacturer": "AECC"}
