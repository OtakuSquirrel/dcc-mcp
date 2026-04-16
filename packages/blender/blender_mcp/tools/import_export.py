"""Import/Export tools — FBX, OBJ, USD, glTF."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def import_file(port: int, filepath: str, format: str | None = None) -> dict:
    """Import a file into the scene.

    Auto-detects format from extension if not specified.

    Args:
        port: Port of the target Blender instance.
        filepath: Path to the file to import.
        format: Force format — fbx, obj, usd, gltf, abc. Auto-detect if None.

    Returns:
        Dict with imported objects info.
    """
    params: dict = {"filepath": filepath}
    if format:
        params["format"] = format
    return blender.send_command(port, "import_file", params)


@mcp.tool()
def export_file(
    port: int,
    filepath: str,
    format: str | None = None,
    selected_only: bool = False,
) -> dict:
    """Export to file (FBX, OBJ, USD, glTF).

    Auto-detects format from extension if not specified.

    Args:
        port: Port of the target Blender instance.
        filepath: Output file path.
        format: Force format — fbx, obj, usd, usdc, gltf, glb.
                Auto-detect if None.
        selected_only: If True, export only selected objects.

    Returns:
        Dict with export status and path.
    """
    params: dict = {"filepath": filepath, "selected_only": selected_only}
    if format:
        params["format"] = format
    return blender.send_command(port, "export_file", params)
