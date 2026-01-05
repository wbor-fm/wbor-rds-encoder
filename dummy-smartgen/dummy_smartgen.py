"""
Simple dummy server to simulate a SmartGen device for testing purposes.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.1
Last Modified: 2025-05-17

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
    - 1.0.1 (2025-05-17): Refactor to avoid global variables
"""

import logging
import signal
import socket
import sys

HOST = "0.0.0.0"  # Listen on all interfaces
PORT = 5000


def start_server():
    """Start a TCP server that listens for connections and echoes messages.

    The server runs indefinitely until interrupted (SIGINT or SIGTERM).

    All received messages receive an `'OK'` response.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)

    def handle_signal(_signum, _frame):
        logger.info("Shutting down server...")
        server_socket.close()
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("Dummy SmartGen server listening on %s:%d", HOST, PORT)

    try:
        while True:
            conn, addr = server_socket.accept()
            logger.info("Connection received from %s", addr)
            with conn:
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break  # Client disconnected
                    message = data.decode("ascii", errors="ignore").strip()
                    logger.info("Received message: %s", message)

                    # Echo the received command with an "OK" response
                    # (always)
                    response = "OK"
                    conn.sendall(response.encode("ascii"))

    except KeyboardInterrupt:
        handle_signal(None, None)

    finally:
        server_socket.close()
        logger.info("Server shut down cleanly.")


if __name__ == "__main__":
    start_server()
