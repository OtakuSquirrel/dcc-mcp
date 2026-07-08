"""The daemon core — owns the single TransportPool, InstanceRegistry,
and exposes them to whatever ingress (MCP-over-HTTP now, WebSocket
tunnel later) is attached.

One process, one pool, one registry. Ingress layers are thin and share
this core so routing/discovery/health logic exists in exactly one place.
"""

from __future__ import annotations

import logging

from dcc_daemon import health
from dcc_daemon.registry import InstanceRegistry
from dcc_daemon.transport import TransportPool

logger = logging.getLogger(__name__)


class DaemonCore:
    def __init__(self):
        self.transport = TransportPool()
        self.registry = InstanceRegistry(self.transport)

    # ── the five things any agent can ask for ──

    def list_instances(self, refresh: bool = False) -> list[dict]:
        return [i.to_dict() for i in self.registry.list_instances(refresh=refresh)]

    def execute_python(self, port: int, code: str) -> dict:
        """Run ``code`` in the DCC on ``port``. The plugin sets ``result``
        to return a value; anything JSON-serializable comes back verbatim."""
        result = self.transport.execute_python(port, code)
        return {"port": port, "result": result}

    def health(self, port: int) -> dict:
        return health.check_health(port, ping_fn=lambda: self.transport.ping(port))

    def screenshot(self, port: int) -> str:
        """Return a base64 PNG of the DCC's viewport/render."""
        return self.transport.screenshot(port)

    def get_info(self, port: int) -> dict:
        return self.transport.get_info(port)
