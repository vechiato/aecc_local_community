from datetime import timedelta

from .const import DOMAIN
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .tcp_client import AECCDeviceClient
import logging

_LOGGER = logging.getLogger(__name__)

class AECCDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host, port, scan_interval=timedelta(10)):
        super().__init__(
            hass,
            _LOGGER,
            name="AECC Device Coordinator",
            update_interval=scan_interval,
        )
        self.client = AECCDeviceClient(host, port)
        self.devices = {}
    async def _async_update_data(self):
        """Fetch data from AECC device, with auto-reconnect on failure."""
        try:
            # 第一次尝试获取数据
            data = await self.client.fetch_data()
            if data:
                return dict(data)
            else:
                _LOGGER.warning("No data returned on first attempt, retrying after reconnect...")
        except (ConnectionError, ConnectionResetError, OSError) as e:
            _LOGGER.warning(f"Connection error during fetch_data: {e}, attempting reconnect...")

        try:
            # 主动断开并重连
            await self.client.disconnect()  # 确保关闭旧连接
            await self.client.connect()  # 重新建立连接
            _LOGGER.info("Successfully reconnected to AECC device")

            # 重新获取数据
            data = await self.client.fetch_data()
            if data:
                return dict(data)
            else:
                _LOGGER.error("No data returned even after reconnect")
                return {}
        except Exception as e:
            _LOGGER.error(f"Failed to fetch data after reconnect: {e}")
            return {}
