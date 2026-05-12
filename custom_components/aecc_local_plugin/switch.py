from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

# 定义哪些字段作为 switch 暴露出去
SWITCH_MAP = {
    "PlugInfoList": {
        "status": ("PlugStatus", "Switch"),
    },
    "ChargerInfoList": {
        "status": ("ChargerStatus", "Switch"),
    },
    "HotInfoList": {
        "status": ("HotStatus", "Switch"),
    }
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """从配置项中初始化设备，并添加 switch 实体"""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    device_sn = config_entry.data["device_sn"]

    switches = []

    # 处理 Switch
    for data_type, field_map in SWITCH_MAP.items():
        raw_data = coordinator.data.get(data_type)
        if not raw_data:
            continue

        if isinstance(raw_data, list):
            for item in raw_data:
                sn = item.get("PlugSN") or item.get("ChargerSN") or item.get("HotSN")
                if not sn:
                    continue

                for key, (path, name) in field_map.items():
                    value = item.get(path)
                    if value is None:
                        continue
                    attr = {
                        "dev_addr": item.get("DevAddr"),
                        "is_third_party": item.get("lsThirdParty"),
                        "fans_dev_type": item.get("FansDevType"),
                        "is_interconnect": item.get("IsInterconnect"),
                    }
                    switches.append(
                        AECCSwitch(coordinator, device_sn, item, data_type, key, path, name, attr)
                    )

    async_add_entities(switches)


class AECCSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, device_sn, item, data_type, key, path, name, attr):
        super().__init__(coordinator)
        self._item = item
        self._data_type = data_type
        self._device_sn = device_sn
        self._key = key
        self._path = path
        self._name = name
        self._unique_id = self._generate_unique_id(device_sn, item)
        self._attr = attr

    def _generate_unique_id(self, device_sn, item):
        sn = item.get("PlugSN") or item.get("ChargerSN") or item.get("HotSN")
        if sn:
            return f"aecc_{device_sn}_{self._data_type.lower()}_{sn}_{self._key}"
        else:
            return f"aecc_{device_sn}_{self._data_type.lower()}_{self._key}"

    def _get_current_item(self):
        raw = self.coordinator.data.get(self._data_type) if self.coordinator.data else None
        if raw is None:
            return {}
        if isinstance(raw, list):
            sn_key = next((k for k in ("PlugSN", "ChargerSN", "HotSN") if k in self._item), None)
            if sn_key:
                sn = self._item.get(sn_key)
                for entry in raw:
                    if entry.get(sn_key) == sn:
                        return entry
            return {}
        return raw

    @property
    def name(self):
        sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        if sn:
            return f"{sn} {self._key.replace('_', ' ').title()}"
        else:
            return f"{self._key.replace('_', ' ').title()}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def is_on(self):
        return self._get_current_item().get(self._path, 0) == 1

    async def async_turn_on(self, **kwargs):
        """发送打开命令"""
        sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        if sn:
            _LOGGER.info(f"Turning on switch: {sn}")
            # 假设 client 提供了 turn_on_plug 方法
            await self.coordinator.client.turn_on_switch(self._attr)
            await self.coordinator.async_request_refresh()
    async def async_turn_off(self, **kwargs):
        """发送关闭命令"""
        sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        if sn:
            _LOGGER.info(f"Turning off switch: {sn}")
            await self.coordinator.client.turn_off_switch(self._attr)
            await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        # sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._device_sn,
            "model": "smart load",
            "manufacturer": "AECC",
        }
    @property
    def extra_state_attributes(self) :
        return self._attr