"""Tool category definitions for UE MCP."""

from __future__ import annotations

CATEGORY_DEFS: dict[str, dict] = {
    "Level": {
        "desc": "Create, open, save levels and get level info",
        "tools": {
            "new_level": "Create a new empty level",
            "open_level": "Open a level by path",
            "save_level": "Save the current level",
            "get_level_info": "Get level actors, lighting, and settings",
        },
    },
    "Actors": {
        "desc": "Spawn, delete, transform, and inspect actors",
        "tools": {
            "spawn_actor": "Spawn an actor from a class or asset",
            "delete_actor": "Delete an actor by name/path",
            "transform_actor": "Set location/rotation/scale",
            "get_actor_info": "Get detailed info about an actor",
            "list_actors": "List all actors in the level",
        },
    },
    "Materials": {
        "desc": "Create and configure material instances",
        "tools": {
            "create_material_instance": "Create a material instance",
            "assign_material": "Assign a material to an actor's mesh",
            "set_material_parameter": "Set a material parameter value",
        },
    },
    "Lighting": {
        "desc": "Create and configure lights and atmosphere",
        "tools": {
            "create_light": "Create a light actor",
            "configure_light": "Set light properties",
            "set_sky_atmosphere": "Configure sky atmosphere",
        },
    },
    "Camera": {
        "desc": "Create and configure cameras",
        "tools": {
            "create_camera": "Create a camera actor",
            "set_active_camera": "Set the viewport camera",
        },
    },
    "Rendering": {
        "desc": "Render settings and output",
        "tools": {
            "set_render_settings": "Configure render quality settings",
            "render_frame": "Render the current viewport to file",
        },
    },
    "Import/Export": {
        "desc": "Import and export assets",
        "tools": {
            "import_asset": "Import an asset (FBX, USD, etc.)",
            "export_asset": "Export an asset to file",
        },
    },
    "Blueprints": {
        "desc": "Create and inspect blueprints",
        "tools": {
            "create_blueprint": "Create a new blueprint class",
            "add_component": "Add a component to a blueprint",
            "get_blueprint_info": "Get blueprint class info",
        },
    },
    "Build": {
        "desc": "Build lighting, package project, play in editor",
        "tools": {
            "build_lighting": "Build lighting for the level",
            "build_all": "Build all (geometry, lighting, paths)",
            "play_in_editor": "Start Play-In-Editor session",
        },
    },
    "Execution": {
        "desc": "Execute Python code in UE",
        "tools": {
            "execute_ue_python": "Execute Python code inside UE",
        },
    },
    "Lifecycle": {
        "desc": "Start/stop UE, health checks",
        "tools": {
            "ensure_ue_ready": "Ensure UE is running and connected",
            "is_ue_healthy": "Check if UE is responsive",
        },
    },
    "Sessions": {
        "desc": "Manage MCP sessions and connections",
        "tools": {
            "list_all_sessions": "List all registered MCP sessions",
            "get_current_session": "Get this session's info",
            "connect_to_ue": "Connect to a UE instance on a port",
            "disconnect_ue": "Disconnect from current UE instance",
        },
    },
}

DEFAULT_DISABLED_TOOLS: list[str] = []
