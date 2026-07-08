"""Build the daemon's HTTP app: MCP endpoint + optional WebUI.

The WebUI routes are attached directly to the FastMCP server via
``@mcp.custom_route``, so everything is ONE Starlette app with ONE
lifespan on ONE port:

    /mcp   -> MCP-over-HTTP (agents)
    /      -> monitoring dashboard (humans), when webui is enabled
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_app(mcp_path: str = "/mcp", *, webui: bool = True):
    """Return the ASGI app serving MCP at ``mcp_path`` and, if ``webui``,
    the dashboard at ``/``. Also starts the DCC registration hub listener
    so DCCs can dial in."""
    from dcc_daemon import config
    from dcc_daemon.mcp_server import core, mcp

    # Start listening for DCC registrations (idempotent).
    reg_host, reg_port = config.register_bind()
    core.hub.start(reg_host, reg_port)

    if webui:
        try:
            from dcc_daemon.webui.dashboard import register_webui

            register_webui()
        except ImportError:
            logger.warning("starlette not available — serving MCP only (no WebUI)")

    return mcp.http_app(path=mcp_path)
