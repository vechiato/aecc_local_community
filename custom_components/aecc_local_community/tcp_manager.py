"""Persistent TCP connection per (host, port), shared by every client of that device.

Transport hardening ported from StekkerDeal/aecc-battery-local v1.4.1-v1.7.1:
reconnect backoff, lock-safe reconnect, closing the old socket before opening a
new one, and recycling a half-open socket after repeated silent reads.
"""
import asyncio
import logging
from typing import Dict, Optional, Tuple

_LOGGER = logging.getLogger(__name__)

RECONNECT_BASE_COOLDOWN = 2.0   # seconds; first retry delay, matches the old flat delay
RECONNECT_MAX_COOLDOWN = 60.0   # cap on the escalating cooldown
READ_TIMEOUT_SUSPECT_THRESHOLD = 3  # consecutive silent reads before recycling the socket


class TCPClientManager:
    _connections: Dict[Tuple[str, int], "TCPClientManager"] = {}
    DEFAULT_TIMEOUT = 5  # connect timeout (seconds)

    def __init__(self, host: str, port: int, timeout: Optional[float] = None):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self._lock = asyncio.Lock()  # guards connect/close
        # Held for a whole request/reply exchange so a poll and a control write
        # can't interleave on the socket and read each other's replies.
        self.io_lock = asyncio.Lock()
        # Unconsumed bytes from the current socket, kept across reads so a reply
        # cut off by a timeout can complete later and be discarded by serial.
        self.rx_buffer = b""
        self.consecutive_failures = 0
        self.read_timeout_streak = 0

    @classmethod
    def get_instance(cls, host: str, port: int, timeout: Optional[float] = None) -> "TCPClientManager":
        key = (host, port)
        if key not in cls._connections:
            cls._connections[key] = TCPClientManager(host, port, timeout)
        return cls._connections[key]

    async def get_reader_writer(self):
        async with self._lock:
            if not self.writer or self.writer.is_closing():
                await self._connect()
            return self.reader, self.writer

    async def _connect(self):
        # Close the previous socket first: some firmware serves one client at a
        # time, and an abandoned socket keeps the session and locks out new ones.
        # Callers hold _lock, so call _close() directly.
        await self._close()
        _LOGGER.info("Connecting to %s:%s (timeout %ss)", self.host, self.port, self.timeout)
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
        except (TimeoutError, OSError) as e:
            _LOGGER.error("Connection to %s:%s failed: %s", self.host, self.port, e or "timed out")
            raise
        _LOGGER.info("Connected to device at %s:%s", self.host, self.port)

    async def _close(self):
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except OSError:
                pass
            _LOGGER.info("Closed connection to %s:%s", self.host, self.port)
        self.reader = None
        self.writer = None
        self.rx_buffer = b""

    async def close(self):
        async with self._lock:
            await self._close()

    async def reconnect(self):
        _LOGGER.info("Reconnecting to %s:%s", self.host, self.port)
        async with self._lock:
            await self._connect()

    # ── Backoff ───────────────────────────────────────────────────────────────

    def current_cooldown(self) -> float:
        """Cooldown before the next reconnect: 2s, 4s, 8s ... capped at 60s."""
        return min(RECONNECT_BASE_COOLDOWN * (2 ** min(self.consecutive_failures, 5)), RECONNECT_MAX_COOLDOWN)

    def note_failure(self) -> None:
        self.consecutive_failures += 1

    def note_success(self) -> None:
        self.consecutive_failures = 0
        self.read_timeout_streak = 0
