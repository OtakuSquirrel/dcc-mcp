"""Modifier tools — add, remove, apply, list."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def add_modifier(
    port: int,
    object_name: str,
    modifier_type: str,
    name: str | None = None,
    settings: dict | None = None,
) -> dict:
    """Add a modifier to an object.

    Args:
        port: Port of the target Blender instance.
        object_name: Name of the object.
        modifier_type: Blender modifier type (e.g. 'SUBSURF', 'MIRROR').
        name: Optional modifier name.
        settings: Optional dict of modifier settings.

    Returns:
        Dict with modifier info.
    """
    params: dict = {"object_name": object_name, "modifier_type": modifier_type}
    if name:
        params["name"] = name
    if settings:
        params["settings"] = settings
    return blender.send_command(port, "add_modifier", params)


@mcp.tool()
def remove_modifier(port: int, object_name: str, modifier_name: str) -> dict:
    """Remove a modifier from an object.

    Args:
        port: Port of the target Blender instance.
        object_name: Name of the object.
        modifier_name: Name of the modifier to remove.

    Returns:
        Dict with removal status.
    """
    return blender.send_command(port, "remove_modifier", {
        "object_name": object_name,
        "modifier_name": modifier_name,
    })


@mcp.tool()
def apply_modifier(port: int, object_name: str, modifier_name: str) -> dict:
    """Apply a modifier (bake it into the mesh).

    Args:
        port: Port of the target Blender instance.
        object_name: Name of the object.
        modifier_name: Name of the modifier to apply.

    Returns:
        Dict with apply status.
    """
    return blender.send_command(port, "apply_modifier", {
        "object_name": object_name,
        "modifier_name": modifier_name,
    })


@mcp.tool()
def get_modifiers(port: int, object_name: str) -> dict:
    """List all modifiers on an object.

    Args:
        port: Port of the target Blender instance.
        object_name: Name of the object.

    Returns:
        Dict with list of modifiers and their settings.
    """
    return blender.send_command(port, "get_modifiers", {
        "object_name": object_name,
    })
