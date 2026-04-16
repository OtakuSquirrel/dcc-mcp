"""Scene management tools — new, open, save, info."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def new_scene(port: int, name: str = "Scene") -> dict:
    """Create a new empty scene in Blender.

    Args:
        port: Port of the target Blender instance (from start_blender or
              os-mcp.list_dcc_instances).
        name: Name for the new scene.

    Returns:
        Dict with scene info.
    """
    return blender.send_command(port, "new_scene", {"name": name})


@mcp.tool()
def open_file(port: int, filepath: str) -> dict:
    """Open a .blend file.

    Args:
        port: Port of the target Blender instance.
        filepath: Path to the .blend file.

    Returns:
        Dict with opened scene info.
    """
    return blender.send_command(port, "open_file", {"filepath": filepath})


@mcp.tool()
def save_file(port: int, filepath: str | None = None) -> dict:
    """Save current scene to .blend file.

    Args:
        port: Port of the target Blender instance.
        filepath: Path to save to. If None, saves to current file.

    Returns:
        Dict with save status.
    """
    params: dict = {}
    if filepath:
        params["filepath"] = filepath
    return blender.send_command(port, "save_file", params)


@mcp.tool()
def get_scene_info(port: int) -> dict:
    """Get scene objects, collections, frame range, and render settings.

    Args:
        port: Port of the target Blender instance.

    Returns:
        Dict with scene overview.
    """
    return blender.send_command(port, "get_scene_info")
