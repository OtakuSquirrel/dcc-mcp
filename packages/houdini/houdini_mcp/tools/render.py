"""Render tools for Houdini — ROP rendering and preview."""

from __future__ import annotations

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain


@mcp.tool()
def render_frame(rop_path: str, frame: int | None = None, output_path: str | None = None) -> dict:
    """Render a frame using a ROP node.

    Args:
        rop_path: Path to the ROP node (e.g. '/out/mantra1').
        frame: Frame to render. If None, uses current frame.
        output_path: Override output path. If None, uses ROP settings.
    """
    hou = houdini.hou
    rop = hou.node(rop_path)
    if rop is None:
        raise ValueError(f"ROP node not found: {rop_path}")

    if output_path:
        try:
            rop.parm("vm_picture").set(output_path)
        except Exception:
            rop.parm("sopoutput").set(output_path)

    if frame is not None:
        rop.render(frame_range=(frame, frame))
    else:
        rop.render()

    return {"rop": rop_path, "frame": frame or obtain(hou.frame()), "status": "rendered"}


@mcp.tool()
def render_preview(output_path: str, width: int = 960, height: int = 540) -> dict:
    """Quick OpenGL preview render.

    Args:
        output_path: File path for the preview image.
        width: Image width.
        height: Image height.
    """
    hou = houdini.hou
    desktop = hou.ui.curDesktop()
    viewport = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
    if viewport is None:
        raise RuntimeError("No SceneViewer pane found")

    settings = viewport.flipbookSettings()
    settings.frameRange((hou.frame(), hou.frame()))
    settings.output(output_path)
    settings.resolution((width, height))
    viewport.flipbook(settings=settings)

    return {"output_path": output_path, "width": width, "height": height}
