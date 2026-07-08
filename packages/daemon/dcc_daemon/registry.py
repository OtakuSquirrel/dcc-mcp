"""Live DCC instance discovery.

Replaces the old per-server session registry + 40-odd session/pool/scan
tools. The daemon does not persist a session file; it discovers what is
actually running by probing the port pool and asking each listener to
identify itself over the unified ``get_info`` command.

Results are cached briefly so back-to-back ``list_instances`` calls (and
the WebUI polling) don't re-scan the whole range every time.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from dcc_daemon import config
from dcc_daemon.transport import TransportPool

logger = logging.getLogger(__name__)

_CACHE_TTL = 3.0  # seconds


@dataclass
class Instance:
    port: int
    kind: str | None = None          # blender | houdini | ue | None
    version: str = ""
    pid: int | None = None
    file: str = ""
    reachable: bool = True
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "kind": self.kind,
            "version": self.version,
            "pid": self.pid,
            "file": self.file,
            "reachable": self.reachable,
            **({"extra": self.extra} if self.extra else {}),
        }


def _port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.15) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


class InstanceRegistry:
    """Discovers and caches the set of live DCC instances."""

    def __init__(self, transport: TransportPool):
        self._transport = transport
        self._lock = threading.Lock()
        self._cache: list[Instance] = []
        self._cache_at: float = 0.0

    def list_instances(self, *, refresh: bool = False, clock: float | None = None) -> list[Instance]:
        now = clock if clock is not None else time.monotonic()
        with self._lock:
            if not refresh and (now - self._cache_at) < _CACHE_TTL and self._cache:
                return list(self._cache)
        instances = self._scan()
        with self._lock:
            self._cache = instances
            self._cache_at = now
        return list(instances)

    def get(self, port: int) -> Instance | None:
        for inst in self.list_instances():
            if inst.port == port:
                return inst
        return self._probe(port)

    def _scan(self) -> list[Instance]:
        ports = config.dcc_ports()
        # Parallel liveness probe first — serial connect_ex across the pool
        # would be slow. Then only identify the few actually listening.
        with ThreadPoolExecutor(max_workers=min(128, max(1, len(ports)))) as pool:
            listening = [p for p, alive in
                         zip(ports, pool.map(_port_listening, ports)) if alive]
        if not listening:
            return []
        with ThreadPoolExecutor(max_workers=min(16, len(listening))) as pool:
            probed = list(pool.map(self._probe, listening))
        return [i for i in probed if i is not None]

    def _probe(self, port: int) -> Instance | None:
        """Ask a listening port to identify itself. Returns None if it is
        not a DCC-plugin socket (e.g. some unrelated service on the port)."""
        try:
            info = self._transport.get_info(port)
        except Exception:
            # Listening but not our protocol, or busy — record as opaque.
            if _port_listening(port):
                return Instance(port=port, kind=None, reachable=False)
            return None
        return Instance(
            port=port,
            kind=info.get("kind"),          # self-reported by the plugin
            version=str(info.get("version", "")),
            pid=info.get("pid"),
            file=str(info.get("file", "")),
            reachable=True,
            extra={k: v for k, v in info.items()
                   if k not in ("kind", "version", "pid", "file")},
        )
