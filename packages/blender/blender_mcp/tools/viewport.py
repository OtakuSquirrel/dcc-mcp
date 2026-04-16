"""Viewport tools — screenshots and display settings."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def viewport_screenshot(port: int, output_path: str) -> dict:
    """Take a viewport screenshot from inside Blender.

    This uses Blender's own screenshot operator, which captures the 3D
    viewport (not the OS window). For OS-level screenshots, use
    os-mcp.take_screenshot() or os-mcp.take_window_screenshot(pid).

    Args:
        port: Port of the target Blender instance.
        output_path: File path to save the screenshot.

    Returns:
        Dict with screenshot path and dimensions.
    """
    return blender.send_command(port, "viewport_screenshot", {
        "output_path": output_path,
    })


@mcp.tool()
def set_viewport_shading(port: int, mode: str = "MATERIAL") -> dict:
    """Set viewport shading mode.

    Args:
        port: Port of the target Blender instance.
        mode: Shading mode — WIREFRAME, SOLID, MATERIAL, RENDERED.

    Returns:
        Dict with current shading mode.
    """
    return blender.send_command(port, "set_viewport_shading", {"mode": mode})


@mcp.tool()
def set_viewport_camera(port: int, camera_name: str | None = None) -> dict:
    """Set viewport to camera view.

    Args:
        port: Port of the target Blender instance.
        camera_name: Camera to use. If None, uses the active camera.

    Returns:
        Dict with viewport state.
    """
    params: dict = {}
    if camera_name:
        params["camera_name"] = camera_name
    return blender.send_command(port, "set_viewport_camera", params)
