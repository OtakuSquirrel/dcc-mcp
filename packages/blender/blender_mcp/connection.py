"""TCP+JSON connection to Blender addon's socket server.

Blender addon runs a non-blocking TCP socket server on bpy.app.timers.
This module connects to that server and sends JSON-RPC commands.

Port resolution (in priority order):
  1. Explicit port passed to connect()
  2. BLENDER_MCP_PORT environment variable
  3. Auto-discovery: scan configured port range for an active listener
"""

from __future__ import annotations

import json
import logging
import os
import socket
from typing import Any

from dcc_mcp_core.connection import ConnectionBase, ConnectionManagerBase
from dcc_mcp_core.registry import SessionRegistry, is_port_in_use

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 19811
_RECV_SIZE = 1024 * 1024  # 1MB max response


def discover_blender_port(
    get_port_range: callable,
    sessions: list[dict] | None = None,
    timeout: float = 0.15,
) -> int | None:
    """Scan the configured port range for a Blender socket listener.

    Prefers ports without an existing MCP session.
    """
    min_port, max_port = get_port_range()
    logger.info("Scanning ports %d-%d for Blender socket server ...", min_port, max_port)

    session_ports = set()
    if sessions:
        from dcc_mcp_core.registry import is_pid_alive
        for s in sessions:
            mcp_pid = s.get("pid")
            if s.get("port") and mcp_pid and is_pid_alive(mcp_pid):
                session_ports.add(s["port"])

    listening_unlinked = []
    listening_linked = []

    for port in range(min_port, max_port + 1):
        if is_port_in_use(port, timeout):
            if port in session_ports:
                listening_linked.append(port)
            else:
                listening_unlinked.append(port)

    if listening_unlinked:
        port = listening_unlinked[0]
        logger.info("Found unlinked Blender listener on port %d", port)
        return port

    if listening_linked:
        port = listening_linked[0]
        logger.info("Found Blender listener on port %d (already has session)", port)
        return port

    logger.info("No Blender socket listeners found in port range")
    return None


class BlenderConnection(ConnectionBase):
    """Manages a TCP+JSON connection to a running Blender instance.

    The Blender addon must have its socket server running.
    Commands are sent as JSON objects and responses are received as JSON.
    """

    def __init__(self, registry: SessionRegistry, host: str = "localhost", port: int | None = None):
        super().__init__(registry, host, port)
        self._socket: socket.socket | None = None

    def _do_connect(self, host: str, port: int) -> Any:
        """Establish TCP connection to Blender addon."""
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        self._socket = sock
        return sock

    def _do_disconnect(self) -> None:
        """Close the TCP socket."""
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _do_ping(self) -> bool:
        """Ping Blender by sending a ping command."""
        if self._socket is None:
            return False
        try:
            result = self.send_command("ping")
            return result is not None
        except Exception:
            self._socket = None
            return False

    def _get_dcc_info(self) -> tuple[int | None, str]:
        """Query Blender for its PID and version."""
        try:
            result = self.send_command("get_info")
            if result:
                pid = result.get("pid")
                version = result.get("version", "")
                return pid, version
        except Exception:
            pass
        return None, ""

    def send_command(self, command: str, params: dict | None = None) -> Any:
        """Send a JSON-RPC command to Blender and return the result.

        Args:
            command: Command name (e.g. 'create_object', 'ping').
            params: Optional parameters dict.

        Returns:
            The result from Blender (parsed JSON).

        Raises:
            ConnectionError: If not connected or connection lost.
            RuntimeError: If Blender returns an error.
        """
        if self._socket is None:
            raise ConnectionError("Not connected to Blender.")

        request = {"command": command}
        if params:
            request["params"] = params

        data = json.dumps(request) + "\n"

        try:
            self._socket.sendall(data.encode("utf-8"))
            response_data = self._recv_response()
            response = json.loads(response_data)
        except (socket.error, json.JSONDecodeError) as e:
            self._socket = None
            raise ConnectionError(f"Communication error: {e}") from e

        if "error" in response:
            raise RuntimeError(f"Blender error: {response['error']}")

        return response.get("result")

    def _recv_response(self) -> str:
        """Receive a complete JSON response (newline-delimited)."""
        buffer = b""
        while True:
            chunk = self._socket.recv(_RECV_SIZE)
            if not chunk:
                raise ConnectionError("Connection closed by Blender")
            buffer += chunk
            if b"\n" in buffer:
                line, _ = buffer.split(b"\n", 1)
                return line.decode("utf-8")


class BlenderConnectionManager(ConnectionManagerBase):
    """Multi-instance proxy for Blender connections.

    Transparent to tool modules — exposes send_command() on the active connection.
    """

    def __init__(self, registry: SessionRegistry, get_port_range: callable):
        super().__init__(registry)
        self._get_port_range = get_port_range

    def _create_connection(self) -> BlenderConnection:
        return BlenderConnection(self._registry)

    def send_command(self, command: str, params: dict | None = None) -> Any:
        """Send a command via the active connection."""
        active = self._active
        if not isinstance(active, BlenderConnection):
            raise TypeError("Active connection is not a BlenderConnection")
        return active.send_command(command, params)

    def connect(self, port: int | None = None) -> None:
        """Connect to Blender, with auto-discovery if no port specified."""
        if port is None:
            port = self._explicit_port
        if port is None:
            discovered = discover_blender_port(self._get_port_range)
            if discovered:
                port = discovered
            else:
                env_port = os.environ.get("BLENDER_MCP_PORT", "").strip()
                if env_port:
                    try:
                        port = int(env_port)
                    except ValueError:
                        pass
                if port is None:
                    port = _DEFAULT_PORT

        super().connect(port)
