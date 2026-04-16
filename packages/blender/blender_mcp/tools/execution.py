"""Code execution tool — escape hatch for arbitrary bpy operations."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def execute_blender_code(port: int, code: str) -> dict:
    """Execute arbitrary Python code inside the Blender process.

    The code runs in Blender's main thread via bpy.app.timers. Has
    access to `bpy`, `mathutils`, and all Blender modules.

    Use this for operations not covered by dedicated tools.

    Args:
        port: Port of the target Blender instance.
        code: Python code to execute. Use `result = ...` to return data.

    Returns:
        Dict with execution result or output.
    """
    return blender.send_command(port, "execute_code", {"code": code})
