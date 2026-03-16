"""Startup script: enable blender_mcp addon and start the socket server."""
import bpy
import addon_utils

# Enable the addon (this calls register() which sets up UI)
addon_utils.enable("blender_mcp", default_set=True, persistent=True)

# Start the MCP socket server
from blender_mcp import socket_server
socket_server.start(19811)
print(f"[MCP] Server started on port {socket_server.get_port()}, running={socket_server.is_running()}")
