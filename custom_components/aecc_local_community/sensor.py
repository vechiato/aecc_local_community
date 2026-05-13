import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import callback
from homeassistant.util import dt as dt_util
from homeassistant.const import (
    UnitOfPower,
    UnitOfEnergy,
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

# Energy sensors auto-created for the HA Energy Dashboard.
# Tuples: (key_suffix, data_type, api_path, label)
# SSumInfoList entries produce system-total sensors (no SN prefix).
# Storage_list entries produce per-device sensors (SN prefix).
ENERGY_SENSOR_DEFS = [
    ("solar_energy", "SSumInfoList", "TotalPVPower", "Solar Energy"),
    ("battery_charge_energy", "SSumInfoList", "TotalChargePower", "Battery Charge Energy"),
    ("battery_discharge_energy", "SSumInfoList", "TotalBatteryOutputPower", "Battery Discharge Energy"),
    ("battery_charge_energy", "Storage_list", "BatteryChargingPower", "Battery Charge Energy"),
    ("battery_discharge_energy", "Storage_list", "BatteryDischargingPower", "Battery Discharge Energy"),
]


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    device_sn = config_entry.data["device_sn"]

    sensors = []

    for data_type, field_map in SENSOR_MAP.items():
        raw_data = coordinator.data.get(data_type)
        if not raw_data:
            continue

        if isinstance(raw_data, list):
            for item in raw_data:
                sn = next((item.get(k) for k in SN_KEYS if item.get(k)), None)
                if not sn:
                    continue
                for key, (path, unit) in field_map.items():
                    if item.get(path) is None:
                        continue
                    sensors.append(
                        AECCSensor(coordinator, device_sn, item, data_type, key, path, unit)
                    )
        else:
            item = raw_data
            for key, (path, unit) in field_map.items():
                if item.get(path) is None:
                    continue
                sensors.append(
                    AECCSensor(coordinator, device_sn, item, data_type, key, path, unit)
                )

    for key_suffix, data_type, api_path, label in ENERGY_SENSOR_DEFS:
        raw_data = coordinator.data.get(data_type)
        if not raw_data:
            continue
        if isinstance(raw_data, list):
            for item in raw_data:
                sn = next((item.get(k) for k in SN_KEYS if item.get(k)), None)
                if not sn or item.get(api_path) is None:
                    continue
                sensors.append(
                    AECCEnergySensor(coordinator, device_sn, data_type, api_path, key_suffix, label, sn=sn)
                )
        else:
            if raw_data.get(api_path) is not None:
                sensors.append(
                    AECCEnergySensor(coordinator, device_sn, data_type, api_path, key_suffix, label)
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


class AECCEnergySensor(CoordinatorEntity, SensorEntity, RestoreEntity):
    """Cumulative energy sensor (kWh) derived by integrating a power sensor over time."""

    def __init__(self, coordinator, device_sn, data_type, api_path, key_suffix, label, sn=None):
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._data_type = data_type
        self._api_path = api_path
        self._sn = sn
        self._energy_kwh = 0.0
        self._last_update = None
        if sn:
            self._unique_id = f"aecc_{device_sn}_{data_type.lower()}_{sn}_{key_suffix}"
            self._attr_name = f"{sn} {label}"
        else:
            self._unique_id = f"aecc_{device_sn}_{data_type.lower()}_{key_suffix}"
            self._attr_name = label

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            try:
                self._energy_kwh = float(last_state.state)
            except (ValueError, TypeError):
                pass
        self._last_update = dt_util.utcnow()

    def _get_power_w(self):
        raw = self.coordinator.data.get(self._data_type) if self.coordinator.data else None
        if raw is None:
            return None
        if isinstance(raw, list):
            item = (
                next((i for i in raw if any(i.get(k) == self._sn for k in SN_KEYS)), None)
                if self._sn else (raw[0] if raw else None)
            )
        else:
            item = raw
        if item is None:
            return None
        value = item.get(self._api_path)
        if value is None:
            return None
        power = float(value)
        if self._data_type == "Storage_list":
            power /= 10
        return power

    @callback
    def _handle_coordinator_update(self):
        now = dt_util.utcnow()
        power_w = self._get_power_w()
        if power_w is not None and self._last_update is not None:
            elapsed_hours = (now - self._last_update).total_seconds() / 3600
            self._energy_kwh += max(0.0, power_w * elapsed_hours / 1000)
        self._last_update = now
        self.async_write_ha_state()

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def native_value(self):
        return round(self._energy_kwh, 3)

    @property
    def native_unit_of_measurement(self):
        return UnitOfEnergy.KILO_WATT_HOUR

    @property
    def device_class(self):
        return SensorDeviceClass.ENERGY

    @property
    def state_class(self):
        return SensorStateClass.TOTAL_INCREASING

    @property
    def device_info(self):
        model_map = {
            "SSumInfoList": "System Summary",
            "Storage_list": "Inverter/Storage",
        }
        model = model_map.get(self._data_type, self._data_type)
        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._device_sn,
            "model": model,
            "manufacturer": "AECC",
        }
