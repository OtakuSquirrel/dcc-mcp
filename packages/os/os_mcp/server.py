"""FastMCP server definition for os-mcp."""

import logging

from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
)

# Register tools via module import.
import os_mcp.tools.processes  # noqa: E402, F401
import os_mcp.tools.windows  # noqa: E402, F401
import os_mcp.tools.health  # noqa: E402, F401
import os_mcp.tools.screenshot  # noqa: E402, F401
import os_mcp.tools.clipboard  # noqa: E402, F401
