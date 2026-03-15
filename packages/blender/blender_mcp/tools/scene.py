"""Scene management tools — new, open, save, info."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def new_scene(name: str = "Scene") -> dict:
    """Create a new empty scene in Blender.

    Args:
        name: Name for the new scene.

    Returns:
        Dict with scene info.
    """
    return blender.send_command("new_scene", {"name": name})


@mcp.tool()
def open_file(filepath: str) -> dict:
    """Open a .blend file.

    Args:
        filepath: Path to the .blend file.

    Returns:
        Dict with opened scene info.
    """
    return blender.send_command("open_file", {"filepath": filepath})


@mcp.tool()
def save_file(filepath: str | None = None) -> dict:
    """Save current scene to .blend file.

    Args:
        filepath: Path to save to. If None, saves to current file.

    Returns:
        Dict with save status.
    """
    params = {}
    if filepath:
        params["filepath"] = filepath
    return blender.send_command("save_file", params)


@mcp.tool()
def get_scene_info() -> dict:
    """Get scene objects, collections, frame range, and render settings.

    Returns:
        Dict with scene overview.
    """
    return blender.send_command("get_scene_info")
