"""Tool category definitions for blender-mcp.

Static metadata used by the Tauri manager to render the tool management
UI. Every operation tool takes `port: int` as its first argument —
see individual tool docstrings for full signatures.
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
        "desc": "Viewport screenshots and settings (Blender-side)",
        "tools": {
            "viewport_screenshot": "Take a viewport screenshot via Blender API",
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
        "desc": "Start/stop Blender instances (port-addressable)",
        "tools": {
            "start_blender": "Launch Blender and return allocated port",
            "stop_blender": "Gracefully stop Blender (for force-kill, use os-mcp.kill_process)",
            "ensure_blender_ready": "Find or start a Blender instance",
            "warm_pool": "Launch N Blender instances",
            "install_addon": "Return addon install instructions",
        },
    },
    "Tasks": {
        "desc": "Manage long-running tool calls (heartbeat pattern)",
        "tools": {
            "wait_task": "Continue waiting for a task that returned status=running",
            "list_tasks": "List all in-flight tasks on this MCP server",
        },
    },
}

DEFAULT_DISABLED_TOOLS: list[str] = []
