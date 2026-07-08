"""Transport pool — routes each port to the right protocol adapter.

The daemon owns exactly one :class:`TransportPool`. Callers name a port;
the pool picks the adapter by the port's conventional DCC range:

  * Houdini range  → :class:`RpycAdapter`      (hot-pluggable ``hrpyc``)
  * everything else → :class:`JsonSocketAdapter` (vendored socket plugin)

Adapters are opened lazily per port, reused, and dropped on error
(reconnect on next call). A per-port lock serializes concurrent calls to
the same instance — a DCC main thread does one thing at a time.

``DCCError`` is re-exported here so existing imports
(``from dcc_daemon.transport import DCCError``) keep working.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from dcc_daemon import config
from dcc_daemon.adapters.base import Adapter, DCCError
from dcc_daemon.adapters.json_socket import JsonSocketAdapter
from dcc_daemon.adapters.rpyc_adapter import RpycAdapter

__all__ = ["DCCError", "TransportPool", "adapter_for_port"]

logger = logging.getLogger(__name__)


def adapter_for_port(port: int, host: str = "127.0.0.1") -> Adapter:
    """Construct (not connect) the adapter appropriate for ``port``."""
    if config.kind_for_port(port) == "houdini":
        return RpycAdapter(port, host)
    return JsonSocketAdapter(port, host)


class TransportPool:
    def __init__(self):
        self._conns: dict[int, Adapter] = {}
        self._locks: dict[int, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    def _lock_for(self, port: int) -> threading.Lock:
        with self._registry_lock:
            return self._locks.setdefault(port, threading.Lock())

    def execute_python(self, port: int, code: str) -> Any:
        """Run ``code`` inside the DCC on ``port`` and return its result."""
        lock = self._lock_for(port)
        with lock:
            conn = self._get_or_open(port)
            try:
                return conn.execute_python(code)
            except ConnectionError:
                self._conns.pop(port, None)
                # one automatic reconnect+retry — DCC may have restarted
                conn = self._get_or_open(port)
                return conn.execute_python(code)

    def ping(self, port: int) -> bool:
        lock = self._lock_for(port)
        with lock:
            try:
                conn = self._get_or_open(port)
            except (OSError, EOFError):
                return False
            ok = conn.ping()
            if not ok:
                self._conns.pop(port, None)
            return ok

    def get_info(self, port: int) -> dict:
        lock = self._lock_for(port)
        with lock:
            conn = self._get_or_open(port)
            return conn.get_info()

    def screenshot(self, port: int) -> str:
        lock = self._lock_for(port)
        with lock:
            conn = self._get_or_open(port)
            return conn.screenshot()

    def _get_or_open(self, port: int) -> Adapter:
        conn = self._conns.get(port)
        if conn is None:
            conn = adapter_for_port(port)
            conn.connect()
            self._conns[port] = conn
        return conn

    def drop(self, port: int) -> None:
        conn = self._conns.pop(port, None)
        if conn is not None:
            conn.close()
