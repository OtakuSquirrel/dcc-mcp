"""Animation tools — keyframes and timeline."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def insert_keyframe(
    port: int,
    object_name: str,
    data_path: str,
    frame: int | None = None,
    value: float | None = None,
) -> dict:
    """Insert a keyframe on a property.

    Args:
        port: Port of the target Blender instance.
        object_name: Name of the object.
        data_path: Property path (e.g. 'location', 'rotation_euler[2]').
        frame: Frame number. If None, uses current frame.
        value: Optional value to set before keying.

    Returns:
        Dict with keyframe info.
    """
    params: dict = {"object_name": object_name, "data_path": data_path}
    if frame is not None:
        params["frame"] = frame
    if value is not None:
        params["value"] = value
    return blender.send_command(port, "insert_keyframe", params)


@mcp.tool()
def remove_keyframe(
    port: int,
    object_name: str,
    data_path: str,
    frame: int | None = None,
) -> dict:
    """Remove a keyframe.

    Args:
        port: Port of the target Blender instance.
        object_name: Name of the object.
        data_path: Property path.
        frame: Frame number. If None, removes at current frame.

    Returns:
        Dict with removal status.
    """
    params: dict = {"object_name": object_name, "data_path": data_path}
    if frame is not None:
        params["frame"] = frame
    return blender.send_command(port, "remove_keyframe", params)


@mcp.tool()
def set_frame(port: int, frame: int) -> dict:
    """Set the current frame.

    Args:
        port: Port of the target Blender instance.
        frame: Frame number to set.

    Returns:
        Dict with current frame info.
    """
    return blender.send_command(port, "set_frame", {"frame": frame})


@mcp.tool()
def get_timeline_info(port: int) -> dict:
    """Get frame range and current frame.

    Args:
        port: Port of the target Blender instance.

    Returns:
        Dict with start_frame, end_frame, current_frame, fps.
    """
    return blender.send_command(port, "get_timeline_info")
