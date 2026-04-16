"""FastMCP server definition for the Blender MCP Server.

Stateless — every operation tool takes an explicit `port` argument.
No session registry writes, no active-port concept. See
`blender_mcp/_heartbeat.py` for the heartbeat task registry that wraps
every tool call.
"""

import logging

from fastmcp import FastMCP

from dcc_mcp_core.config import DCCConfig
from dcc_mcp_core.middleware import ToolGuardMiddleware
from dcc_mcp_core.tool_registry import ToolRegistry

from blender_mcp._heartbeat import HeartbeatMiddleware, register_task_tools
from blender_mcp.connection import BlenderConnectionManager
from blender_mcp.tool_defs import CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration (still via dcc-mcp-core until Phase 4 deletes core) ──
config = DCCConfig(
    app_name="blender_mcp",
    default_port_range=(19811, 19910),
    dcc_search_paths=[],
)

tool_registry = ToolRegistry(config, CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS)

# ── Stateless connection manager ──
# Lazy, port-keyed, per-port locked. Shared across all tool invocations
# in this MCP server process.
blender = BlenderConnectionManager()

# ── FastMCP server with middleware chain ──
mcp = FastMCP(
    "blender",
    instructions=(
        "MCP Server for controlling Blender via TCP+JSON. Every tool that "
        "interacts with a Blender instance takes an explicit `port` argument "
        "identifying which instance. Use `start_blender` to spawn a new "
        "instance (returns the allocated port). Use "
        "`os-mcp.list_dcc_instances()` to discover instances started outside "
        "this session. Long tool calls yield via the heartbeat pattern — if "
        "a call takes longer than 15s, you'll receive `status=running` with a "
        "task_id; call `wait_task(task_id)` to keep waiting."
    ),
    middleware=[
        ToolGuardMiddleware(tool_registry),
        HeartbeatMiddleware(),
    ],
)

# Register infrastructure tools (wait_task, list_tasks) on this mcp instance.
register_task_tools(mcp)

# Register operation tool modules (each file decorates its own @mcp.tool()s).
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
# tools.sessions DELETED in Phase 1b
