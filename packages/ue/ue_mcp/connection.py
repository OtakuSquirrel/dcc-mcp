"""TCP connection to Unreal Engine's Python Remote Execution plugin.

UE's Remote Execution plugin accepts Python commands over a simple TCP
protocol. We send Python code strings and receive execution results.

Protocol: UE Remote Execution uses a specific binary format with
a magic header, but we use the simplified TCP text mode for now.

Port resolution:
  1. Explicit port from CLI --port
  2. UE_MCP_PORT env var
  3. Default: 20811
"""

from __future__ import annotations

import json
import logging
import os
import socket
import struct
from typing import Any

from dcc_mcp_core.connection import ConnectionBase, ConnectionManagerBase
from dcc_mcp_core.registry import SessionRegistry, is_port_in_use

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 20811

# UE Remote Execution protocol constants
_MAGIC = b"ue_py"  # 5-byte magic header
_ENCODING = "utf-8"


def discover_ue_port(
    get_port_range: callable,
    timeout: float = 0.15,
) -> int | None:
    """Scan the configured port range for a UE Remote Execution listener."""
    min_port, max_port = get_port_range()
    for port in range(min_port, max_port + 1):
        if is_port_in_use(port, timeout):
            return port
    return None


class UEConnection(ConnectionBase):
    """Manages a TCP connection to UE's Remote Execution plugin."""

    def __init__(self, registry: SessionRegistry, host: str = "localhost", port: int | None = None):
        super().__init__(registry, host, port)
        self._socket: socket.socket | None = None

    def _do_connect(self, host: str, port: int) -> Any:
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
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _do_ping(self) -> bool:
        if self._socket is None:
            return False
        try:
            result = self.execute_python("print('pong')")
            return result is not None
        except Exception:
            self._socket = None
            return False

    def _get_dcc_info(self) -> tuple[int | None, str]:
        try:
            result = self.execute_python(
                "import unreal; result = str(unreal.SystemLibrary.get_engine_version())"
            )
            return None, result.get("output", "")
        except Exception:
            return None, ""

    def execute_python(self, code: str) -> dict:
        """Execute Python code in UE via Remote Execution.

        Args:
            code: Python code to execute.

        Returns:
            Dict with execution output.
        """
        if self._socket is None:
            raise ConnectionError("Not connected to UE.")

        # Send the Python command
        encoded = code.encode(_ENCODING)
        # Simple framing: length-prefixed message
        header = struct.pack("!I", len(encoded))
        self._socket.sendall(header + encoded)

        # Receive response
        resp_header = self._recv_exact(4)
        resp_len = struct.unpack("!I", resp_header)[0]
        resp_data = self._recv_exact(resp_len)
        output = resp_data.decode(_ENCODING)

        return {"output": output, "success": True}

    def _recv_exact(self, n: int) -> bytes:
        """Receive exactly n bytes."""
        data = b""
        while len(data) < n:
            chunk = self._socket.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed by UE")
            data += chunk
        return data


class UEConnectionManager(ConnectionManagerBase):
    """Multi-instance proxy for UE connections."""

    def __init__(self, registry: SessionRegistry, get_port_range: callable):
        super().__init__(registry)
        self._get_port_range = get_port_range

    def _create_connection(self) -> UEConnection:
        return UEConnection(self._registry)

    def execute_python(self, code: str) -> dict:
        """Execute Python code via the active connection."""
        active = self._active
        if not isinstance(active, UEConnection):
            raise TypeError("Active connection is not a UEConnection")
        return active.execute_python(code)

    def connect(self, port: int | None = None) -> None:
        """Connect to UE, with auto-discovery if no port specified."""
        if port is None:
            port = self._explicit_port
        if port is None:
            discovered = discover_ue_port(self._get_port_range)
            if discovered:
                port = discovered
            else:
                env_port = os.environ.get("UE_MCP_PORT", "").strip()
                if env_port:
                    try:
                        port = int(env_port)
                    except ValueError:
                        pass
                if port is None:
                    port = _DEFAULT_PORT
        super().connect(port)
