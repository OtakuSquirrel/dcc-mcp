"""Node operation tools for Houdini."""

from __future__ import annotations

from typing import Any

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain, obtain_list, node_to_dict


@mcp.tool()
def create_node(parent_path: str, node_type: str, name: str | None = None) -> dict:
    """Create a new node inside a parent network.

    Args:
        parent_path: Path to the parent node (e.g. '/obj', '/obj/geo1').
        node_type: Houdini node type name (e.g. 'geo', 'sphere', 'null').
        name: Optional name for the new node.
    """
    hou = houdini.hou
    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError(f"Parent node not found: {parent_path}")
    node = parent.createNode(node_type, node_name=name)
    node.moveToGoodPosition()
    return node_to_dict(node)


@mcp.tool()
def delete_node(path: str) -> str:
    """Delete a node by its path."""
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")
    node.destroy()
    return f"Deleted node: {path}"


@mcp.tool()
def get_node_info(path: str) -> dict:
    """Get detailed information about a node."""
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")

    info = node_to_dict(node)

    inputs = []
    for i, inp in enumerate(node.inputs()):
        if inp is not None:
            inputs.append({"index": i, "connected_to": obtain(inp.path())})
    info["inputs"] = inputs

    outputs = []
    for conn in node.outputs():
        outputs.append(obtain(conn.path()))
    info["outputs"] = outputs
    info["num_parameters"] = obtain(len(node.parms()))

    try:
        info["is_display_flag"] = obtain(node.isDisplayFlagSet())
    except Exception:
        pass
    try:
        info["is_render_flag"] = obtain(node.isRenderFlagSet())
    except Exception:
        pass

    errors = obtain(node.errors())
    warnings = obtain(node.warnings())
    if errors:
        info["errors"] = errors
    if warnings:
        info["warnings"] = warnings

    return info


@mcp.tool()
def get_node_tree(path: str = "/", depth: int = 2) -> dict:
    """Get a hierarchical tree of nodes starting from a path."""
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")
    return _build_tree(node, depth)


def _build_tree(node: Any, depth: int) -> dict:
    result = {
        "path": obtain(node.path()),
        "type": obtain(node.type().name()),
        "name": obtain(node.name()),
    }
    if depth > 0:
        children = [_build_tree(child, depth - 1) for child in node.children()]
        if children:
            result["children"] = children
    return result


@mcp.tool()
def get_node_children(path: str) -> list[dict]:
    """Get the direct children of a node."""
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")
    return [node_to_dict(child) for child in node.children()]
