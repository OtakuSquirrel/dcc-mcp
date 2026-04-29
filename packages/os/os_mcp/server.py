"""FastMCP server definition for os-mcp."""

import logging

from fastmcp import FastMCP

from dcc_mcp_core.middleware import ToolGuardMiddleware
from dcc_mcp_core.tool_registry import ToolRegistry

from os_mcp.tool_defs import CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# os-mcp has no DCCConfig — tool enable/disable state lives only in
# the unified ~/.dcc-mcp/config.toml under [tools.os].
tool_registry = ToolRegistry(None, CATEGORY_DEFS, DEFAULT_DISABLED_TOOLS, mcp_name="os")

mcp = FastMCP(
    "os",
    instructions=(
        "OS-level tools for inspecting DCC processes, diagnosing health, "
        "managing windows, taking screenshots, and working with the clipboard. "
        "Use alongside blender-mcp/houdini-mcp/ue-mcp when you need to diagnose "
        "a DCC issue or perform process-level operations like force-kill. "
        "All tools are stateless and return immediately — there is no "
        "long-running work here."
    ),
    middleware=[ToolGuardMiddleware(tool_registry)],
)

# Register tools via module import.
import os_mcp.tools.processes  # noqa: E402, F401
import os_mcp.tools.windows  # noqa: E402, F401
import os_mcp.tools.health  # noqa: E402, F401
import os_mcp.tools.screenshot  # noqa: E402, F401
import os_mcp.tools.clipboard  # noqa: E402, F401
