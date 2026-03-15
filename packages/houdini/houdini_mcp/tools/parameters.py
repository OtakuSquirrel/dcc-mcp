"""Parameter tools for Houdini — read, write, discover."""

from __future__ import annotations

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain, obtain_list, parm_template_to_dict


def _safe_expression(parm) -> str | None:
    """Get expression string from a parm, returning None if none set."""
    try:
        expr = parm.expression()
        return obtain(expr) if expr else None
    except Exception:
        return None


@mcp.tool()
def get_parameter(node_path: str, parm_name: str) -> dict:
    """Read a parameter value.

    Args:
        node_path: Full path of the node.
        parm_name: Parameter name.
    """
    hou = houdini.hou
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if parm is None:
        ptuple = node.parmTuple(parm_name)
        if ptuple is None:
            raise ValueError(f"Parameter not found: {parm_name}")
        return {
            "name": parm_name,
            "value": obtain_list(ptuple.eval()),
            "is_tuple": True,
        }
    return {
        "name": parm_name,
        "value": obtain(parm.eval()),
        "expression": _safe_expression(parm),
    }


@mcp.tool()
def set_parameter(node_path: str, parm_name: str, value) -> dict:
    """Set a parameter value.

    Args:
        node_path: Full path of the node.
        parm_name: Parameter name.
        value: Value to set (number, string, or list for tuples).
    """
    hou = houdini.hou
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Node not found: {node_path}")

    if isinstance(value, (list, tuple)):
        ptuple = node.parmTuple(parm_name)
        if ptuple is None:
            raise ValueError(f"Parameter tuple not found: {parm_name}")
        ptuple.set(value)
        return {"name": parm_name, "value": obtain_list(ptuple.eval())}
    else:
        # Try single parm first, then fall back to parmTuple
        parm = node.parm(parm_name)
        if parm is not None:
            parm.set(value)
            return {"name": parm_name, "value": obtain(parm.eval())}
        # Might be a tuple parm — set all components to the same scalar
        ptuple = node.parmTuple(parm_name)
        if ptuple is not None:
            ptuple.set([value] * obtain(len(ptuple)))
            return {"name": parm_name, "value": obtain_list(ptuple.eval())}
        raise ValueError(f"Parameter not found: {parm_name}")


@mcp.tool()
def get_parm_template(node_path: str) -> dict:
    """Get parameter schema (names, types, defaults) for a node.

    Args:
        node_path: Full path of the node.
    """
    hou = houdini.hou
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Node not found: {node_path}")

    templates = []
    for pt in node.parmTemplateGroup().entries():
        templates.append(parm_template_to_dict(pt))

    return {"node": node_path, "parameters": templates}
