"""The daemon core — owns the RegistrationHub and exposes it to whatever
ingress (MCP-over-HTTP, WebSocket tunnel) is attached.

One process, one hub. DCCs register with the hub (dial in and hold a
connection); the core routes agent requests to them by ``instance_id``.
Discovery/health logic lives here, in one place.
"""

from __future__ import annotations

import logging

from dcc_daemon import health
from dcc_daemon.hub import HubError, RegistrationHub

logger = logging.getLogger(__name__)

# Re-export so ingress layers (tunnel client) can catch DCC-side errors
# without importing the hub directly.
DCCError = HubError


class DaemonCore:
    def __init__(self, hub: RegistrationHub | None = None):
        self.hub = hub or RegistrationHub()

    # ── the things any agent can ask for ──

    def list_instances(self, refresh: bool = False) -> list[dict]:
        # refresh kept for signature compatibility; the registry is always
        # live, so there is nothing to re-scan.
        return self.hub.list()

    def execute_python(self, instance_id: str, code: str) -> dict:
        """Run ``code`` in the DCC ``instance_id``. The plugin sets
        ``result`` to return a value; JSON-serializable comes back verbatim."""
        result = self.hub.request(instance_id, "execute_python", {"code": code})
        return {"instance_id": instance_id, "result": result}

    def health(self, instance_id: str) -> dict:
        return health.check_health(instance_id, self.hub)

    def screenshot(self, instance_id: str) -> str:
        """Return a base64 PNG of the DCC's viewport/render."""
        result = self.hub.request(instance_id, "screenshot")
        if isinstance(result, dict):
            return str(result.get("png_base64") or result.get("data") or "")
        return str(result)

    def get_info(self, instance_id: str) -> dict:
        result = self.hub.request(instance_id, "get_info")
        return result if isinstance(result, dict) else {}
