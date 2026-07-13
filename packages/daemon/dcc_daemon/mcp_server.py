"""MCP-over-HTTP ingress — the meta-tools local agents see.

This is deliberately tiny. There is no per-DCC tool, no tool-search
layer. DCC domain knowledge (how to build a mesh, wire a node graph,
set up a render) lives in Skills that the agent loads on demand — NOT
in tool schemas, which would sit in the system prompt every turn.

Tools:
  * list_instances()                 — what DCCs are registered
  * execute_python(instance_id, code)— the one channel that does everything
  * screenshot(instance_id)          — capture its Windows application window
  * health(instance_id)              — liveness + responsiveness, never hangs

Claude Code connects with  {"type": "http", "url": ".../mcp"}  — no
child process, the daemon is already running. DCCs are addressed by the
daemon-assigned ``instance_id`` (e.g. "blender-1"), not a port.
"""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from dcc_daemon.core import DaemonCore

logger = logging.getLogger(__name__)

core = DaemonCore()

mcp = FastMCP(
    "dcc",
    instructions=(
        "Unified control of local DCC applications (Blender, Houdini, "
        "Unreal Engine, Maya) through a single daemon. Workflow: call "
        "`list_instances` to see what is running and each instance's "
        "`instance_id`, then `execute_python(instance_id, code)` to do "
        "ANYTHING — it runs Python inside that DCC (bpy / hou / unreal / "
        "cmds are in scope) and returns whatever you assign to `result`. "
        "There are no per-operation tools; load the relevant DCC skill "
        "for code recipes. Use `screenshot(instance_id)` to see its "
        "Windows application window and `health(instance_id)` if an instance seems "
        "stuck."
    ),
)


@mcp.tool()
def list_instances(refresh: bool = False) -> list[dict]:
    """List DCC instances currently registered with the daemon.

    Returns one entry per instance with its `instance_id` (e.g.
    "blender-1"), `kind` (blender/houdini/ue/maya), `version`, `pid`,
    open `file`, and whether it is `connected`. Pass the `instance_id`
    to every other tool.

    Args:
        refresh: Ignored — the registry is always live. Kept for
            signature stability.
    """
    return core.list_instances(refresh=refresh)


@mcp.tool()
def execute_python(instance_id: str, code: str) -> dict:
    """Execute Python inside the DCC instance `instance_id`.

    This is the universal channel — every operation (modeling,
    materials, nodes, rendering, import/export, inspection) is done by
    sending code here. The code runs on the DCC's main thread with full
    access to its Python API (`bpy` for Blender, `hou` for Houdini,
    `unreal` for Unreal, `cmds` for Maya). Assign to `result` to return
    a value:

        result = [o.name for o in bpy.data.objects]

    Anything JSON-serializable in `result` is returned verbatim.

    Args:
        instance_id: Target instance (from `list_instances`).
        code: Python source to run inside the DCC.
    """
    return core.execute_python(instance_id, code)


@mcp.tool()
def health(instance_id: str) -> dict:
    """Health verdict for a DCC instance — never hangs.

    Combines the live connection state with a main-thread heartbeat (and
    OS window/CPU signals) into a verdict: healthy | busy | hung | dead |
    unknown. Use this when an `execute_python` call times out or an
    instance seems frozen.

    Args:
        instance_id: Target instance (from `list_instances`).
    """
    return core.health(instance_id)


@mcp.tool()
def screenshot(instance_id: str) -> Image:
    """Capture the real Windows application window for `instance_id`.

    The daemon locates the top-level window by the registered process ID
    and captures Windows desktop pixels. It does not call the DCC's
    viewport capture, playblast, flipbook, screenshot, or render APIs.

    Args:
        instance_id: Target instance (from `list_instances`).
    """
    return Image(data=core.screenshot(instance_id), format="png")
