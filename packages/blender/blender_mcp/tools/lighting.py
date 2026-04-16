"""Lighting tools — create, configure lights and HDRI."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def create_light(
    port: int,
    type: str = "POINT",
    name: str | None = None,
    location: list[float] | None = None,
    energy: float = 1000.0,
    color: list[float] | None = None,
) -> dict:
    """Create a light in the scene.

    Args:
        port: Port of the target Blender instance.
        type: Light type — POINT, SUN, SPOT, AREA.
        name: Optional light name.
        location: [x, y, z] world location.
        energy: Light power in watts (default 1000).
        color: [R, G, B] light color (0.0-1.0).

    Returns:
        Dict with light info.
    """
    params: dict = {"type": type, "energy": energy}
    if name:
        params["name"] = name
    if location:
        params["location"] = location
    if color:
        params["color"] = color
    return blender.send_command(port, "create_light", params)


@mcp.tool()
def configure_light(
    port: int,
    name: str,
    energy: float | None = None,
    color: list[float] | None = None,
    shadow_soft_size: float | None = None,
    spot_size: float | None = None,
    spot_blend: float | None = None,
) -> dict:
    """Configure light properties.

    Args:
        port: Port of the target Blender instance.
        name: Name of the light object.
        energy: Light power in watts.
        color: [R, G, B] light color.
        shadow_soft_size: Shadow softness radius.
        spot_size: Spot cone angle in radians (spot lights only).
        spot_blend: Spot edge falloff (spot lights only).

    Returns:
        Dict with updated light settings.
    """
    params: dict = {"name": name}
    if energy is not None:
        params["energy"] = energy
    if color is not None:
        params["color"] = color
    if shadow_soft_size is not None:
        params["shadow_soft_size"] = shadow_soft_size
    if spot_size is not None:
        params["spot_size"] = spot_size
    if spot_blend is not None:
        params["spot_blend"] = spot_blend
    return blender.send_command(port, "configure_light", params)


@mcp.tool()
def set_hdri(
    port: int, filepath: str, strength: float = 1.0, rotation: float = 0.0
) -> dict:
    """Set an HDRI environment map for world lighting.

    Args:
        port: Port of the target Blender instance.
        filepath: Path to the HDRI image file (.hdr, .exr).
        strength: Environment light strength (default 1.0).
        rotation: Z-axis rotation in radians (default 0.0).

    Returns:
        Dict with HDRI setup status.
    """
    return blender.send_command(port, "set_hdri", {
        "filepath": filepath,
        "strength": strength,
        "rotation": rotation,
    })
