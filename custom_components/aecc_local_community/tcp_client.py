import asyncio
import json
import logging
from typing import Any, Dict, Optional

from .tcp_manager import READ_TIMEOUT_SUSPECT_THRESHOLD, TCPClientManager

_LOGGER = logging.getLogger(__name__)

_REPLY_TIMEOUT = 10  # seconds
_PROBE_TIMEOUT = 3  # DeviceManagement: some firmware never answers it
_REG_WIFI_RSSI = 76  # DeviceManagement register: Wi-Fi signal in dBm
_REG_DATALOGGER_RESTART = "32"  # DeviceManagement register: write 1 to reboot the logger
_RESTART_REPLY_TIMEOUT = 2  # the logger usually drops the socket before replying
_DECODER = json.JSONDecoder()


class _ReadTimeout(Exception):
    """The device accepted the request but never replied."""


class AECCDeviceClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.tcp_manager = TCPClientManager.get_instance(host, port, timeout=5)
        self.serial_number = 0

    async def connect(self):
        # Through the guarded accessor: reuses a live socket instead of leaking one.
        await self.tcp_manager.get_reader_writer()

    async def disconnect(self):
        await self.tcp_manager.close()

    # ── Public API ────────────────────────────────────────────────────────────

    async def fetch_data(self) -> Optional[Dict[str, Any]]:
        return await self._request("Get", "EnergyParameter")

    async def get_control_parameters(self, register_addrs: list) -> Optional[Dict[str, Any]]:
        return await self._request("Get", "Energycontrolparameters", {"RegControlAddr": register_addrs})

    async def set_control_parameters(self, register_values: dict) -> Optional[Dict[str, Any]]:
        _LOGGER.debug("SET control registers: %s", register_values)
        return await self._request("Set", "Energycontrolparameters", {"SetControlInfo": register_values})

    async def send_switch_command(self, attr, switch=False) -> bool:
        """Switch a sub-device (smart plug etc.) on or off."""
        data = await self._request("Set", "SubDeviceControl", {
            "ControlsParameter": {
                "DevTypeClass": 0x200,
                "DevAddr": attr["dev_addr"],
                "IsThirdParty": attr["is_third_party"],
                "CommSerialNum": 963,
                "DevType": 200,
                "Param": {"Switch": 1 if switch else 0, "IsInterconnect": 0},
            }
        })
        if data is not None and "succeed" in str(data):
            return True
        _LOGGER.warning("Switch command failed: %s", data)
        return False

    async def get_wifi_rssi(self) -> Optional[int]:
        """Wi-Fi signal in dBm, or None if the device doesn't report it.

        Only register 76 is requested. The same command also exposes the
        device's Wi-Fi credentials, which must never be read.
        """
        data = await self._request(
            "Get", "DeviceManagement", {"RegDeviceManagementAddr": [_REG_WIFI_RSSI]},
            timeout=_PROBE_TIMEOUT, quiet=True,
        )
        if not data:
            return None
        # Firmware differs on the container key.
        params = next(
            (data[k] for k in ("DeviceManagementInfo", "ControlInfo", "Parameters", "GetParameters")
             if isinstance(data.get(k), dict)),
            {},
        )
        value = params.get(str(_REG_WIFI_RSSI), params.get(_REG_WIFI_RSSI))
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None

    async def restart_datalogger(self) -> bool:
        """Reboot the Wi-Fi datalogger. True once the command was sent.

        The logger usually closes the socket before it can reply, so a missing
        reply or a reset is expected, not a failure. The socket is always closed
        afterwards; the next poll reconnects once the logger is back.
        """
        mgr = self.tcp_manager
        async with mgr.io_lock:
            self.serial_number += 1
            payload = {
                "Set": "DeviceManagement",
                "SerialNumber": self.serial_number,
                "CommandSource": "Web",
                "DeviceManagementAddr": {_REG_DATALOGGER_RESTART: "1"},
            }
            try:
                reader, writer = await mgr.get_reader_writer()
                writer.write(json.dumps(payload).encode() + b"\n")
                await writer.drain()
            except OSError as e:
                _LOGGER.warning("Could not send datalogger restart: %s", e)
                return False
            try:
                reply = await self._read_reply(reader, self.serial_number, _RESTART_REPLY_TIMEOUT)
                _LOGGER.info("Datalogger restart reply: %s", reply)
            except (_ReadTimeout, OSError, asyncio.IncompleteReadError):
                _LOGGER.debug("No reply to datalogger restart (expected while it reboots)")
            finally:
                await mgr.close()
            return True

    async def turn_on_switch(self, attr) -> bool:
        return await self.send_switch_command(attr, True)

    async def turn_off_switch(self, attr) -> bool:
        return await self.send_switch_command(attr, False)

    # ── Transport ─────────────────────────────────────────────────────────────

    async def _request(
        self, verb: str, command: str, extra: dict | None = None,
        timeout: float = _REPLY_TIMEOUT, quiet: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Send one request and return its reply, or None on any failure.

        quiet: log a missing reply at debug level, for optional probes.
        """
        mgr = self.tcp_manager
        async with mgr.io_lock:
            # Fresh serial per request, so a late reply to an earlier one is
            # recognisably not ours.
            self.serial_number += 1
            payload = {verb: command, "SerialNumber": self.serial_number, "CommandSource": "Web", **(extra or {})}
            try:
                reader, writer = await mgr.get_reader_writer()
                writer.write(json.dumps(payload).encode() + b"\n")
                await writer.drain()
                reply = await self._read_reply(reader, self.serial_number, timeout)
                mgr.note_success()
                return reply
            except _ReadTimeout:
                mgr.read_timeout_streak += 1
                _LOGGER.log(
                    logging.DEBUG if quiet else logging.WARNING,
                    "%s %s: no reply within %ss (%d in a row)",
                    verb, command, timeout, mgr.read_timeout_streak,
                )
                if mgr.read_timeout_streak >= READ_TIMEOUT_SUSPECT_THRESHOLD:
                    # Likely half-open: close it so the next request reconnects.
                    _LOGGER.warning("Recycling socket after %d silent reads", mgr.read_timeout_streak)
                    await mgr.close()
                    mgr.read_timeout_streak = 0
                return None
            except (ConnectionResetError, OSError, asyncio.IncompleteReadError) as e:
                # Cooldown read before recording the failure: the first error of
                # an outage waits the base 2s, sustained failures escalate.
                cooldown = mgr.current_cooldown()
                mgr.note_failure()
                _LOGGER.warning(
                    "%s %s connection error: %s; reconnecting after %.0fs cooldown",
                    verb, command, e, cooldown,
                )
                await asyncio.sleep(cooldown)
                try:
                    await mgr.reconnect()
                except (TimeoutError, OSError) as reconnect_error:
                    _LOGGER.debug("Reconnect failed: %s", reconnect_error)
                return None
            except Exception as e:
                _LOGGER.error("%s %s error: %s", verb, command, e, exc_info=True)
                return None

    async def _read_reply(self, reader: asyncio.StreamReader, expected_serial: int, timeout: float) -> Dict[str, Any]:
        """Return the reply matching ``expected_serial``.

        Replies are decoded one whole JSON object at a time from a buffer that
        survives across requests. A reply to an earlier request (one that timed
        out and answered late) is discarded instead of being handed to this
        caller. A reply without a serial is accepted as-is.
        """
        mgr = self.tcp_manager
        try:
            async with asyncio.timeout(timeout):
                while True:
                    while True:
                        try:
                            text = mgr.rx_buffer.decode("utf-8").lstrip()
                            data, end = _DECODER.raw_decode(text)
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            break  # incomplete frame, read more
                        mgr.rx_buffer = text[end:].encode("utf-8")
                        if not isinstance(data, dict):
                            continue
                        serial = data.get("SerialNumber")
                        # str(): tolerate firmware echoing the serial as a string.
                        if serial is not None and str(serial) != str(expected_serial):
                            _LOGGER.debug("Discarding stale reply serial %s, expected %s", serial, expected_serial)
                            continue
                        return data
                    chunk = await reader.read(4096)
                    if not chunk:
                        raise ConnectionResetError("Device closed the connection")
                    mgr.rx_buffer += chunk
        except TimeoutError:
            raise _ReadTimeout from None
