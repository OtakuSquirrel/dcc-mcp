"""Adapter interface + shared helpers for talking to one DCC instance.

An *adapter* owns the connection to a single DCC on a known port and
implements the four operations the daemon needs. Two concrete adapters
exist:

  * :class:`~dcc_daemon.adapters.json_socket.JsonSocketAdapter` —
    newline-delimited JSON to the vendored socket-server plugin
    (Blender, Unreal).
  * :class:`~dcc_daemon.adapters.rpyc_adapter.RpycAdapter` — RPyC classic
    to Houdini's built-in ``hrpyc`` server (hot-pluggable: started from
    Houdini's Python shell, no addon install).

Which adapter a port gets is decided by :class:`TransportPool` from the
port's conventional range, so callers never care about the protocol —
the port identifies the instance, the adapter hides the wire.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DCCError(RuntimeError):
    """The DCC executed the command but it raised inside the DCC process.

    Distinct from ``ConnectionError`` (transport failed) — a ``DCCError``
    means the round-trip succeeded but the code itself failed.
    """

    def __init__(self, message: str, traceback: str | None = None):
        super().__init__(message)
        self.traceback = traceback


def to_jsonable(value: Any) -> Any:
    """Best-effort conversion of a value to something JSON-serializable.

    Mirrors the socket plugin's contract: JSON-serializable values pass
    through; everything else becomes its ``repr``. ``None`` stays
    ``None``.
    """
    if value is None:
        return None
    import json

    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


class Adapter(ABC):
    """Connection to one DCC instance on ``port``. Not thread-safe;
    :class:`TransportPool` serializes calls with a per-port lock."""

    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.port = port
        self.host = host

    @abstractmethod
    def connect(self) -> None:
        """Open (or reopen) the connection. Raises on failure."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection; safe to call when already closed."""

    @abstractmethod
    def execute_python(self, code: str) -> Any:
        """Run ``code`` in the DCC; return whatever it assigns to
        ``result`` (JSON-normalized), or ``None``."""

    @abstractmethod
    def ping(self) -> bool:
        """Cheap liveness check. Never raises — returns False on failure."""

    @abstractmethod
    def get_info(self) -> dict:
        """Return identity: ``{"kind","version","pid","file", ...}``."""

    @abstractmethod
    def screenshot(self) -> str:
        """Return a base64-encoded PNG of the viewport/render."""
