"""Rendering tools — engine, resolution, render output."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def set_render_engine(engine: str = "CYCLES", device: str = "GPU") -> dict:
    """Set the render engine.

    Args:
        engine: Render engine — CYCLES, BLENDER_EEVEE_NEXT, BLENDER_WORKBENCH.
        device: Compute device for Cycles — GPU or CPU.

    Returns:
        Dict with engine settings.
    """
    return blender.send_command("set_render_engine", {"engine": engine, "device": device})


@mcp.tool()
def set_resolution(width: int = 1920, height: int = 1080, percentage: int = 100) -> dict:
    """Set render resolution.

    Args:
        width: Resolution width in pixels.
        height: Resolution height in pixels.
        percentage: Resolution percentage scale (default 100).

    Returns:
        Dict with resolution settings.
    """
    return blender.send_command("set_resolution", {
        "width": width,
        "height": height,
        "percentage": percentage,
    })


@mcp.tool()
def render_frame(output_path: str, frame: int | None = None, samples: int | None = None) -> dict:
    """Render the current or specified frame to file.

    Args:
        output_path: File path for the rendered image.
        frame: Frame number to render. If None, renders current frame.
        samples: Override sample count. If None, uses scene settings.

    Returns:
        Dict with render result and output path.
    """
    params = {"output_path": output_path}
    if frame is not None:
        params["frame"] = frame
    if samples is not None:
        params["samples"] = samples
    return blender.send_command("render_frame", params)


@mcp.tool()
def render_preview(output_path: str, quality: str = "medium") -> dict:
    """Quick viewport/OpenGL render preview.

    Args:
        output_path: File path for the preview image.
        quality: Preview quality — low, medium, high.

    Returns:
        Dict with preview render result.
    """
    return blender.send_command("render_preview", {
        "output_path": output_path,
        "quality": quality,
    })
