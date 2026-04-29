"""FastMCP server definition for UE MCP."""

import logging

from fastmcp import FastMCP

from dcc_mcp_core.config import DCCConfig
from dcc_mcp_core.registry import SessionRegistry
from dcc_mcp_core.tool_registry import ToolRegistry
from dcc_mcp_core.middleware import ClientNameMiddleware, ToolGuardMiddleware

from ue_mcp.connection import UEConnectionManager
from ue_mcp.tool_defs import CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration ──
config = DCCConfig(
    app_name="ue_mcp",
    default_port_range=(20811, 20899),
)

# ── Session registry ──
registry = SessionRegistry(config.sessions_dir, config.get_port_range)

# ── Tool registry ──
tool_registry = ToolRegistry(config, CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS, mcp_name="ue")

# ── Session tracking ──
_session_id: str | None = None

# ── Global connection manager ──
ue = UEConnectionManager(registry, config.get_port_range)

# ── FastMCP server ──
mcp = FastMCP(
    "ue",
    instructions="MCP Server for controlling Unreal Engine via Python Remote Execution",
    middleware=[
        ClientNameMiddleware(on_client_name=lambda name: setattr(ue, '_client_name', name)),
        ToolGuardMiddleware(tool_registry),
    ],
)


def set_port(port: int) -> None:
    ue._explicit_port = port
    logger.info("UE target port set to %d", port)


def set_session_id(sid: str) -> None:
    global _session_id
    _session_id = sid
    ue._session_id = sid


def get_session_id() -> str | None:
    return _session_id or ue._session_id


# Import tool modules
import ue_mcp.tools.level  # noqa: E402, F401
import ue_mcp.tools.actors  # noqa: E402, F401
import ue_mcp.tools.execution  # noqa: E402, F401
import ue_mcp.tools.lifecycle  # noqa: E402, F401
import ue_mcp.tools.sessions  # noqa: E402, F401
