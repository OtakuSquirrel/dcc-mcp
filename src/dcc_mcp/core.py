"""The daemon core — owns the RegistrationHub used by MCP-over-HTTP.

One process, one hub. DCCs register with the hub (dial in and hold a
connection); the core routes agent requests to them by ``instance_id``.
Discovery/health logic lives here, in one place.
"""

from __future__ import annotations

import logging

from dcc_mcp import health
from dcc_mcp.hub import HubError, RegistrationHub
from dcc_mcp.window_capture import capture_process_window

logger = logging.getLogger(__name__)

# Public DCC-side execution error exposed by the core API.
DCCError = HubError


class DaemonCore:
    def __init__(self, hub: RegistrationHub | None = None, window_capturer=None):
        self.hub = hub or RegistrationHub()
        self._window_capturer = window_capturer or capture_process_window

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

    def screenshot(self, instance_id: str) -> bytes:
        """Capture the registered process's real Windows application window."""
        registration = self.hub.get(instance_id)
        if registration is None:
            raise KeyError(f"unknown or disconnected instance: {instance_id}")
        return self._window_capturer(registration.pid)

    def get_info(self, instance_id: str) -> dict:
        result = self.hub.request(instance_id, "get_info")
        return result if isinstance(result, dict) else {}
