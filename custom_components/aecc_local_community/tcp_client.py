import asyncio
import logging
import json
from typing import Optional, Dict, Any, Tuple
from .tcp_manager import TCPClientManager

_LOGGER = logging.getLogger(__name__)

class AECCDeviceClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.tcp_manager = TCPClientManager.get_instance(host, port,timeout=5)
        self.serial_number = 1  # 可改为动态生成或从配置中读取

    async def connect(self):
        """确保连接已建立"""
        await self.tcp_manager.connect()

    async def fetch_data(self) -> Optional[Dict[str, Any]]:
        """发送请求并获取设备数据"""
        try:
            _, writer = await self.tcp_manager.get_reader_writer()

            request = {
                "Get": "EnergyParameter",
                "SerialNumber": self.serial_number,
                "CommandSource": "Web"
            }

            # 发送 JSON 请求
            writer.write(json.dumps(request).encode() + b'\n')
            await writer.drain()
            _LOGGER.info(f"Sent request: {request}")

            buffer = b''
            while True:
                reader, _ = await self.tcp_manager.get_reader_writer()
                chunk = await reader.read(4096)
                if not chunk:
                    raise ConnectionResetError("Device closed the connection")
                buffer += chunk
                try:
                    json_data = json.loads(buffer.decode('utf-8'))
                    _LOGGER.info(f"Received raw response: {json_data}")
                    self.serial_number += 1
                    return json_data
                except json.JSONDecodeError:
                    await asyncio.sleep(0.1)  # 继续等待更多数据

        except (ConnectionResetError, OSError, asyncio.IncompleteReadError) as e:
            _LOGGER.warning(f"Connection error during fetch_data: {e}, reconnecting...")
            await self.tcp_manager.reconnect()
            return None
        except Exception as e:
            _LOGGER.error(f"Error fetching data from AECC device: {e}", exc_info=True)
            return None

    async def send_switch_command(self,attr,switch=False) -> bool:
        """
        发送插座开关控制命令
        :param dev_addr:
        :param dev_addr: 插座地址（如 PlugSN 对应的地址）
        :param switch_on: True=开，False=关
        :param dev_type: 设备类型，默认为 200（可按需修改）
        :return: 成功返回 True，失败返回 False
        """
        try:
            _, writer = await self.tcp_manager.get_reader_writer()
            _LOGGER.info(f"Send switch command: {attr}")
            request = {
                "Set": "SubDeviceControl",
                "SerialNumber": self.serial_number,
                "CommandSource": "Web",
                "ControlsParameter": {
                    "DevTypeClass": 0x200,
                    "DevAddr": attr['dev_addr'],
                    "IsThirdParty": attr['is_third_party'],
                    "CommSerialNum": 963,
                    "DevType": 200,
                    "Param": {
                        "Switch": 1 if switch else 0,
                        "IsInterconnect": 0
                    }
                }
            }
            _LOGGER.info(f"req: {request}")
            writer.write(json.dumps(request).encode() + b'\n')
            await writer.drain()
            _LOGGER.info(f"Sent switch command: {request}")

            # 等待响应
            data =''
            buffer = b''
            while True:
                reader, _ = await self.tcp_manager.get_reader_writer()
                chunk = await reader.read(4096)
                if not chunk:
                    raise ConnectionResetError("Device closed the connection")
                buffer += chunk
                try:
                    json_data = json.loads(buffer.decode('utf-8'))
                    _LOGGER.info(f"response: {json_data}")
                    data=json_data
                    self.serial_number += 1
                    break
                except json.JSONDecodeError:
                    await asyncio.sleep(0.1)  # 继续等待更多数据

            # response = json.loads(data.decode().strip())
            _LOGGER.info(f"Switch command response: {data}")

            if str(data).__contains__("succeed"):
                self.serial_number += 1
                return True
            else:
                _LOGGER.warning(f"Switch command failed: {data}")
                return False

        except (ConnectionResetError, OSError, asyncio.IncompleteReadError) as e:
            _LOGGER.warning(f"Connection error during send_switch_command: {e}, reconnecting...")
            await self.tcp_manager.reconnect()
            return False
        except Exception as e:
            _LOGGER.error(f"Error sending switch command to AECC device: {e}", exc_info=True)
            return False

    async def turn_on_switch(self, attr) -> bool:
        return await self.send_switch_command(attr,True)

    async def turn_off_switch(self, attr) -> bool:
        return await self.send_switch_command(attr,False)

    async def disconnect(self):
        """主动关闭连接"""
        await self.tcp_manager.close()