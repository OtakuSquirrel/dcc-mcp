"""Houdini MCP startup script — auto-starts RPyC server when Houdini launches.

This script is loaded by 456.py (runs after scene load) when
HOUDINI_MCP_ENABLED=1 is set in the environment.

It starts the RPyC classic server on the port specified by HOUDINI_MCP_PORT
(default 18811).
"""

import os
import hou


def _start_mcp_rpyc():
    """Start the RPyC classic server for MCP communication."""
    enabled = os.environ.get("HOUDINI_MCP_ENABLED", "0")
    if enabled != "1":
        return

    port = int(os.environ.get("HOUDINI_MCP_PORT", "18811"))

    try:
        import hrpyc
        hrpyc.start_server(port=port)
        print(f"[HoudiniMCP] RPyC server started on port {port}")
    except Exception as e:
        print(f"[HoudiniMCP] Failed to start RPyC server: {e}")


_start_mcp_rpyc()
