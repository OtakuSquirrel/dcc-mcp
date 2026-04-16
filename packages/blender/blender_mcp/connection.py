"""TCP+JSON connection to Blender addon — stateless port-keyed cache.

Every send_command call names the target port. Connections are opened
lazily on first use for a port, reused on subsequent calls to the same
port, and dropped on connection error (will reconnect on next call).

There is no 'active port', no session registry, no client-name tracking.
Claude addresses each Blender instance directly by port and remembers
port→instance mappings in its own conversation context.
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import threading
from typing import Any

logger = logging.getLogger(__name__)

_RECV_SIZE = 1024 * 1024


class BlenderConnection:
    """Raw TCP+JSON connection to one Blender instance on a known port."""

    def __init__(self, host: str = "localhost"):
        self.host = host
        self._socket: socket.socket | None = None
        self._port: int | None = None

    def connect(self, port: int) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((self.host, port))
        self._socket = sock
        self._port = port

    def disconnect(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
            self._port = None

    def is_connected(self) -> bool:
        if self._socket is None:
            return False
        try:
            return self._ping()
        except Exception:
            return False

    def _ping(self) -> bool:
        return self.send_command("ping") is not None

    def send_command(self, command: str, params: dict | None = None) -> Any:
        if self._socket is None:
            raise ConnectionError("Not connected.")
        request: dict[str, Any] = {"command": command}
        if params:
            request["params"] = params
        data = json.dumps(request) + "\n"
        try:
            self._socket.sendall(data.encode("utf-8"))
            response_data = self._recv_response()
            response = json.loads(response_data)
        except (OSError, json.JSONDecodeError) as e:
            self._socket = None
            self._port = None
            raise ConnectionError(f"Communication error: {e}") from e
        if "error" in response:
            raise RuntimeError(f"Blender error: {response['error']}")
        return response.get("result")

    def _recv_response(self) -> str:
        buffer = b""
        while True:
            if self._socket is None:
                raise ConnectionError("Connection lost during recv")
            chunk = self._socket.recv(_RECV_SIZE)
            if not chunk:
                raise ConnectionError("Connection closed by Blender")
            buffer += chunk
            if b"\n" in buffer:
                line, _ = buffer.split(b"\n", 1)
                return line.decode("utf-8")


class BlenderConnectionManager:
    """Lazy port-keyed connection cache with per-port locks.

    No 'active port'. Every call names a port. Connections are opened
    lazily on first use for a port, reused on subsequent calls to the
    same port, and dropped on connection error.
    """

    def __init__(self):
        self._connections: dict[int, BlenderConnection] = {}
        self._processes: dict[int, subprocess.Popen] = {}
        self._locks: dict[int, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    def send_command(
        self, port: int, command: str, params: dict | None = None
    ) -> Any:
        """Send a command to the Blender instance on the given port."""
        lock = self._get_lock(port)
        with lock:
            conn = self._get_or_open(port)
            try:
                return conn.send_command(command, params)
            except ConnectionError:
                # Drop dead connection; next call will reconnect.
                self._connections.pop(port, None)
                raise

    def _get_lock(self, port: int) -> threading.Lock:
        with self._registry_lock:
            if port not in self._locks:
                self._locks[port] = threading.Lock()
            return self._locks[port]

    def _get_or_open(self, port: int) -> BlenderConnection:
        conn = self._connections.get(port)
        if conn is None:
            conn = BlenderConnection()
            conn.connect(port=port)
            self._connections[port] = conn
        return conn

    def drop_connection(self, port: int) -> None:
        """Close and forget the connection for a port (used by stop_blender)."""
        conn = self._connections.pop(port, None)
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:
                pass

    def register_process(self, port: int, proc: subprocess.Popen) -> None:
        """Record that this MCP server launched a Blender process on this port."""
        self._processes[port] = proc

    def get_process(self, port: int) -> subprocess.Popen | None:
        return self._processes.get(port)

    def unregister_process(self, port: int) -> subprocess.Popen | None:
        return self._processes.pop(port, None)

    def is_alive(self, port: int) -> bool:
        """Quick check without sending a command — is the port listening?"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(("localhost", port)) == 0
