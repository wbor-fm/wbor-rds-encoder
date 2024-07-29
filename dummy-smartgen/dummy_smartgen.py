"""
Simple dummy server to simulate a SmartGen device for testing purposes.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.0
Last Modified: 2025-03-23

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
"""

import signal
import socket
import sys

HOST = "0.0.0.0"  # Listen on all interfaces
PORT = 5000

# Global server socket
server_socket = None


def handle_signal(signum, frame):
    """Gracefully shuts down the server on SIGINT or SIGTERM."""
    print("\nShutting down server...")
    if server_socket:
        server_socket.close()
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def start_server():
    """
    Starts a TCP server that listens for incoming connections and echoes
    back received messages.

    The server runs indefinitely until interrupted (SIGINT or SIGTERM).
    """
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)

    print(f"Dummy SmartGen server listening on {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server_socket.accept()
            print(f"Connection received from {addr}")
            with conn:
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break  # Client disconnected
                    message = data.decode("ascii", errors="ignore").strip()
                    print(f"Received message: {message}")

                    # Echo the received command with an "OK" response
                    # (always)
                    response = "OK"
                    conn.sendall(response.encode("ascii"))

    except KeyboardInterrupt:
        handle_signal(signal.SIGINT, None)

    finally:
        server_socket.close()
        print("Server shut down cleanly.")


if __name__ == "__main__":
    start_server()
