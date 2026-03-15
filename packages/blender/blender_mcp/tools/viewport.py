"""Viewport tools — screenshots and display settings."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def viewport_screenshot(output_path: str) -> dict:
    """Take a viewport screenshot.

    Args:
        output_path: File path to save the screenshot.

    Returns:
        Dict with screenshot path and dimensions.
    """
    return blender.send_command("viewport_screenshot", {"output_path": output_path})


@mcp.tool()
def set_viewport_shading(mode: str = "MATERIAL") -> dict:
    """Set viewport shading mode.

    Args:
        mode: Shading mode — WIREFRAME, SOLID, MATERIAL, RENDERED.

    Returns:
        Dict with current shading mode.
    """
    return blender.send_command("set_viewport_shading", {"mode": mode})


@mcp.tool()
def set_viewport_camera(camera_name: str | None = None) -> dict:
    """Set viewport to camera view.

    Args:
        camera_name: Camera to use. If None, uses the active camera.

    Returns:
        Dict with viewport state.
    """
    params = {}
    if camera_name:
        params["camera_name"] = camera_name
    return blender.send_command("set_viewport_camera", params)
