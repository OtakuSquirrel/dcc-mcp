"""FastMCP server definition for the Blender MCP Server.

Creates the MCP server instance, initializes the TCP connection manager,
and registers all tool modules.
"""

import logging

from fastmcp import FastMCP

from dcc_mcp_core.config import DCCConfig
from dcc_mcp_core.registry import SessionRegistry
from dcc_mcp_core.tool_registry import ToolRegistry
from dcc_mcp_core.middleware import ClientNameMiddleware, ToolGuardMiddleware

from blender_mcp.connection import BlenderConnectionManager
from blender_mcp.tool_defs import CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration ──
config = DCCConfig(
    app_name="blender_mcp",
    default_port_range=(19811, 19899),
    dcc_search_paths=[],  # Blender doesn't need search paths (addon-based)
)

# ── Session registry ──
registry = SessionRegistry(config.sessions_dir, config.get_port_range)

# ── Tool registry ──
tool_registry = ToolRegistry(config, CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS)

# ── Session tracking ──
_session_id: str | None = None

# ── Global connection manager ──
blender = BlenderConnectionManager(registry, config.get_port_range)

# ── FastMCP server with middleware ──
mcp = FastMCP(
    "blender",
    instructions="MCP Server for controlling Blender via TCP+JSON",
    middleware=[
        ClientNameMiddleware(on_client_name=lambda name: setattr(blender, '_client_name', name)),
        ToolGuardMiddleware(tool_registry),
    ],
)


def set_port(port: int) -> None:
    """Override the target port for the global connection."""
    blender._explicit_port = port
    logger.info("Blender target port set to %d", port)


def set_session_id(sid: str) -> None:
    """Set the session ID for this MCP server instance."""
    global _session_id
    _session_id = sid
    blender._session_id = sid


def get_session_id() -> str | None:
    """Get the current session ID."""
    return _session_id or blender._session_id


# Import tool modules to register their tools on `mcp`.
import blender_mcp.tools.scene  # noqa: E402, F401
import blender_mcp.tools.objects  # noqa: E402, F401
import blender_mcp.tools.materials  # noqa: E402, F401
import blender_mcp.tools.modifiers  # noqa: E402, F401
import blender_mcp.tools.animation  # noqa: E402, F401
import blender_mcp.tools.camera  # noqa: E402, F401
import blender_mcp.tools.lighting  # noqa: E402, F401
import blender_mcp.tools.rendering  # noqa: E402, F401
import blender_mcp.tools.viewport  # noqa: E402, F401
import blender_mcp.tools.import_export  # noqa: E402, F401
import blender_mcp.tools.execution  # noqa: E402, F401
import blender_mcp.tools.lifecycle  # noqa: E402, F401
import blender_mcp.tools.sessions  # noqa: E402, F401
