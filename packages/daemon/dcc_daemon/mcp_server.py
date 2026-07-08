"""MCP-over-HTTP ingress — the ~5 meta-tools local agents see.

This is deliberately tiny. There is no per-DCC tool, no tool-search
layer. DCC domain knowledge (how to build a mesh, wire a node graph,
set up a render) lives in Skills that the agent loads on demand — NOT
in tool schemas, which would sit in the system prompt every turn.

Tools:
  * list_instances()          — what DCCs are running, on which ports
  * execute_python(port, code)— the one channel that does everything
  * screenshot(port)          — render/grab an image the model can see
  * health(port)              — OS-level verdict, never hangs

Claude Code connects with  {"type": "http", "url": ".../mcp"}  — no
child process, the daemon is already running.
"""

from __future__ import annotations

import base64
import binascii
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
        "Unreal Engine) through a single daemon. Workflow: call "
        "`list_instances` to see what is running and on which port, then "
        "`execute_python(port, code)` to do ANYTHING — it runs Python "
        "inside that DCC (bpy / hou / unreal are in scope) and returns "
        "whatever you assign to `result`. There are no per-operation "
        "tools; load the relevant DCC skill for code recipes. Use "
        "`screenshot(port)` to see the viewport/render and `health(port)` "
        "if an instance seems stuck."
    ),
)


@mcp.tool()
def list_instances(refresh: bool = False) -> list[dict]:
    """List running DCC instances discovered on the local machine.

    Returns one entry per instance with its `port`, `kind`
    (blender/houdini/ue), `version`, `pid`, open `file`, and whether it
    is `reachable`. Pass the `port` to every other tool.

    Args:
        refresh: Force a fresh port scan instead of the short cache.
    """
    return core.list_instances(refresh=refresh)


@mcp.tool()
def execute_python(port: int, code: str) -> dict:
    """Execute Python inside the DCC instance on `port`.

    This is the universal channel — every operation (modeling,
    materials, nodes, rendering, import/export, inspection) is done by
    sending code here. The code runs on the DCC's main thread with full
    access to its Python API (`bpy` for Blender, `hou` for Houdini,
    `unreal` for Unreal). Assign to `result` to return a value:

        result = [o.name for o in bpy.data.objects]

    Anything JSON-serializable in `result` is returned verbatim.

    Args:
        port: Target instance port (from `list_instances`).
        code: Python source to run inside the DCC.
    """
    return core.execute_python(port, code)


@mcp.tool()
def health(port: int) -> dict:
    """OS-level health verdict for the DCC on `port` — never hangs.

    Combines process/window/CPU/protocol signals into a verdict:
    healthy | busy | hung | no_protocol | dead | unknown. Use this when
    an `execute_python` call times out or an instance seems frozen.

    Args:
        port: Target instance port.
    """
    return core.health(port)


@mcp.tool()
def screenshot(port: int) -> Image:
    """Capture an image from the DCC on `port` so you can see the result.

    Asks the DCC to grab its viewport (or last render) to a PNG and
    returns the image bytes directly, so the model sees the picture.
    The grab mechanism is DCC-specific and implemented by the plugin's
    `screenshot` command.

    Args:
        port: Target instance port.
    """
    b64 = core.screenshot(port)
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise RuntimeError(f"screenshot did not return valid base64 PNG: {e}") from e
    return Image(data=raw, format="png")
