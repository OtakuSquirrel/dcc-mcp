"""FastMCP server definition for HoudiniMCP — rewrite using dcc-mcp-core."""

import logging

from fastmcp import FastMCP

from dcc_mcp_core.config import DCCConfig
from dcc_mcp_core.registry import SessionRegistry
from dcc_mcp_core.tool_registry import ToolRegistry
from dcc_mcp_core.middleware import ClientNameMiddleware, ToolGuardMiddleware, TimeoutGuardMiddleware

from houdini_mcp.connection import HoudiniConnectionManager
from houdini_mcp.tool_defs import CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration ──
config = DCCConfig(
    app_name="houdini_mcp",
    default_port_range=(18811, 18899),
    dcc_search_paths=["C:/Program Files/Side Effects Software"],
)

# ── Session registry ──
registry = SessionRegistry(config.sessions_dir, config.get_port_range)

# ── Tool registry ──
tool_registry = ToolRegistry(config, CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS)

# ── Session tracking ──
_session_id: str | None = None

# ── Global connection manager ──
houdini = HoudiniConnectionManager(registry, config.get_port_range)

def _health_check_for_timeout(port: int) -> dict:
    """Health check called by TimeoutGuardMiddleware when a tool times out."""
    import rpyc
    from dcc_mcp_core.health import check_health

    def _rpyc_ping(host, p):
        try:
            conn = rpyc.classic.connect(host, p)
            conn.ping()
            conn.close()
            return True
        except Exception:
            return False

    return check_health(port, ping_fn=_rpyc_ping, sessions=registry.list_sessions())


# Tools that don't touch Houdini RPyC — skip timeout guard
# (they can't hang on a frozen Houdini, so wrapping them is pointless)
_NO_TIMEOUT_TOOLS = {
    "is_houdini_healthy", "scan_ports", "cleanup_stale_sessions",
    "start_houdini", "stop_houdini", "ensure_houdini_ready",
    "connect_to_houdini", "disconnect_houdini", "switch_active_houdini",
    "list_houdini_connections", "adopt_idle", "acquire_from_pool",
    "install_startup_scripts", "uninstall_startup_scripts",
    "get_houdini_status", "warm_pool", "get_pool_status",
    "get_current_session", "list_all_sessions",
    "get_mcp_config", "update_mcp_config",
    "compare_screenshots", "get_scene_diff",
}

# ── FastMCP server ──
mcp = FastMCP(
    "houdini",
    instructions="MCP Server for controlling Houdini via RPyC",
    middleware=[
        ClientNameMiddleware(on_client_name=lambda name: setattr(houdini, '_client_name', name)),
        ToolGuardMiddleware(tool_registry),
        TimeoutGuardMiddleware(
            timeout=10.0,
            get_port=lambda: houdini._active_port or houdini._explicit_port,
            health_check_fn=_health_check_for_timeout,
            skip_tools=_NO_TIMEOUT_TOOLS,
        ),
    ],
)


def set_port(port: int) -> None:
    """Override the RPyC port for the global connection."""
    houdini._explicit_port = port
    logger.info("RPyC target port set to %d", port)


def set_session_id(sid: str) -> None:
    """Set the session ID for this MCP server instance."""
    global _session_id
    _session_id = sid
    houdini._session_id = sid


def get_session_id() -> str | None:
    """Get the current session ID."""
    return _session_id or houdini._session_id


# Import tool modules to register their tools on `mcp`.
import houdini_mcp.tools.scene  # noqa: E402, F401
import houdini_mcp.tools.nodes  # noqa: E402, F401
import houdini_mcp.tools.parameters  # noqa: E402, F401
import houdini_mcp.tools.connections  # noqa: E402, F401
import houdini_mcp.tools.execution  # noqa: E402, F401
import houdini_mcp.tools.geometry  # noqa: E402, F401
import houdini_mcp.tools.viewport  # noqa: E402, F401
import houdini_mcp.tools.render  # noqa: E402, F401
import houdini_mcp.tools.verification  # noqa: E402, F401
import houdini_mcp.tools.lifecycle  # noqa: E402, F401
import houdini_mcp.tools.sessions  # noqa: E402, F401
