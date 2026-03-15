"""Node connection tools for Houdini — wire and unwire."""

from __future__ import annotations

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain


@mcp.tool()
def connect_nodes(
    from_node: str,
    to_node: str,
    from_output: int = 0,
    to_input: int = 0,
) -> dict:
    """Wire output of one node to input of another.

    Args:
        from_node: Path of the source node.
        to_node: Path of the destination node.
        from_output: Output index on the source node (default 0).
        to_input: Input index on the destination node (default 0).
    """
    hou = houdini.hou
    src = hou.node(from_node)
    dst = hou.node(to_node)
    if src is None:
        raise ValueError(f"Source node not found: {from_node}")
    if dst is None:
        raise ValueError(f"Destination node not found: {to_node}")
    dst.setInput(to_input, src, from_output)
    return {"from": from_node, "to": to_node, "output": from_output, "input": to_input}


@mcp.tool()
def disconnect_nodes(node_path: str, input_index: int) -> dict:
    """Disconnect an input on a node.

    Args:
        node_path: Path of the node.
        input_index: Input index to disconnect.
    """
    hou = houdini.hou
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Node not found: {node_path}")
    node.setInput(input_index, None)
    return {"node": node_path, "disconnected_input": input_index}


@mcp.tool()
def get_connections(node_path: str) -> dict:
    """Get all input/output connections for a node.

    Args:
        node_path: Path of the node.
    """
    hou = houdini.hou
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Node not found: {node_path}")

    inputs = []
    for i, inp in enumerate(node.inputs()):
        if inp is not None:
            inputs.append({"index": i, "node": obtain(inp.path())})

    outputs = []
    for out in node.outputs():
        outputs.append(obtain(out.path()))

    return {"node": node_path, "inputs": inputs, "outputs": outputs}
