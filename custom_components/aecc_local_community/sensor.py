import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    UnitOfPower,
    UnitOfTemperature,
    PERCENTAGE,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_UNIT_TO_DEVICE_CLASS = {
    UnitOfPower.WATT: SensorDeviceClass.POWER,
    PERCENTAGE: SensorDeviceClass.BATTERY,
    UnitOfTemperature.CELSIUS: SensorDeviceClass.TEMPERATURE,
}

SN_KEYS = ("PlugSN", "ChargerSN", "HotSN", "StorageSN")

SENSOR_MAP = {
    "SSumInfoList": {
        "control_enable_status": ("ControlEnableStatus", None),
        "total_active_power": ("MeterTotalActivePower", UnitOfPower.WATT),
        "pv_power": ("TotalPVPower", UnitOfPower.WATT),
        "pv_charge_power": ("TotalPVChargePower", UnitOfPower.WATT),
        "ac_charge_power": ("TotalACChargePower", UnitOfPower.WATT),
        "smart_load_power": ("TotalSmartLoadElectricalPower", UnitOfPower.WATT),
        "avg_battery_soc": ("AverageBatteryAverageSOC", PERCENTAGE),
        "battery_output_power": ("TotalBatteryOutputPower", UnitOfPower.WATT),
        "grid_output_power": ("TotalGridOutputPower", UnitOfPower.WATT),
        "backup_power": ("TotalBackUpPower", UnitOfPower.WATT),
        "total_charge_power": ("TotalChargePower", UnitOfPower.WATT),
    },
    "Storage_list": {
        "status": ("StorageStatus", None),
        "pv_charging_power": ("PvChargingPower", UnitOfPower.WATT),
        "ac_charging_power": ("AcChargingPower", UnitOfPower.WATT),
        "battery_soc": ("BatterySoc", PERCENTAGE),
        "battery_discharging_power": ("BatteryDischargingPower", UnitOfPower.WATT),
        "ac_in_active_power": ("AcInActivePower", UnitOfPower.WATT),
        "off_grid_load_power": ("OffGridLoadPower", UnitOfPower.WATT),
        "battery_charging_power": ("BatteryChargingPower", UnitOfPower.WATT),
        "pv_string_count": ("PvStringCount", None),
        "pv1_power": ("Pv1Power", UnitOfPower.WATT),
        "pv2_power": ("Pv2Power", UnitOfPower.WATT),
        "pv3_power": ("Pv3Power", UnitOfPower.WATT),
        "pv4_power": ("Pv4Power", UnitOfPower.WATT),
    },
    "PlugInfoList": {
        "active_power": ("PlugActvePower", UnitOfPower.WATT),
    },
    "ChargerInfoList": {
        "connector_1_status": ("Connector1Status", None),
        "connector_1_power": ("Connector1Power", UnitOfPower.WATT),
        "connector_2_status": ("Connector2Status", None),
        "connector_2_power": ("Connector2Power", UnitOfPower.WATT),
    },
    "HotInfoList": {
        "active_power": ("HotActvePower", UnitOfPower.WATT),
        "max_power": ("HotActvePowerMAX", UnitOfPower.WATT),
        "temperature": ("HotTEMP", UnitOfTemperature.CELSIUS),
        "max_temperature": ("HotTEMPMAX", UnitOfTemperature.CELSIUS),
    }
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    device_sn = config_entry.data["device_sn"]

    sensors = []
    # 遍历map
    for data_type, field_map in SENSOR_MAP.items():
        raw_data = coordinator.data.get(data_type)
        if not raw_data:
            continue  # 数据不存在，跳过

        if isinstance(raw_data, list):
            # 遍历各个设备数组
            for item in raw_data:
                sn = next((item.get(k) for k in SN_KEYS if item.get(k)), None)
                if not sn:
                    continue  # 缺少 SN，跳过

                for key, (path, unit) in field_map.items():
                    value = item.get(path)
                    if value is None:
                        continue  # 字段缺失，跳过

                    unique_id = f"{device_sn}_{data_type.lower()}_{sn}_{key}"


                    sensors.append(
                        AECCSensor(coordinator, device_sn, item, data_type, key, path, unit)
                    )
        else:
            # 非列表结构（如 SSumInfoList）
            item = raw_data
            for key, (path, unit) in field_map.items():
                value = item.get(path)
                if value is None:
                    continue  # 字段缺失，跳过

                unique_id = f"{device_sn}_{data_type.lower()}_{key}"
                sensors.append(
                    AECCSensor(coordinator, device_sn, item, data_type, key, path, unit)
                )

    async_add_entities(sensors)


class AECCSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, device_sn, item, data_type, key, path, unit):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._item = item
        self._data_type = data_type
        self._device_sn = device_sn
        self._key = key
        self._path = path
        self._unit = unit
        self._unique_id = self._generate_unique_id(device_sn, item)

    def _generate_unique_id(self, device_sn, item):
        sn = next((item.get(k) for k in SN_KEYS if item.get(k)), None)
        if sn:
            return f"aecc_{device_sn}_{self._data_type.lower()}_{sn}_{self._key}"
        else:
            return f"aecc_{device_sn}_{self._data_type.lower()}_{self._key}"

    def _get_current_item(self):
        raw = self.coordinator.data.get(self._data_type) if self.coordinator.data else None
        if raw is None:
            return {}
        if isinstance(raw, list):
            sn_key = next((k for k in SN_KEYS if k in self._item), None)
            if sn_key:
                sn = self._item.get(sn_key)
                for entry in raw:
                    if entry.get(sn_key) == sn:
                        return entry
            return {}
        return raw

    @property
    def name(self):
        sn = next((self._item.get(k) for k in SN_KEYS if self._item.get(k)), None)
        if sn:
            return f"{sn} {self._key.replace('_', ' ').title()}"
        else:
            return f"{self._key.replace('_', ' ').title()}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def native_value(self):
        value = self._get_current_item().get(self._path)
        _LOGGER.debug(f"Analysis key {self._path} value：{value}")
        if value is None:
            return 0.0
        try:
            result = float(value)
        except (ValueError, TypeError):
            _LOGGER.debug(f"Exception value：{value} is not a float, returning 0.0")
            return 0.0

        if self._data_type == "Storage_list" and self._unit == UnitOfPower.WATT:
            return result / 10
        if self._data_type == "HotInfoList" and self._path in ["HotTEMP", "HotTEMPMAX"]:
            return result / 10
        return result

    @property
    def device_class(self):
        return _UNIT_TO_DEVICE_CLASS.get(self._unit)

    @property
    def state_class(self):
        if self._unit is not None:
            return SensorStateClass.MEASUREMENT
        return None

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def device_info(self):
        model_map = {
            "SSumInfoList": "System Summary",
            "Storage_list": "Inverter/Storage",
            "PlugInfoList": "Smart Plug",
            "ChargerInfoList": "EV Charger",
            "HotInfoList": "Heater",
        }
        model = model_map.get(self._data_type, self._data_type)

        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._device_sn,
            "model": model,
            "manufacturer": "AECC",
        }

