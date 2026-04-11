from __future__ import annotations

import json
import socket
import time
from pathlib import Path


DEFAULT_SOCKET = Path.home() / ".cache" / "pc-e500-expd.sock"
RUST_DAEMON_SOCKET = Path("/tmp/pc-e500-expd-rs.sock")
PYTHON_DAEMON_SOCKET = Path("/tmp/pc-e500-expd-py.sock")
CONNECT_RETRIES = 5
CONNECT_RETRY_DELAY_S = 0.05


def resolve_socket(socket_path: Path) -> Path:
    if socket_path.exists():
        return socket_path
    if socket_path == DEFAULT_SOCKET:
        for candidate in (RUST_DAEMON_SOCKET, PYTHON_DAEMON_SOCKET):
            if candidate.exists():
                return candidate
    return socket_path


def send_request(socket_path: Path, payload: dict[str, object]) -> dict[str, object]:
    resolved_socket = resolve_socket(socket_path)
    response = bytearray()
    last_error: OSError | None = None
    for attempt in range(CONNECT_RETRIES):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(resolved_socket))
                client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response.extend(chunk)
                    if b"\n" in chunk:
                        break
            last_error = None
            break
        except (ConnectionRefusedError, FileNotFoundError) as exc:
            last_error = exc
            if attempt == CONNECT_RETRIES - 1:
                raise
            time.sleep(CONNECT_RETRY_DELAY_S)
    if last_error is not None:
        raise last_error
    if not response:
        raise RuntimeError("daemon returned no response")
    return json.loads(response.decode("utf-8"))
