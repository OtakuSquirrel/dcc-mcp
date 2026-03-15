"""Code execution tool for UE."""

from __future__ import annotations

from ue_mcp.server import mcp, ue


@mcp.tool()
def execute_ue_python(code: str) -> dict:
    """Execute Python code inside the Unreal Engine process.

    Has access to `unreal` module and all UE Python APIs.

    Args:
        code: Python code to execute. Use `result = ...` to return data.
    """
    return ue.execute_python(code)
