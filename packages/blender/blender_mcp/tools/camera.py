"""Camera tools — create, configure, set active."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def create_camera(
    port: int,
    name: str = "Camera",
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    focal_length: float = 50.0,
) -> dict:
    """Create a new camera.

    Args:
        port: Port of the target Blender instance.
        name: Camera name.
        location: [x, y, z] world location.
        rotation: [x, y, z] rotation in radians.
        focal_length: Focal length in mm (default 50).

    Returns:
        Dict with camera info.
    """
    params: dict = {"name": name, "focal_length": focal_length}
    if location:
        params["location"] = location
    if rotation:
        params["rotation"] = rotation
    return blender.send_command(port, "create_camera", params)


@mcp.tool()
def set_active_camera(port: int, name: str) -> dict:
    """Set the active camera for rendering.

    Args:
        port: Port of the target Blender instance.
        name: Name of the camera object.

    Returns:
        Dict with active camera info.
    """
    return blender.send_command(port, "set_active_camera", {"name": name})


@mcp.tool()
def configure_camera(
    port: int,
    name: str,
    focal_length: float | None = None,
    sensor_width: float | None = None,
    clip_start: float | None = None,
    clip_end: float | None = None,
    dof_focus_distance: float | None = None,
    dof_fstop: float | None = None,
) -> dict:
    """Configure camera properties.

    Args:
        port: Port of the target Blender instance.
        name: Name of the camera object.
        focal_length: Focal length in mm.
        sensor_width: Sensor width in mm.
        clip_start: Near clipping distance.
        clip_end: Far clipping distance.
        dof_focus_distance: Depth of field focus distance.
        dof_fstop: Depth of field f-stop.

    Returns:
        Dict with updated camera settings.
    """
    params: dict = {"name": name}
    if focal_length is not None:
        params["focal_length"] = focal_length
    if sensor_width is not None:
        params["sensor_width"] = sensor_width
    if clip_start is not None:
        params["clip_start"] = clip_start
    if clip_end is not None:
        params["clip_end"] = clip_end
    if dof_focus_distance is not None:
        params["dof_focus_distance"] = dof_focus_distance
    if dof_fstop is not None:
        params["dof_fstop"] = dof_fstop
    return blender.send_command(port, "configure_camera", params)
