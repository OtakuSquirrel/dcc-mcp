"""Object operation tools — create, delete, transform, inspect."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def create_object(
    type: str = "MESH",
    mesh_type: str = "cube",
    name: str | None = None,
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
) -> dict:
    """Create a new object in the scene.

    Args:
        type: Object type — MESH, EMPTY, CURVE, ARMATURE.
        mesh_type: For MESH type — cube, sphere, plane, cylinder, cone, torus, monkey.
        name: Optional name for the object.
        location: [x, y, z] location.
        rotation: [x, y, z] rotation in radians.
        scale: [x, y, z] scale.

    Returns:
        Dict with created object info.
    """
    params = {"type": type, "mesh_type": mesh_type}
    if name:
        params["name"] = name
    if location:
        params["location"] = location
    if rotation:
        params["rotation"] = rotation
    if scale:
        params["scale"] = scale
    return blender.send_command("create_object", params)


@mcp.tool()
def delete_object(name: str) -> dict:
    """Delete an object by name.

    Args:
        name: Name of the object to delete.

    Returns:
        Dict with deletion status.
    """
    return blender.send_command("delete_object", {"name": name})


@mcp.tool()
def select_objects(names: list[str] | None = None, pattern: str | None = None, deselect_all: bool = True) -> dict:
    """Select objects by name or pattern.

    Args:
        names: List of object names to select.
        pattern: Glob pattern to match object names (e.g. 'Cube*').
        deselect_all: Whether to deselect all first (default True).

    Returns:
        Dict with selected object names.
    """
    params = {"deselect_all": deselect_all}
    if names:
        params["names"] = names
    if pattern:
        params["pattern"] = pattern
    return blender.send_command("select_objects", params)


@mcp.tool()
def get_object_info(name: str) -> dict:
    """Get detailed info about an object.

    Args:
        name: Name of the object.

    Returns:
        Dict with object type, transforms, modifiers, materials, etc.
    """
    return blender.send_command("get_object_info", {"name": name})


@mcp.tool()
def transform_object(
    name: str,
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
) -> dict:
    """Set location, rotation, and/or scale of an object.

    Args:
        name: Name of the object.
        location: [x, y, z] world location.
        rotation: [x, y, z] rotation in radians.
        scale: [x, y, z] scale factors.

    Returns:
        Dict with updated transforms.
    """
    params = {"name": name}
    if location is not None:
        params["location"] = location
    if rotation is not None:
        params["rotation"] = rotation
    if scale is not None:
        params["scale"] = scale
    return blender.send_command("transform_object", params)


@mcp.tool()
def duplicate_object(name: str, new_name: str | None = None, linked: bool = False) -> dict:
    """Duplicate an object.

    Args:
        name: Name of the object to duplicate.
        new_name: Optional name for the duplicate.
        linked: If True, create a linked duplicate (shared mesh data).

    Returns:
        Dict with the duplicated object info.
    """
    params = {"name": name, "linked": linked}
    if new_name:
        params["new_name"] = new_name
    return blender.send_command("duplicate_object", params)


@mcp.tool()
def list_objects(type_filter: str | None = None) -> dict:
    """List all objects in the scene.

    Args:
        type_filter: Optional filter by type (MESH, LIGHT, CAMERA, etc.).

    Returns:
        Dict with list of object names and types.
    """
    params = {}
    if type_filter:
        params["type_filter"] = type_filter
    return blender.send_command("list_objects", params)
