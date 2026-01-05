"""Connection manager for the SmartGen Mini RDS encoder.

Handles automatic reconnection (with exponential backoff), starting, stopping, and
command sending.
"""

import asyncio
from contextlib import suppress

from utils.decode_rt_plus import decode_rt_plus
from utils.logging import configure_logging

logger = configure_logging(__name__)


class SmartGenConnectionManager:
    """Maintains a persistent TCP socket to the SmartGen Mini RDS encoder.

    Provides automatic reconnection logic with exponential backoff.
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._stop = False
        self._reconnect_task = None
        self._connected_event = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Return `True` if the socket is currently connected."""
        return self._writer is not None and not self._writer.is_closing()

    async def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """Wait for the connection to be established.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            `True` if connected, `False` if timeout occurred.
        """
        if self.is_connected:
            return True
        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def start(self):
        """Launch a background task to ensure self.sock remains connected."""
        # Use create_task to start a background reconnection manager.
        self._reconnect_task = asyncio.create_task(self._manage_connection())

    async def stop(self):
        """Signal the background manager to stop and close socket."""
        self._stop = True
        if self._reconnect_task:
            self._reconnect_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reconnect_task

        await self._close_connection()
        logger.info("Closed SmartGen connection.")

    async def _close_connection(self):
        """Close the current connection if open."""
        if self._writer:
            self._writer.close()
            with suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def _manage_connection(self):
        """Continuously ensure there's a valid socket connection to the encoder.

        If the connection drops, retry with exponential backoff.
        """
        backoff = 1
        while not self._stop:
            if not self.is_connected:
                self._connected_event.clear()
                try:
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_connection(self.host, self.port),
                        timeout=self.timeout,
                    )
                    self._connected_event.set()
                    logger.info(
                        "Connected to SmartGen Mini RDS encoder at `%s:%d`",
                        self.host,
                        self.port,
                    )
                    # Reset backoff on successful connect
                    backoff = 1
                except (OSError, asyncio.TimeoutError) as e:
                    logger.error(
                        "Failed to connect to SmartGen RDS encoder at `%s:%d`: %s",
                        self.host,
                        self.port,
                        e,
                    )
                    # Wait before retrying
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)  # Exponential backoff up to 1 min
            else:
                # If we already have a connection, just idle until it fails or we're stopped.
                await asyncio.sleep(1)

    async def send_command(self, command: str, value: str, truncated_text: str = "") -> None:
        """Send a command to the encoder and wait for `OK` or `NO` response.

        Sends a line like `TEXT=HELLO` to the encoder.

        Args:
            command: The command to send (e.g., "TEXT", "RT+TAG").
            value: The value to send (e.g., "HELLO").
            truncated_text: The truncated text for logging purposes.

        Raises:
            ConnectionError: If no socket is available.
            RuntimeError: If the command is rejected or fails.
        """
        if not self.is_connected or not self._writer or not self._reader:
            raise ConnectionError("SmartGen socket is not connected.")

        if command == "RT+TAG":
            # Reconstruct the parsed values for logging
            decoded_payload = decode_rt_plus(value, truncated_text)
            logger.debug("Decoded RT+ payload: `%s`", decoded_payload)

        message = f"{command}={value}\r\n"
        logger.info("Sending to encoder: `%s`", message.strip())

        async with self._lock:
            try:
                self._writer.write(message.encode("ascii", errors="ignore"))
                await self._writer.drain()

                response_bytes = await asyncio.wait_for(
                    self._reader.read(1024),
                    timeout=self.timeout,
                )
                response = response_bytes.decode("ascii", errors="ignore").strip()
                logger.debug("Encoder response: `%s`", response.strip())

                response_lines = response.splitlines()
                if not response_lines:
                    logger.warning("No response from encoder.")
                elif response_lines[0] == "NO":
                    logger.warning(
                        "Command `%s=%s` was rejected by encoder. Response was: `%s`",
                        command,
                        value,
                        response_lines[0],
                    )
                    raise RuntimeError(
                        f"Command `{command}={value}` rejected: `{response.strip()}`"
                    )
                elif response_lines[-1] != "OK":
                    logger.warning(
                        "Command `%s=%s` returned an unexpected response: `%s`",
                        command,
                        value,
                        response_lines,
                    )
                    raise RuntimeError(f"Command `{command}={value}` failed: `{response}`")
            except (OSError, asyncio.TimeoutError) as e:
                logger.error("Error while sending command to encoder: `%s`", e)
                # Close so the manager attempts a reconnect
                await self._close_connection()
                self._connected_event.clear()
                raise
            except Exception:
                # Close so the manager attempts a reconnect
                await self._close_connection()
                self._connected_event.clear()
                raise
