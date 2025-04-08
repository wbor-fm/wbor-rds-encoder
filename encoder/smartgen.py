"""
Connection manager for the SmartGen Mini RDS encoder. Handles automatic
reconnection (with exponential backoff), starting, stopping, and command
sending.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.0
Last Modified: 2025-03-23

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
"""

import asyncio
import socket
from contextlib import suppress

from utils.decode_rt_plus import decode_rt_plus
from utils.logging import configure_logging

logger = configure_logging(__name__)


class SmartGenConnectionManager:
    """
    Maintains a persistent TCP socket to the SmartGen Mini RDS encoder,
    with automatic reconnection logic.
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self._stop = False
        self._reconnect_task = None

    async def start(self):
        """
        Launch a background task to ensure self.sock remains connected.
        """
        # Use create_task to start a background reconnection manager.
        self._reconnect_task = asyncio.create_task(self._manage_connection())

    async def stop(self):
        """
        Signal the background manager to stop and close socket.
        """
        self._stop = True
        if self._reconnect_task:
            self._reconnect_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reconnect_task

        if self.sock:
            self.sock.close()
            self.sock = None
            logger.info("Closed SmartGen socket.")

    async def _manage_connection(self):
        """
        Continuously ensure there's a valid socket connection to the
        encoder. If the connection drops, retry with exponential
        backoff.
        """
        backoff = 1
        while not self._stop:
            if self.sock is None:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.connect((self.host, self.port))
                    sock.settimeout(self.timeout)
                    self.sock = sock
                    logger.info(
                        "Connected to SmartGen Mini RDS encoder at `%s:%d`",
                        self.host,
                        self.port,
                    )
                    # Reset backoff on successful connect
                    backoff = 1
                except (socket.error, socket.timeout) as e:
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
                # If we already have a socket, just idle until it fails or we're stopped.
                await asyncio.sleep(1)

    def send_command(self, command: str, value: str, truncated_text: str = ""):
        """
        Send a line like `TEXT=HELLO` to the encoder and wait for `OK`
        or `NO`. Raises an exception if no socket is available or if the
        send fails.
        """
        if not self.sock:
            raise ConnectionError("SmartGen socket is not connected.")

        if command == "RT+TAG":
            # Reconstruct the parsed values for logging
            decoded_payload = decode_rt_plus(value, truncated_text)
            logger.debug("Decoded RT+ payload: `%s`", decoded_payload)

        message = f"{command}={value}\r\n"
        logger.info("Sending to encoder: `%s`", message.strip())
        try:
            self.sock.sendall(message.encode("ascii", errors="ignore"))
            response = self.sock.recv(1024).decode("ascii", errors="ignore").strip()
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
        except socket.error as e:
            logger.error("Socket error while sending command to encoder: `%s`", e)
            # Attempt to close so the manager reconnects
            self.sock.close()
            self.sock = None
            raise
        except Exception:
            # Close so the manager attempts a reconnect
            self.sock.close()
            self.sock = None
            raise
