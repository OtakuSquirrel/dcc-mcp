"""Animation tools — keyframes and timeline."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def insert_keyframe(object_name: str, data_path: str, frame: int | None = None, value: float | None = None) -> dict:
    """Insert a keyframe on a property.

    Args:
        object_name: Name of the object.
        data_path: Property path (e.g. 'location', 'rotation_euler[2]', 'scale[0]').
        frame: Frame number. If None, uses current frame.
        value: Optional value to set before keying.

    Returns:
        Dict with keyframe info.
    """
    params = {"object_name": object_name, "data_path": data_path}
    if frame is not None:
        params["frame"] = frame
    if value is not None:
        params["value"] = value
    return blender.send_command("insert_keyframe", params)


@mcp.tool()
def remove_keyframe(object_name: str, data_path: str, frame: int | None = None) -> dict:
    """Remove a keyframe.

    Args:
        object_name: Name of the object.
        data_path: Property path.
        frame: Frame number. If None, removes at current frame.

    Returns:
        Dict with removal status.
    """
    params = {"object_name": object_name, "data_path": data_path}
    if frame is not None:
        params["frame"] = frame
    return blender.send_command("remove_keyframe", params)


@mcp.tool()
def set_frame(frame: int) -> dict:
    """Set the current frame.

    Args:
        frame: Frame number to set.

    Returns:
        Dict with current frame info.
    """
    return blender.send_command("set_frame", {"frame": frame})


@mcp.tool()
def get_timeline_info() -> dict:
    """Get frame range and current frame.

    Returns:
        Dict with start_frame, end_frame, current_frame, fps.
    """
    return blender.send_command("get_timeline_info")
