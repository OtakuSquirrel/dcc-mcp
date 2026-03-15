"""Abstract connection base classes for DCC MCP servers.

Provides ConnectionBase (single connection) and ConnectionManagerBase
(multi-instance proxy) that each DCC package subclasses.

Subclasses only need to implement the protocol-specific parts:
- ConnectionBase: _do_connect, _do_disconnect, _do_ping, _get_dcc_info
- ConnectionManagerBase: typically no overrides needed
"""

from __future__ import annotations

import atexit
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from typing import Any

from dcc_mcp_core.registry import SessionRegistry

logger = logging.getLogger(__name__)


class ConnectionBase(ABC):
    """Manages a single connection to a DCC instance.

    Subclasses implement the protocol-specific methods:
    - _do_connect(port): Establish connection, return connection object
    - _do_disconnect(): Close connection
    - _do_ping(): Return True if connection is alive
    - _get_dcc_info(): Return (dcc_pid, version_str) from remote DCC
    """

    def __init__(self, registry: SessionRegistry, host: str = "localhost", port: int | None = None):
        self._registry = registry
        self.host = host
        self._explicit_port = port
        self._session_id: str | None = None
        self._session_registered: bool = False
        self._atexit_registered: bool = False
        self._client_name: str = "Agent"

    @property
    def port(self) -> int | None:
        """Current target port."""
        return self._explicit_port

    # ── Abstract methods (subclass implements) ──

    @abstractmethod
    def _do_connect(self, host: str, port: int) -> Any:
        """Establish connection to the DCC. Return connection object."""
        ...

    @abstractmethod
    def _do_disconnect(self) -> None:
        """Close the connection."""
        ...

    @abstractmethod
    def _do_ping(self) -> bool:
        """Return True if connection is alive."""
        ...

    def _get_dcc_info(self) -> tuple[int | None, str]:
        """Return (dcc_pid, version_string) from the remote DCC.
        Override in subclass for DCC-specific queries.
        """
        return None, ""

    # ── Public API ──

    def connect(self, port: int | None = None) -> None:
        """Establish connection to the DCC instance.

        Args:
            port: Specific port to connect to. If None, uses explicit port.
        """
        # Clean up previous
        self._do_disconnect()
        self._unregister_session()

        if port is not None:
            self._explicit_port = port

        if self._explicit_port is None:
            raise ValueError("No port specified and no default port set.")

        logger.info("Connecting to %s:%d ...", self.host, self._explicit_port)
        self._do_connect(self.host, self._explicit_port)
        logger.info("Connected successfully on port %d.", self._explicit_port)

        self._register_session_lazy()

    def disconnect(self) -> None:
        """Close the connection and unregister the session."""
        self._do_disconnect()
        self._unregister_session()

    def release(self) -> None:
        """Release the connection without notifying the DCC.

        Resets all state so the next connect() starts fresh.
        """
        self._do_disconnect()
        self._unregister_session()
        self._session_id = None
        self._explicit_port = None

    def is_connected(self) -> bool:
        """Check if connection is alive by pinging."""
        try:
            return self._do_ping()
        except Exception:
            return False

    # ── Session registration ──

    def _register_session_lazy(self) -> None:
        """Register this MCP<->DCC pairing in the session registry."""
        if self._session_registered:
            return

        try:
            if self._session_id is None:
                self._session_id = self._registry.generate_session_id()

            mcp_pid = os.getpid()
            dcc_pid, version = self._get_dcc_info()

            self._registry.register_session(
                session_id=self._session_id,
                port=self._explicit_port,
                pid=mcp_pid,
                dcc_pid=dcc_pid,
                version=version,
                launched_by="agent",
                client_name=self._client_name,
            )

            if not self._atexit_registered:
                atexit.register(self._unregister_session)
                self._atexit_registered = True
            self._session_registered = True

            logger.info(
                "Session %s registered (port %d, MCP pid %d, DCC pid %s, ver %s)",
                self._session_id, self._explicit_port, mcp_pid, dcc_pid, version,
            )
        except Exception as e:
            logger.warning("Session registration failed (non-fatal): %s", e)

    def _unregister_session(self) -> None:
        """Remove this session from the registry."""
        if not self._session_registered or self._session_id is None:
            return

        try:
            self._registry.unregister_session(self._session_id)
            logger.info("Session %s unregistered", self._session_id)
        except Exception as e:
            logger.warning("Session unregister failed: %s", e)
        finally:
            self._session_registered = False


class ConnectionManagerBase:
    """Proxy that manages multiple DCC connections.

    Transparent to tool modules — delegates to the "active" connection.
    Maintains a pool of connections keyed by port, with one designated
    as "active".

    Subclasses should override _create_connection() to return their
    DCC-specific ConnectionBase subclass.
    """

    def __init__(self, registry: SessionRegistry):
        self._registry = registry
        self._connections: dict[int, ConnectionBase] = {}
        self._active_port: int | None = None
        self._processes: dict[int, subprocess.Popen] = {}
        self._explicit_port: int | None = None
        self._session_id: str | None = None
        self._client_name: str = "Agent"

    @abstractmethod
    def _create_connection(self) -> ConnectionBase:
        """Create a new DCC-specific connection instance.
        Subclass MUST implement this.
        """
        ...

    # ── Active connection access ──

    @property
    def port(self) -> int | None:
        """Current active port."""
        return self._active_port or self._explicit_port

    def is_connected(self) -> bool:
        """Check if the active connection is alive."""
        if self._active_port is None:
            return False
        active = self._connections.get(self._active_port)
        return active.is_connected() if active else False

    @property
    def _active(self) -> ConnectionBase:
        """Get the active connection. Raises if none."""
        if self._active_port is not None:
            conn = self._connections.get(self._active_port)
            if conn is not None:
                return conn
        raise RuntimeError(
            "No active DCC connection. Use connect() or ensure_ready() first."
        )

    # ── Connection management ──

    def connect(self, port: int | None = None) -> None:
        """Connect to a DCC on the given port."""
        if port is None:
            port = self._explicit_port
        if port is None:
            raise ValueError("No port specified.")

        if port not in self._connections:
            conn = self._create_connection()
            conn._client_name = self._client_name
            self._connections[port] = conn

        self._connections[port].connect(port=port)
        self._active_port = port
        self._explicit_port = port
        self._session_id = self._connections[port]._session_id

    def disconnect(self, port: int | None = None) -> None:
        """Hard disconnect — closes connection to DCC."""
        port = port or self._active_port
        if port and port in self._connections:
            self._connections[port].disconnect()
            del self._connections[port]
            if self._active_port == port:
                self._active_port = next(iter(self._connections), None)
                self._explicit_port = self._active_port
                self._session_id = (
                    self._connections[self._active_port]._session_id
                    if self._active_port else None
                )

    def release(self, port: int | None = None) -> None:
        """Soft disconnect — preserves DCC's listener."""
        port = port or self._active_port
        if port and port in self._connections:
            self._connections[port].release()
            del self._connections[port]
            if self._active_port == port:
                self._active_port = next(iter(self._connections), None)
                self._explicit_port = self._active_port
                self._session_id = (
                    self._connections[self._active_port]._session_id
                    if self._active_port else None
                )

    def switch_active(self, port: int) -> None:
        """Switch which connection is active."""
        if port not in self._connections:
            raise ValueError(
                f"No connection on port {port}. Use connect({port}) first."
            )
        if not self._connections[port].is_connected():
            self._connections[port].connect(port=port)
        self._active_port = port
        self._explicit_port = port
        self._session_id = self._connections[port]._session_id

    def list_connections(self) -> list[dict]:
        """Return info about all managed connections."""
        result = []
        for port, conn in self._connections.items():
            result.append({
                "port": port,
                "connected": conn.is_connected(),
                "active": port == self._active_port,
                "owned": port in self._processes,
                "session_id": conn._session_id,
            })
        return result

    # ── Process ownership tracking ──

    def register_process(self, port: int, proc: subprocess.Popen) -> None:
        """Record that this MCP server launched the DCC on this port."""
        self._processes[port] = proc

    def get_process(self, port: int | None = None) -> subprocess.Popen | None:
        """Get the Popen for a managed DCC process."""
        port = port or self._active_port
        return self._processes.get(port) if port else None

    def unregister_process(self, port: int) -> subprocess.Popen | None:
        """Remove and return the Popen for a managed DCC process."""
        return self._processes.pop(port, None)

    def owned_ports(self) -> list[int]:
        """Ports of DCC processes launched by this MCP."""
        return list(self._processes.keys())
