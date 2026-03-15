"""Blender MCP Addon — Non-blocking TCP socket server for MCP communication.

This addon runs a JSON-RPC socket server on bpy.app.timers so all bpy API
calls execute safely on Blender's main thread.

The MCP server (separate process) connects to this addon and sends commands.
"""

bl_info = {
    "name": "Blender MCP",
    "author": "dcc-mcp",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > MCP",
    "description": "MCP socket server for AI agent control",
    "category": "System",
}

import bpy
from bpy.props import IntProperty, BoolProperty

from . import socket_server


class BLENDERMCP_PT_Panel(bpy.types.Panel):
    """MCP control panel in the 3D Viewport sidebar."""
    bl_label = "MCP Server"
    bl_idname = "BLENDERMCP_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        if socket_server.is_running():
            layout.label(text=f"Running on port {socket_server.get_port()}", icon="LINKED")
            layout.operator("blendermcp.stop_server", text="Stop Server", icon="CANCEL")
        else:
            layout.prop(scene, "blender_mcp_port")
            layout.operator("blendermcp.start_server", text="Start Server", icon="PLAY")


class BLENDERMCP_OT_StartServer(bpy.types.Operator):
    """Start the MCP socket server."""
    bl_idname = "blendermcp.start_server"
    bl_label = "Start MCP Server"

    def execute(self, context):
        port = context.scene.blender_mcp_port
        socket_server.start(port)
        self.report({"INFO"}, f"MCP server started on port {port}")
        return {"FINISHED"}


class BLENDERMCP_OT_StopServer(bpy.types.Operator):
    """Stop the MCP socket server."""
    bl_idname = "blendermcp.stop_server"
    bl_label = "Stop MCP Server"

    def execute(self, context):
        socket_server.stop()
        self.report({"INFO"}, "MCP server stopped")
        return {"FINISHED"}


_classes = (
    BLENDERMCP_PT_Panel,
    BLENDERMCP_OT_StartServer,
    BLENDERMCP_OT_StopServer,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.blender_mcp_port = IntProperty(
        name="Port",
        description="TCP port for the MCP socket server",
        default=19811,
        min=1024,
        max=65535,
    )

    # Auto-start if BLENDER_MCP_ENABLED env var is set
    import os
    if os.environ.get("BLENDER_MCP_ENABLED") == "1":
        port = int(os.environ.get("BLENDER_MCP_PORT", "19811"))
        bpy.app.timers.register(lambda: _auto_start(port), first_interval=1.0)


def _auto_start(port: int) -> None:
    """Auto-start the server after Blender finishes loading."""
    socket_server.start(port)


def unregister():
    socket_server.stop()

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.blender_mcp_port
