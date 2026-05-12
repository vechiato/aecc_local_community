from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from typing import Any, Dict, Optional
import logging
import voluptuous as vol
from .const import DOMAIN, LOGGER_NAME, get_device_type_name

_LOGGER = logging.getLogger(LOGGER_NAME)

class AeccLocalPluginConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """AECC 本地插件配置流程"""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self):
        self._host: str = ""
        self._port: int = 0
        self._device_sn: str = ""
        self._device_ip: str = ""
        self._device_type: str = ""
        self._device_port: int = 0
        self._default_name: str = ""

    async def async_step_zeroconf(
        self,
        discovery_info: ZeroconfServiceInfo
    ):
        """处理 Zeroconf 发现的设备"""
        # _LOGGER.info(f"info:{discovery_info}")
        if not discovery_info.name.startswith("SXD-mDNS-IF"):
            return self.async_abort(reason="not_aecc_device")

        # 提取设备信息
        self._host = str(discovery_info.addresses[0])
        self._port = discovery_info.port
        properties = dict(discovery_info.properties)

        self._device_sn = properties.get('s_sn', '')
        self._device_ip = properties.get('s_ip', '')
        self._device_type = int(properties.get('s_type', '0'))
        self._device_port = properties.get('s_port', 0)

        device_type_name = get_device_type_name(self._device_type)

        self._default_name = f"{device_type_name}--{self._device_sn}--{self._device_ip}"


        _LOGGER.info(f" discovery :{self._default_name}")
        await self.async_set_unique_id(self._device_sn)
        self._abort_if_unique_id_configured()

        self.context.update({
            "title_placeholders": {
                "name": self._default_name
            }
        })

        return await self.async_step_confirm_discovery()

    async def async_step_confirm_discovery(
        self,
        user_input: Optional[Dict[str, Any]] = None
    ) :
        """显示设备信息并等待用户确认"""
        if user_input is not None:
             return self.async_create_entry(
                title=f"{self._device_sn}",
                data={
                    "host": self._host,
                    "port": self._port,
                    "device_sn": self._device_sn,
                    "device_ip": self._device_ip,
                    "device_type": self._device_type,
                    "device_port": self._device_port,
                    "friendlyName": user_input.get("deviceName", self._device_sn),
                    # "area_id": area_id
                }
            )

        return self.async_show_form(
            step_id="confirm_discovery",
            description_placeholders={
                'sn': self._device_sn,
                'ip': self._device_ip,
                'type': self._device_type
            },
            data_schema=vol.Schema({
                vol.Required("deviceName"): vol.All(str, vol.Length(min=1, max=64)),
            }),
            errors={}
        )



