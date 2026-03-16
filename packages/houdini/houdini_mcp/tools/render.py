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


def _find_camera(hou) -> str | None:
    """Find a camera: prefer viewport's current camera, fallback to first in scene."""
    try:
        desktop = hou.ui.curDesktop()
        sv = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if sv is not None:
            vp = sv.curViewport()
            cam = vp.camera()
            if cam is not None:
                return obtain(cam.path())
    except Exception:
        pass

    # Fallback: find first camera node in /obj
    obj = hou.node("/obj")
    if obj is not None:
        for child in obj.children():
            if obtain(child.type().name()) in ("cam", "stereocam"):
                return obtain(child.path())

    return None


@mcp.tool()
def render_preview(output_path: str, rop_path: str | None = None) -> dict:
    """Quick OpenGL preview render of the current viewport/scene.

    If rop_path is provided, uses that ROP. Otherwise, creates a temporary
    OpenGL ROP for a quick preview. Automatically uses the viewport's current
    camera, or falls back to the first camera in the scene.

    Uses an OpenGL ROP node for rendering. The ROP is reused across calls
    (NOT destroyed — destroying it crashes Houdini).

    Args:
        output_path: File path for the output image (e.g. 'D:/renders/preview.png').
        rop_path: Optional path to an existing OpenGL ROP node.

    Returns:
        Dict with output path and status.
    """
    hou = houdini.hou
    conn = houdini.conn
    camera_path = None

    if rop_path is not None:
        rop = hou.node(rop_path)
        if rop is None:
            raise ValueError(f"ROP node not found: {rop_path}")
    else:
        # Create or reuse the OpenGL ROP
        rop = hou.node("/out/mcp_opengl")
        if rop is None:
            rop = hou.node("/out").createNode("opengl", "mcp_opengl")

        # Auto-set camera
        camera_path = _find_camera(hou)
        if camera_path:
            cam_parm = rop.parm("camera")
            if cam_parm is not None:
                cam_parm.set(camera_path)

    # Set output path
    picture_parm = rop.parm("picture")
    if picture_parm is not None:
        picture_parm.set(output_path)

    try:
        current_frame = int(obtain(hou.frame()))
        rop_path_str = obtain(rop.path())

        # Render via remote exec with conn.modules.hou namespace.
        # Using conn.modules.hou provides the correct remote module reference
        # with proper GL context, while "import hou" inside bare exec
        # can trigger "OpenGL Fatal Error" on first use.
        ns = conn.modules.builtins.dict()
        ns["hou"] = conn.modules.hou
        conn.modules.builtins.exec(
            f"hou.node('{rop_path_str}').parm('execute').pressButton()",
            ns,
        )
    finally:
        # Do NOT destroy the OpenGL ROP — destroying it triggers
        # "OpenGL Fatal Error" because GL context cleanup crashes.
        # Leave it in /out; it's harmless and reusable.
        pass

    return {
        "output_path": output_path,
        "frame": current_frame,
        "status": "rendered",
        "camera": camera_path,
    }
