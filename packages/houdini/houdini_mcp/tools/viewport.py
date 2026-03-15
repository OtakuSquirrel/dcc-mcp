"""Viewport tools for Houdini — screenshots and display."""

from __future__ import annotations

import base64

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain


@mcp.tool()
def viewport_screenshot(output_path: str, width: int = 1920, height: int = 1080) -> dict:
    """Screenshot the current viewport.

    Args:
        output_path: File path to save the screenshot.
        width: Image width.
        height: Image height.
    """
    hou = houdini.hou
    desktop = hou.ui.curDesktop()
    viewport = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
    if viewport is None:
        raise RuntimeError("No SceneViewer pane found")

    flipbook_settings = viewport.flipbookSettings()
    flipbook_settings.frameRange((hou.frame(), hou.frame()))
    flipbook_settings.output(output_path)
    flipbook_settings.resolution((width, height))
    viewport.flipbook(settings=flipbook_settings)

    return {"output_path": output_path, "width": width, "height": height}


@mcp.tool()
def set_viewport(
    camera: str | None = None,
    display_mode: str | None = None,
) -> dict:
    """Configure viewport camera and display mode.

    Args:
        camera: Camera node path to look through.
        display_mode: Display mode (e.g. 'smooth', 'wire', 'smooth_wire').
    """
    hou = houdini.hou
    desktop = hou.ui.curDesktop()
    viewport = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
    if viewport is None:
        raise RuntimeError("No SceneViewer pane found")

    result = {}

    if camera:
        cam_node = hou.node(camera)
        if cam_node is None:
            raise ValueError(f"Camera not found: {camera}")
        viewport.curViewport().setCamera(cam_node)
        result["camera"] = camera

    if display_mode:
        mode_map = {
            "smooth": hou.glShadingType.SmoothShaded,
            "wire": hou.glShadingType.Wire,
            "smooth_wire": hou.glShadingType.SmoothWire,
            "flat": hou.glShadingType.FlatShaded,
            "flat_wire": hou.glShadingType.FlatWire,
            "hidden_line": hou.glShadingType.HiddenLine,
        }
        mode = mode_map.get(display_mode)
        if mode is None:
            raise ValueError(f"Unknown display mode: {display_mode}. Options: {list(mode_map.keys())}")
        viewport.curViewport().settings().displaySet(hou.displaySetType.DisplayModel).setShadedMode(mode)
        result["display_mode"] = display_mode

    return result
