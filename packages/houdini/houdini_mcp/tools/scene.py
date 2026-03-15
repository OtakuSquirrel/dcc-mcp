"""Scene management tools for Houdini."""

from __future__ import annotations

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain


@mcp.tool()
def new_scene() -> dict:
    """Create a new empty scene (clear all nodes)."""
    hou = houdini.hou
    hou.hipFile.clear(suppress_save_prompt=True)
    return {"status": "new_scene_created", "file": obtain(hou.hipFile.name())}


@mcp.tool()
def save_hip(filepath: str | None = None) -> dict:
    """Save current scene to .hip file.

    Args:
        filepath: Path to save. If None, saves to current file.
    """
    hou = houdini.hou
    if filepath:
        hou.hipFile.save(file_name=filepath)
    else:
        hou.hipFile.save()
    return {"filepath": obtain(hou.hipFile.path())}


@mcp.tool()
def open_hip(filepath: str) -> dict:
    """Open a .hip file.

    Args:
        filepath: Path to the .hip file.
    """
    hou = houdini.hou
    hou.hipFile.load(filepath, suppress_save_prompt=True)
    return {"filepath": obtain(hou.hipFile.path()), "name": obtain(hou.hipFile.name())}


@mcp.tool()
def get_scene_summary() -> dict:
    """Get scene file, frame range, node counts."""
    hou = houdini.hou
    root = hou.node("/")
    total_nodes = 0
    for child in root.allSubChildren():
        total_nodes += 1

    return {
        "file": obtain(hou.hipFile.path()),
        "name": obtain(hou.hipFile.name()),
        "frame_range": [obtain(hou.playbar.frameRange()[0]), obtain(hou.playbar.frameRange()[1])],
        "current_frame": obtain(hou.frame()),
        "fps": obtain(hou.fps()),
        "total_nodes": total_nodes,
    }
