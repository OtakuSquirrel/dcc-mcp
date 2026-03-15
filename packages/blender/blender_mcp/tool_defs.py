"""Tool category definitions for BlenderMCP.

Static metadata — descriptions, categories, default enable/disable state.
"""

from __future__ import annotations

CATEGORY_DEFS: dict[str, dict] = {
    "Scene": {
        "desc": "Create, open, save scenes and get scene info",
        "tools": {
            "new_scene": "Create a new empty scene",
            "open_file": "Open a .blend file",
            "save_file": "Save current scene to .blend file",
            "get_scene_info": "Get scene objects, collections, frame range",
        },
    },
    "Objects": {
        "desc": "Create, delete, transform, and inspect objects",
        "tools": {
            "create_object": "Create a mesh/empty/curve object",
            "delete_object": "Delete an object by name",
            "select_objects": "Select objects by name/pattern",
            "get_object_info": "Get detailed info about an object",
            "transform_object": "Set location/rotation/scale",
            "duplicate_object": "Duplicate an object",
            "list_objects": "List all objects in the scene",
        },
    },
    "Materials": {
        "desc": "Create and configure materials and shader nodes",
        "tools": {
            "create_material": "Create a new material",
            "assign_material": "Assign a material to an object",
            "add_shader_node": "Add a node to a material's node tree",
            "connect_shader_nodes": "Connect two shader nodes",
            "get_material_info": "Get material node tree info",
        },
    },
    "Modifiers": {
        "desc": "Add, remove, and apply modifiers",
        "tools": {
            "add_modifier": "Add a modifier to an object",
            "remove_modifier": "Remove a modifier from an object",
            "apply_modifier": "Apply a modifier",
            "get_modifiers": "List modifiers on an object",
        },
    },
    "Animation": {
        "desc": "Keyframes and timeline control",
        "tools": {
            "insert_keyframe": "Insert a keyframe on a property",
            "remove_keyframe": "Remove a keyframe",
            "set_frame": "Set the current frame",
            "get_timeline_info": "Get frame range and current frame",
        },
    },
    "Camera": {
        "desc": "Create and configure cameras",
        "tools": {
            "create_camera": "Create a new camera",
            "set_active_camera": "Set the active camera",
            "configure_camera": "Set camera properties (focal length, DOF, etc.)",
        },
    },
    "Lighting": {
        "desc": "Create and configure lights and HDRI",
        "tools": {
            "create_light": "Create a light (point, sun, spot, area)",
            "configure_light": "Set light properties",
            "set_hdri": "Set an HDRI environment map",
        },
    },
    "Rendering": {
        "desc": "Render settings and output",
        "tools": {
            "set_render_engine": "Set render engine (Cycles, Eevee)",
            "set_resolution": "Set render resolution",
            "render_frame": "Render the current frame to file",
            "render_preview": "Quick viewport render preview",
        },
    },
    "Viewport": {
        "desc": "Viewport screenshots and settings",
        "tools": {
            "viewport_screenshot": "Take a viewport screenshot",
            "set_viewport_shading": "Set viewport shading mode",
            "set_viewport_camera": "Set viewport to camera view",
        },
    },
    "Import/Export": {
        "desc": "Import and export files (FBX, OBJ, USD, glTF)",
        "tools": {
            "import_file": "Import a file (auto-detect format)",
            "export_file": "Export to file (FBX, OBJ, USD, glTF)",
        },
    },
    "Execution": {
        "desc": "Execute Python code directly in Blender",
        "tools": {
            "execute_blender_code": "Execute arbitrary Python code in Blender",
        },
    },
    "Lifecycle": {
        "desc": "Start/stop Blender, health checks, addon management",
        "tools": {
            "start_blender": "Launch Blender with MCP addon",
            "stop_blender": "Stop Blender process",
            "ensure_blender_ready": "Start Blender if not running (idempotent)",
            "is_blender_healthy": "Check if Blender is responsive",
            "warm_pool": "Batch-launch idle Blender instances",
            "install_addon": "Install/enable the MCP addon in Blender",
        },
    },
    "Sessions": {
        "desc": "Manage MCP sessions, ports, multi-instance connections",
        "tools": {
            "list_all_sessions": "List all registered MCP sessions",
            "disconnect_blender": "Disconnect from current Blender instance",
            "get_current_session": "Get this MCP server's session info",
            "cleanup_stale_sessions": "Remove sessions with dead processes",
            "scan_ports": "Scan port range for Blender/MCP status",
            "get_pool_status": "Show idle/active Blender instance counts",
            "acquire_from_pool": "Grab an idle instance and connect to it",
            "connect_to_blender": "Connect to a Blender instance on a port",
            "switch_active_blender": "Switch which Blender receives commands",
        },
    },
}

DEFAULT_DISABLED_TOOLS: list[str] = []
