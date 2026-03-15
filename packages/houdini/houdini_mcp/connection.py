"""RPyC connection to Houdini — rewrite using dcc-mcp-core.

Houdini exposes hrpyc (RPyC classic mode). We connect and get full
access to the `hou` module through the connection.

Port resolution:
  1. Explicit port from CLI --port
  2. HOUDINI_MCP_PORT env var
  3. Auto-discovery: scan configured port range
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Any

import rpyc

from dcc_mcp_core.connection import ConnectionBase, ConnectionManagerBase
from dcc_mcp_core.registry import SessionRegistry, is_port_in_use

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 18811


def discover_rpyc_port(
    get_port_range: callable,
    sessions: list[dict] | None = None,
    timeout: float = 0.15,
) -> int | None:
    """Scan the configured port range for a Houdini RPyC listener."""
    min_port, max_port = get_port_range()
    logger.info("Scanning ports %d-%d for Houdini RPyC ...", min_port, max_port)

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
        return listening_unlinked[0]
    if listening_linked:
        return listening_linked[0]
    return None


class HoudiniConnection(ConnectionBase):
    """Manages an RPyC connection to a running Houdini instance."""

    def __init__(self, registry: SessionRegistry, host: str = "localhost", port: int | None = None):
        super().__init__(registry, host, port)
        self._conn: rpyc.Connection | None = None

    @property
    def conn(self) -> rpyc.Connection:
        """Get the raw RPyC connection."""
        if self._conn is None:
            raise RuntimeError("Not connected to Houdini.")
        return self._conn

    @property
    def hou(self):
        """Get the remote hou module."""
        return self.conn.modules.hou

    def _do_connect(self, host: str, port: int) -> Any:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = rpyc.classic.connect(host, port)
        return self._conn

    def _do_disconnect(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _do_ping(self) -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.ping()
            return True
        except Exception:
            self._conn = None
            return False

    def _get_dcc_info(self) -> tuple[int | None, str]:
        try:
            dcc_pid = self._conn.modules.os.getpid()
        except Exception:
            dcc_pid = None
        try:
            ver = self._conn.modules.hou.applicationVersionString()
        except Exception:
            ver = ""
        return dcc_pid, ver


class HoudiniConnectionManager(ConnectionManagerBase):
    """Multi-instance proxy for Houdini connections.

    Transparent to tool modules — exposes .hou and .conn on the active connection.
    """

    def __init__(self, registry: SessionRegistry, get_port_range: callable):
        super().__init__(registry)
        self._get_port_range = get_port_range

    def _create_connection(self) -> HoudiniConnection:
        return HoudiniConnection(self._registry)

    @property
    def hou(self):
        """Get the remote hou module from the active connection."""
        active = self._active
        if not isinstance(active, HoudiniConnection):
            raise TypeError("Active connection is not a HoudiniConnection")
        return active.hou

    @property
    def conn(self) -> rpyc.Connection:
        """Get the raw RPyC connection from the active connection."""
        active = self._active
        if not isinstance(active, HoudiniConnection):
            raise TypeError("Active connection is not a HoudiniConnection")
        return active.conn

    def connect(self, port: int | None = None) -> None:
        """Connect to Houdini, with auto-discovery if no port specified."""
        if port is None:
            port = self._explicit_port
        if port is None:
            discovered = discover_rpyc_port(self._get_port_range)
            if discovered:
                port = discovered
            else:
                env_port = os.environ.get("HOUDINI_MCP_PORT", "").strip()
                if env_port and env_port != "auto":
                    try:
                        port = int(env_port)
                    except ValueError:
                        pass
                if port is None:
                    port = _DEFAULT_PORT

        super().connect(port)
