"""Geometry inspection tools for Houdini."""

from __future__ import annotations

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain, obtain_list


@mcp.tool()
def get_geometry_info(path: str) -> dict:
    """Get point/prim counts and attribute list.

    Args:
        path: Path to a SOP node.
    """
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")
    geo = node.geometry()
    if geo is None:
        raise ValueError(f"No geometry on node: {path}")

    point_attribs = [obtain(a.name()) for a in geo.pointAttribs()]
    prim_attribs = [obtain(a.name()) for a in geo.primAttribs()]
    vertex_attribs = [obtain(a.name()) for a in geo.vertexAttribs()]
    detail_attribs = [obtain(a.name()) for a in geo.globalAttribs()]

    return {
        "path": path,
        "num_points": obtain(len(geo.points())),
        "num_prims": obtain(len(geo.prims())),
        "num_vertices": sum(obtain(p.numVertices()) for p in geo.prims()),
        "point_attribs": point_attribs,
        "prim_attribs": prim_attribs,
        "vertex_attribs": vertex_attribs,
        "detail_attribs": detail_attribs,
    }


@mcp.tool()
def get_point_positions(path: str, limit: int = 100) -> dict:
    """Get point positions from geometry.

    Args:
        path: Path to a SOP node.
        limit: Max points to return (default 100).
    """
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")
    geo = node.geometry()
    if geo is None:
        raise ValueError(f"No geometry on node: {path}")

    points = geo.points()
    total = obtain(len(points))
    positions = []
    for i, pt in enumerate(points):
        if i >= limit:
            break
        pos = obtain_list(pt.position())
        positions.append(pos)

    return {"path": path, "total_points": total, "returned": len(positions), "positions": positions}


@mcp.tool()
def get_attribute_values(path: str, attrib_name: str, attrib_type: str = "point", limit: int = 100) -> dict:
    """Get attribute values from geometry.

    Args:
        path: Path to a SOP node.
        attrib_name: Attribute name (e.g. 'P', 'N', 'Cd').
        attrib_type: 'point', 'prim', 'vertex', or 'detail'.
        limit: Max elements to return.
    """
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")
    geo = node.geometry()
    if geo is None:
        raise ValueError(f"No geometry on node: {path}")

    if attrib_type == "point":
        attrib = geo.findPointAttrib(attrib_name)
        elements = geo.points()
    elif attrib_type == "prim":
        attrib = geo.findPrimAttrib(attrib_name)
        elements = geo.prims()
    elif attrib_type == "vertex":
        attrib = geo.findVertexAttrib(attrib_name)
        # Collect vertices from all prims (no top-level iterVertices in Houdini 21+)
        elements = [v for p in geo.prims() for v in p.vertices()]
    elif attrib_type == "detail":
        attrib = geo.findGlobalAttrib(attrib_name)
        val = obtain(geo.attribValue(attrib_name))
        return {"path": path, "attrib": attrib_name, "type": "detail", "value": val}
    else:
        raise ValueError(f"Unknown attrib_type: {attrib_type}")

    if attrib is None:
        raise ValueError(f"Attribute '{attrib_name}' not found on {attrib_type}")

    values = []
    for i, elem in enumerate(elements):
        if i >= limit:
            break
        val = obtain(elem.attribValue(attrib_name))
        values.append(val)

    return {
        "path": path,
        "attrib": attrib_name,
        "type": attrib_type,
        "total": obtain(len(elements)),
        "returned": len(values),
        "values": values,
    }
