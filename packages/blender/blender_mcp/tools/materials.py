"""Material and shader node tools."""

from __future__ import annotations

from blender_mcp.server import mcp, blender


@mcp.tool()
def create_material(name: str, color: list[float] | None = None) -> dict:
    """Create a new material.

    Args:
        name: Material name.
        color: Optional base color as [R, G, B, A] (0.0-1.0).

    Returns:
        Dict with material info.
    """
    params = {"name": name}
    if color:
        params["color"] = color
    return blender.send_command("create_material", params)


@mcp.tool()
def assign_material(object_name: str, material_name: str, slot: int = 0) -> dict:
    """Assign a material to an object.

    Args:
        object_name: Name of the object.
        material_name: Name of the material.
        slot: Material slot index (default 0).

    Returns:
        Dict with assignment status.
    """
    return blender.send_command("assign_material", {
        "object_name": object_name,
        "material_name": material_name,
        "slot": slot,
    })


@mcp.tool()
def add_shader_node(material_name: str, node_type: str, location: list[float] | None = None) -> dict:
    """Add a node to a material's shader node tree.

    Args:
        material_name: Name of the material.
        node_type: Blender node type (e.g. 'ShaderNodeTexImage', 'ShaderNodeMixShader').
        location: [x, y] position in the node editor.

    Returns:
        Dict with the created node's name and info.
    """
    params = {"material_name": material_name, "node_type": node_type}
    if location:
        params["location"] = location
    return blender.send_command("add_shader_node", params)


@mcp.tool()
def connect_shader_nodes(
    material_name: str,
    from_node: str,
    from_output: int | str,
    to_node: str,
    to_input: int | str,
) -> dict:
    """Connect two shader nodes.

    Args:
        material_name: Name of the material.
        from_node: Name of the output node.
        from_output: Output socket index or name.
        to_node: Name of the input node.
        to_input: Input socket index or name.

    Returns:
        Dict with connection status.
    """
    return blender.send_command("connect_shader_nodes", {
        "material_name": material_name,
        "from_node": from_node,
        "from_output": from_output,
        "to_node": to_node,
        "to_input": to_input,
    })


@mcp.tool()
def get_material_info(material_name: str) -> dict:
    """Get material node tree info.

    Args:
        material_name: Name of the material.

    Returns:
        Dict with nodes, links, and settings.
    """
    return blender.send_command("get_material_info", {"material_name": material_name})
