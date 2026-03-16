"""Viewport tools — screenshot, camera settings.

NOTE: Viewport operations require Houdini to be running in GUI mode.
For headless rendering, use render tools instead.
"""

from __future__ import annotations

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain


def _get_scene_viewer_and_viewport(hou):
    """Get SceneViewer pane tab and its current GeometryViewport.

    Returns:
        (scene_viewer, viewport) tuple.
    """
    desktop = hou.ui.curDesktop()
    scene_viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
    if scene_viewer is None:
        raise ValueError("No SceneViewer pane found. Houdini must be in GUI mode.")
    viewport = scene_viewer.curViewport()
    return scene_viewer, viewport


@mcp.tool()
def viewport_screenshot(
    output_path: str,
    width: int = 1920,
    height: int = 1080,
) -> dict:
    """Take a screenshot of the current Houdini viewport.

    Requires Houdini running in GUI mode with a visible viewport.
    For headless rendering, use render_frame or render_preview instead.

    Args:
        output_path: File path to save the screenshot (e.g. 'D:/screenshots/viewport.png').
        width: Image width in pixels (default 1920).
        height: Image height in pixels (default 1080).

    Returns:
        Dict with output path and dimensions.
    """
    hou = houdini.hou

    try:
        scene_viewer, viewport = _get_scene_viewer_and_viewport(hou)
    except Exception as e:
        raise ValueError(
            f"Cannot access viewport. Houdini must be running in GUI mode. Error: {e}"
        )

    # Use flipbook to capture the viewport
    try:
        flipbook_settings = scene_viewer.flipbookSettings().stash()
        cur_frame = int(obtain(hou.frame()))
        flipbook_settings.frameRange((cur_frame, cur_frame))
        flipbook_settings.output(output_path)
        flipbook_settings.resolution((width, height))
        # flipbook() needs the GeometryViewport, not the SceneViewer
        scene_viewer.flipbook(viewport, flipbook_settings)
    except Exception as e:
        raise ValueError(f"Failed to capture viewport screenshot: {e}")

    return {
        "output_path": output_path,
        "width": width,
        "height": height,
    }


@mcp.tool()
def set_viewport(
    camera: str | None = None,
    display_mode: str | None = None,
) -> dict:
    """Configure viewport settings.

    Requires Houdini running in GUI mode.

    Args:
        camera: Path to a camera node to look through (e.g. '/obj/cam1'), or None.
        display_mode: One of 'wireframe', 'smooth', 'smooth_wire', 'hidden_line',
                      'flat', 'flat_wire', 'matcap', or None.

    Returns:
        Dict confirming the applied settings.
    """
    hou = houdini.hou

    try:
        scene_viewer, viewport = _get_scene_viewer_and_viewport(hou)
    except Exception as e:
        raise ValueError(f"Cannot access viewport: {e}")

    result = {}

    if camera is not None:
        cam_node = hou.node(camera)
        if cam_node is None:
            raise ValueError(f"Camera node not found: {camera}")
        viewport.setCamera(cam_node)
        result["camera"] = camera

    if display_mode is not None:
        # Build mode map dynamically to handle API changes across Houdini versions.
        gl = hou.glShadingType
        mode_map = {}

        # wireframe — consistent across versions
        if hasattr(gl, "Wire"):
            mode_map["wireframe"] = gl.Wire

        # smooth — try Smooth (H21+) then SmoothShaded (H20-)
        if hasattr(gl, "Smooth"):
            mode_map["smooth"] = gl.Smooth
        elif hasattr(gl, "SmoothShaded"):
            mode_map["smooth"] = gl.SmoothShaded

        # smooth_wire
        if hasattr(gl, "SmoothWire"):
            mode_map["smooth_wire"] = gl.SmoothWire

        # hidden_line — try both variants
        for name in ("HiddenLineInvisible", "HiddenLine"):
            if hasattr(gl, name):
                mode_map["hidden_line"] = getattr(gl, name)
                break

        # flat, matcap (H21+ extras)
        if hasattr(gl, "Flat"):
            mode_map["flat"] = gl.Flat
        if hasattr(gl, "FlatWire"):
            mode_map["flat_wire"] = gl.FlatWire
        if hasattr(gl, "MatCap"):
            mode_map["matcap"] = gl.MatCap

        gl_mode = mode_map.get(display_mode)
        if gl_mode is None:
            available = [attr for attr in dir(gl) if not attr.startswith("_")]
            raise ValueError(
                f"Unknown display_mode: {display_mode}. "
                f"Available modes: {', '.join(mode_map.keys())}. "
                f"Raw glShadingType attrs: {available}"
            )

        # H21+: use displaySet.setShadedMode() on the SceneObject display set
        # H20-: use viewport.changeShadingMode()
        settings = viewport.settings()
        if hasattr(settings, "displaySet"):
            ds = settings.displaySet(hou.displaySetType.SceneObject)
            ds.setShadedMode(gl_mode)
        elif hasattr(viewport, "changeShadingMode"):
            viewport.changeShadingMode(gl_mode)
        else:
            raise ValueError("Cannot set shading mode: no compatible API found.")

        result["display_mode"] = display_mode

    if not result:
        result["message"] = "No settings changed (no arguments provided)."

    return result
