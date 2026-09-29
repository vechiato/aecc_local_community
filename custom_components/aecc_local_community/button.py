"""Restart Data Logger button."""
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([AECCRestartDataloggerButton(coordinator, config_entry.data["device_sn"])])


class AECCRestartDataloggerButton(CoordinatorEntity, ButtonEntity):
    """Reboot the Wi-Fi datalogger over local TCP, e.g. when it stops answering."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_icon = "mdi:restart-alert"

    def __init__(self, coordinator, device_sn: str) -> None:
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"aecc_{device_sn}_restart_datalogger"
        self._attr_name = "Restart Data Logger"

    @property
    def available(self) -> bool:
        # A restart is most useful exactly when polling has stopped working.
        return True

    async def async_press(self) -> None:
        if not await self.coordinator.async_restart_datalogger():
            raise HomeAssistantError("The datalogger restart command could not be sent")

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._device_sn,
            "manufacturer": "AECC",
        }
