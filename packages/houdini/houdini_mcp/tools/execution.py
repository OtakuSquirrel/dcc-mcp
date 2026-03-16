"""Code execution and node cooking tools for Houdini."""

from __future__ import annotations

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain, obtain_list


@mcp.tool()
def execute_python(code: str) -> dict:
    """Execute Python code inside the Houdini process.

    Args:
        code: Python code to execute. Has access to `hou` module.
              Assign to `_result` to return a value.
    """
    conn = houdini.conn
    # Build a real remote dict with hou pre-injected so user code can
    # reference `hou` directly (matches Houdini's native shell behaviour).
    ns = conn.modules.builtins.dict()
    ns["hou"] = conn.modules.hou
    remote_exec = conn.modules.builtins.eval(
        "lambda code, ns: (exec(compile(code, '<mcp>', 'exec'), ns), ns.get('_result'))",
    )
    _, remote_result = remote_exec(code, ns)
    result = obtain(remote_result) if remote_result is not None else None
    return {"result": result, "executed": True}


@mcp.tool()
def cook_node(path: str) -> dict:
    """Force cook a node and return status.

    Args:
        path: Full path of the node to cook.
    """
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")
    node.cook(force=True)
    errors = obtain(node.errors())
    warnings = obtain(node.warnings())
    return {
        "path": path,
        "cooked": True,
        "errors": errors if errors else [],
        "warnings": warnings if warnings else [],
    }


@mcp.tool()
def get_node_errors(path: str) -> dict:
    """Get errors and warnings from a node.

    Args:
        path: Full path of the node.
    """
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")
    return {
        "path": path,
        "errors": obtain(node.errors()),
        "warnings": obtain(node.warnings()),
    }
