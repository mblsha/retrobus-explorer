from __future__ import annotations

import socket
import threading
from pathlib import Path
from tempfile import gettempdir

from pce500_host import supervisor_client


def test_resolve_socket_prefers_existing_default_fallback(tmp_path, monkeypatch):
    default_socket = tmp_path / "default.sock"
    rust_socket = tmp_path / "rust.sock"
    python_socket = tmp_path / "python.sock"
    rust_socket.touch()

    monkeypatch.setattr(supervisor_client, "DEFAULT_SOCKET", default_socket)
    monkeypatch.setattr(supervisor_client, "RUST_DAEMON_SOCKET", rust_socket)
    monkeypatch.setattr(supervisor_client, "PYTHON_DAEMON_SOCKET", python_socket)

    assert supervisor_client.resolve_socket(default_socket) == rust_socket


def test_resolve_socket_prefers_python_when_rust_missing(tmp_path, monkeypatch):
    default_socket = tmp_path / "default.sock"
    rust_socket = tmp_path / "rust.sock"
    python_socket = tmp_path / "python.sock"
    python_socket.touch()

    monkeypatch.setattr(supervisor_client, "DEFAULT_SOCKET", default_socket)
    monkeypatch.setattr(supervisor_client, "RUST_DAEMON_SOCKET", rust_socket)
    monkeypatch.setattr(supervisor_client, "PYTHON_DAEMON_SOCKET", python_socket)

    assert supervisor_client.resolve_socket(default_socket) == python_socket


def test_send_request_retries_after_connection_refused(tmp_path, monkeypatch):
    socket_path = Path(gettempdir()) / "pce500_host_retry.sock"
    if socket_path.exists():
        socket_path.unlink()
    monkeypatch.setattr(supervisor_client, "CONNECT_RETRIES", 8)
    monkeypatch.setattr(supervisor_client, "CONNECT_RETRY_DELAY_S", 0.01)

    def delayed_server():
        import time

        time.sleep(0.02)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(socket_path))
            server.listen(1)
            conn, _ = server.accept()
            with conn:
                _ = conn.recv(4096)
                conn.sendall(b'{"status":"ok","value":1}\n')

    thread = threading.Thread(target=delayed_server, daemon=True)
    thread.start()
    response = supervisor_client.send_request(socket_path, {"action": "status"})
    thread.join(timeout=1.0)
    if socket_path.exists():
        socket_path.unlink()

    assert response["status"] == "ok"
    assert response["value"] == 1
