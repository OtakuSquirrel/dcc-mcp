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


def build_app(
    mcp_path: str = "/mcp",
    *,
    webui: bool = True,
    registration_bind: tuple[str, int] | None = None,
):
    """Return the ASGI app serving MCP at ``mcp_path`` and, if ``webui``,
    the dashboard at ``/``. Also starts the DCC registration hub listener
    so DCCs can dial in."""
    from dcc_mcp import config
    from dcc_mcp.mcp_server import core, mcp

    if webui:
        from dcc_mcp.webui.log_buffer import install_log_capture

        install_log_capture()

    # Start listening for DCC registrations (idempotent).
    reg_host, reg_port = registration_bind or config.register_bind()
    core.hub.start(reg_host, reg_port)

    if webui:
        try:
            from dcc_mcp.webui.dashboard import register_webui

            register_webui()
        except ImportError:
            logger.warning("starlette not available — serving MCP only (no WebUI)")

    app = mcp.http_app(path=mcp_path)
    app.state.mcp_path = mcp_path
    return app
