"""AECC 本地插件集成。"""
import logging
from datetime import timedelta

from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncZeroconf, AsyncServiceBrowser

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import AECCDataUpdateCoordinator
from .tcp_client import AECCDeviceClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]
SCAN_INTERVAL = timedelta(seconds=10)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _LOGGER.info(f"Setting up AECC device entry {config_entry.data}")

    # 获取配置信息
    host = config_entry.data["device_ip"]
    port = config_entry.data["device_port"]

    # 创建协调器
    coordinator = AECCDataUpdateCoordinator(hass, host, port, SCAN_INTERVAL)
    await coordinator.async_config_entry_first_refresh()

    # 初始化 hass.data[DOMAIN]
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    # 将协调器和配置保存到 hass.data 中
    hass.data[DOMAIN][config_entry.entry_id] = {
        "coordinator": coordinator,
        "config_entry": config_entry,
    }
    # 使用新方法一次性加载所有平台
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # 注册卸载回调
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
    """处理配置条目更新。"""
    await hass.config_entries.async_reload(entry.entry_id)
