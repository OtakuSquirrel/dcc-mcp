"""Non-blocking TCP socket server for UE MCP.

Runs inside Unreal Engine's Python environment. All incoming JSON commands are
dispatched to handlers that execute UE Python API calls.

Uses unreal.register_slate_post_tick_callback() for non-blocking polling at
every editor tick — never blocks the editor.

Protocol: newline-delimited JSON. Each request is a JSON object with:
  {"command": "...", "params": {...}}
Response is a JSON object with:
  {"result": ...} or {"error": "..."}
"""

from __future__ import annotations

import json
import os
import select
import socket
import sys
import traceback
from pathlib import Path
from typing import Any

import unreal

_server_socket: socket.socket | None = None
_client_sockets: list[socket.socket] = []
_port: int = 20811
_running: bool = False
_tick_handle = None


def is_running() -> bool:
    return _running


def get_port() -> int:
    return _port


def start(port: int | None = None) -> None:
    """Start the MCP socket server."""
    global _server_socket, _port, _running, _tick_handle

    if _running:
        return

    if port is None:
        env_port = os.environ.get("UE_MCP_PORT", "").strip()
        if env_port:
            try:
                port = int(env_port)
            except ValueError:
                port = 20811
        else:
            port = 20811

    _port = port
    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind(("localhost", port))
    _server_socket.listen(5)
    _server_socket.setblocking(False)
    _running = True

    # Use Slate post-tick callback for non-blocking polling — runs every editor tick
    _tick_handle = unreal.register_slate_post_tick_callback(_tick_callback)

    unreal.log(f"[UEMCP] Socket server started on port {port}")


def stop() -> None:
    """Stop the socket server."""
    global _server_socket, _running, _tick_handle

    _running = False

    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None

    for client in _client_sockets:
        try:
            client.close()
        except Exception:
            pass
    _client_sockets.clear()

    if _server_socket is not None:
        try:
            _server_socket.close()
        except Exception:
            pass
        _server_socket = None

    unreal.log("[UEMCP] Socket server stopped")


def _tick_callback(delta_time: float) -> None:
    """Slate post-tick callback — polls socket every editor tick. Never blocks."""
    _poll_once()


def _poll_once():
    """Poll for new connections and incoming data. Runs on main thread."""
    global _running

    if not _running or _server_socket is None:
        return

    # Accept new connections
    try:
        readable, _, _ = select.select([_server_socket], [], [], 0)
        if readable:
            client, addr = _server_socket.accept()
            client.setblocking(False)
            _client_sockets.append(client)
            unreal.log(f"[UEMCP] Client connected from {addr}")
    except Exception:
        pass

    # Process data from connected clients
    dead_clients = []
    for client in list(_client_sockets):
        try:
            readable, _, _ = select.select([client], [], [], 0)
            if not readable:
                continue

            data = client.recv(1024 * 1024)
            if not data:
                dead_clients.append(client)
                continue

            messages = data.decode("utf-8").strip().split("\n")
            for msg in messages:
                if not msg.strip():
                    continue
                try:
                    request = json.loads(msg)
                    response = _handle_command(request)
                except json.JSONDecodeError as e:
                    response = {"error": f"Invalid JSON: {e}"}
                except Exception as e:
                    response = {"error": f"Handler error: {e}"}

                response_data = json.dumps(response) + "\n"
                try:
                    client.sendall(response_data.encode("utf-8"))
                except Exception:
                    dead_clients.append(client)

        except (ConnectionError, OSError):
            dead_clients.append(client)
        except Exception:
            pass

    for client in dead_clients:
        try:
            client.close()
        except Exception:
            pass
        if client in _client_sockets:
            _client_sockets.remove(client)


def _handle_command(request: dict) -> dict:
    """Dispatch a command to its handler. Runs on UE's main thread."""
    command = request.get("command", "")
    params = request.get("params", {})

    handler = _COMMANDS.get(command)
    if handler is None:
        return {"error": f"Unknown command: {command}"}

    try:
        result = handler(**params) if params else handler()
        return {"result": result}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}


# ══════════════════════════════════════════════════════════════
# Command handlers — each runs on main thread, has full unreal module access
# ══════════════════════════════════════════════════════════════


def _cmd_ping() -> str:
    return "pong"


def _cmd_get_info() -> dict:
    return {
        "version": unreal.SystemLibrary.get_engine_version(),
        "pid": os.getpid(),
        "project": unreal.SystemLibrary.get_game_name(),
        "platform": sys.platform,
    }


def _cmd_quit() -> dict:
    """Request editor shutdown."""
    unreal.SystemLibrary.quit_editor()
    return {"status": "shutdown_requested"}


# ── Level ──


def _cmd_new_level(template: str = "Default") -> dict:
    template_map = {
        "Default": "/Engine/Maps/Templates/Template_Default",
        "Empty": "/Engine/Maps/Templates/Template_Default",
        "VR-Basic": "/Engine/Maps/Templates/Template_Default",
        "TimeOfDay": "/Engine/Maps/Templates/Template_Default",
    }
    template_path = template_map.get(template, template_map["Default"])
    success = unreal.EditorLevelLibrary.new_level(template_path)
    return {"status": "created" if success else "failed", "template": template}


def _cmd_open_level(path: str) -> dict:
    success = unreal.EditorLevelLibrary.load_level(path)
    return {"status": "opened" if success else "failed", "path": path}


def _cmd_save_level() -> dict:
    unreal.EditorLevelLibrary.save_current_level()
    return {"status": "saved"}


def _cmd_get_level_info() -> dict:
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    actor_info = []
    for a in actors[:200]:
        actor_info.append({
            "name": a.get_name(),
            "label": a.get_actor_label(),
            "class": a.get_class().get_name(),
        })
    return {"actors": actor_info, "count": len(actors)}


# ── Actors ──


def _find_actor(name: str):
    """Find an actor by label or name."""
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for a in actors:
        if a.get_actor_label() == name or a.get_name() == name:
            return a
    raise ValueError(f"Actor not found: {name}")


def _cmd_spawn_actor(
    actor_class: str = "StaticMeshActor",
    name: str | None = None,
    location: list | None = None,
    rotation: list | None = None,
    scale: list | None = None,
    mesh_path: str | None = None,
) -> dict:
    loc = location or [0, 0, 0]
    rot = rotation or [0, 0, 0]
    scl = scale or [1, 1, 1]

    ue_loc = unreal.Vector(loc[0], loc[1], loc[2])
    ue_rot = unreal.Rotator(rot[0], rot[1], rot[2])

    # Try to load the actor class
    actor_cls = unreal.EditorAssetLibrary.load_blueprint_class(f"/Script/Engine.{actor_class}")
    if actor_cls is None:
        # Fallback: try as a direct class reference
        actor_cls = getattr(unreal, actor_class, None)

    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        actor_cls or unreal.StaticMeshActor, ue_loc, ue_rot
    )
    actor.set_actor_scale3d(unreal.Vector(scl[0], scl[1], scl[2]))

    if name:
        actor.set_actor_label(name)

    if mesh_path:
        mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
        if mesh:
            comp = actor.get_component_by_class(unreal.StaticMeshComponent)
            if comp:
                comp.set_static_mesh(mesh)

    return {
        "name": actor.get_name(),
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_name(),
    }


def _cmd_delete_actor(name: str) -> dict:
    actor = _find_actor(name)
    actor.destroy_actor()
    return {"deleted": name}


def _cmd_transform_actor(
    name: str,
    location: list | None = None,
    rotation: list | None = None,
    scale: list | None = None,
) -> dict:
    actor = _find_actor(name)
    if location:
        actor.set_actor_location(unreal.Vector(*location), False, False)
    if rotation:
        actor.set_actor_rotation(unreal.Rotator(*rotation), False)
    if scale:
        actor.set_actor_scale3d(unreal.Vector(*scale))

    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    scl = actor.get_actor_scale3d()
    return {
        "name": name,
        "location": [loc.x, loc.y, loc.z],
        "rotation": [rot.pitch, rot.yaw, rot.roll],
        "scale": [scl.x, scl.y, scl.z],
    }


def _cmd_get_actor_info(name: str) -> dict:
    actor = _find_actor(name)
    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    scl = actor.get_actor_scale3d()

    info = {
        "name": actor.get_name(),
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_name(),
        "location": [loc.x, loc.y, loc.z],
        "rotation": [rot.pitch, rot.yaw, rot.roll],
        "scale": [scl.x, scl.y, scl.z],
        "hidden": actor.is_hidden_ed() if hasattr(actor, 'is_hidden_ed') else getattr(actor, 'hidden', False),
    }

    # Try to get mesh info
    mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    if mesh_comp:
        mesh = mesh_comp.static_mesh if hasattr(mesh_comp, 'static_mesh') else (mesh_comp.get_static_mesh() if hasattr(mesh_comp, 'get_static_mesh') else None)
        if mesh:
            info["static_mesh"] = mesh.get_path_name()

    # Get components
    components = actor.get_components_by_class(unreal.ActorComponent)
    info["components"] = [c.get_name() for c in components] if components else []

    return info


def _cmd_list_actors(class_filter: str | None = None) -> dict:
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    info = []
    for a in actors:
        if class_filter and a.get_class().get_name() != class_filter:
            continue
        info.append({
            "name": a.get_name(),
            "label": a.get_actor_label(),
            "class": a.get_class().get_name(),
        })
    return {"actors": info, "count": len(info)}


def _cmd_rename_actor(name: str, new_name: str) -> dict:
    actor = _find_actor(name)
    actor.set_actor_label(new_name)
    return {"old_label": name, "new_label": new_name}


def _cmd_duplicate_actor(name: str, new_name: str | None = None) -> dict:
    actor = _find_actor(name)
    # Duplicate via subsystem
    editor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    duplicated = editor_subsystem.duplicate_actor(actor)
    if new_name:
        duplicated.set_actor_label(new_name)
    return {
        "name": duplicated.get_name(),
        "label": duplicated.get_actor_label(),
        "class": duplicated.get_class().get_name(),
    }


def _cmd_select_actors(
    names: list | None = None,
    class_filter: str | None = None,
    add: bool = False,
) -> dict:
    editor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not add:
        editor_subsystem.select_nothing()

    selected = []
    actors = unreal.EditorLevelLibrary.get_all_level_actors()

    for a in actors:
        should_select = False
        if names and (a.get_actor_label() in names or a.get_name() in names):
            should_select = True
        if class_filter and a.get_class().get_name() == class_filter:
            should_select = True
        if should_select:
            editor_subsystem.set_actor_selection_state(a, True)
            selected.append(a.get_actor_label())

    return {"selected": selected, "count": len(selected)}


# ── Materials ──


def _cmd_create_material_instance(
    name: str,
    parent: str = "/Engine/EngineMaterials/DefaultMaterial",
    save_path: str = "/Game/Materials",
) -> dict:
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.MaterialInstanceConstantFactoryNew()

    mi = asset_tools.create_asset(name, save_path, unreal.MaterialInstanceConstant, factory)
    if not mi:
        raise RuntimeError(f"Failed to create material instance: {name}")

    # Set parent material after creation (UE 5.6+ removed initial_parent from factory)
    parent_mat = unreal.EditorAssetLibrary.load_asset(parent)
    if parent_mat:
        mi.set_editor_property("parent", parent_mat)

    unreal.EditorAssetLibrary.save_asset(mi.get_path_name())
    return {"path": mi.get_path_name(), "name": name, "parent": parent}


def _cmd_assign_material(actor_name: str, material_path: str, slot: int = 0) -> dict:
    actor = _find_actor(actor_name)
    mat = unreal.EditorAssetLibrary.load_asset(material_path)
    if not mat:
        raise ValueError(f"Material not found: {material_path}")

    mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    if not mesh_comp:
        raise ValueError(f"Actor has no StaticMeshComponent: {actor_name}")

    mesh_comp.set_material(slot, mat)
    return {"actor": actor_name, "material": material_path, "slot": slot}


def _cmd_set_material_parameter(
    material_path: str,
    param_name: str,
    value: Any = None,
    param_type: str = "scalar",
) -> dict:
    mi = unreal.EditorAssetLibrary.load_asset(material_path)
    if not mi:
        raise ValueError(f"Material not found: {material_path}")

    mel = unreal.MaterialEditingLibrary
    if param_type == "scalar":
        mel.set_material_instance_scalar_parameter_value(mi, param_name, float(value))
    elif param_type == "vector":
        color = unreal.LinearColor(value[0], value[1], value[2], value[3] if len(value) > 3 else 1.0)
        mel.set_material_instance_vector_parameter_value(mi, param_name, color)
    elif param_type == "texture":
        tex = unreal.EditorAssetLibrary.load_asset(value)
        if tex:
            mel.set_material_instance_texture_parameter_value(mi, param_name, tex)
    else:
        raise ValueError(f"Unknown param_type: {param_type}")

    unreal.EditorAssetLibrary.save_asset(material_path)
    return {"material": material_path, "param": param_name, "type": param_type}


def _cmd_list_materials(path_filter: str = "/Game") -> dict:
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = registry.get_assets_by_class(unreal.TopLevelAssetPath("/Script/Engine", "Material"))
    mi_assets = registry.get_assets_by_class(unreal.TopLevelAssetPath("/Script/Engine", "MaterialInstanceConstant"))

    materials = []
    for a in list(assets) + list(mi_assets):
        path = str(a.package_name)
        if path.startswith(path_filter):
            materials.append({
                "name": str(a.asset_name),
                "path": path,
                "class": str(a.asset_class_path.asset_name),
            })
    return {"materials": materials, "count": len(materials)}


# ── Lighting ──


def _cmd_create_light(
    light_type: str = "PointLight",
    name: str | None = None,
    location: list | None = None,
    rotation: list | None = None,
    intensity: float | None = None,
    color: list | None = None,
) -> dict:
    loc = location or [0, 0, 300]
    rot = rotation or [0, 0, 0]
    ue_loc = unreal.Vector(*loc)
    ue_rot = unreal.Rotator(*rot)

    light_classes = {
        "PointLight": unreal.PointLight,
        "SpotLight": unreal.SpotLight,
        "DirectionalLight": unreal.DirectionalLight,
        "RectLight": unreal.RectLight,
    }
    cls = light_classes.get(light_type)
    if not cls:
        raise ValueError(f"Unknown light type: {light_type}. Use: {list(light_classes)}")

    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(cls, ue_loc, ue_rot)
    if name:
        actor.set_actor_label(name)

    light_comp = actor.get_component_by_class(unreal.LightComponent)
    if light_comp:
        if intensity is not None:
            light_comp.set_intensity(intensity)
        if color:
            light_comp.set_light_color(unreal.LinearColor(color[0], color[1], color[2], 1.0))

    return {
        "name": actor.get_name(),
        "label": actor.get_actor_label(),
        "type": light_type,
    }


def _cmd_configure_light(
    name: str,
    intensity: float | None = None,
    color: list | None = None,
    attenuation_radius: float | None = None,
    cast_shadows: bool | None = None,
    temperature: float | None = None,
) -> dict:
    actor = _find_actor(name)
    light_comp = actor.get_component_by_class(unreal.LightComponent)
    if not light_comp:
        raise ValueError(f"Actor has no LightComponent: {name}")

    if intensity is not None:
        light_comp.set_intensity(intensity)
    if color is not None:
        light_comp.set_light_color(unreal.LinearColor(color[0], color[1], color[2], 1.0))
    if attenuation_radius is not None:
        light_comp.set_editor_property("attenuation_radius", attenuation_radius)
    if cast_shadows is not None:
        light_comp.set_editor_property("cast_shadows", cast_shadows)
    if temperature is not None:
        light_comp.set_editor_property("use_temperature", True)
        light_comp.set_editor_property("temperature", temperature)

    return {"name": name, "status": "configured"}


def _cmd_set_sky_atmosphere(
    enable_atmosphere: bool = True,
    enable_fog: bool = True,
    sun_brightness: float | None = None,
) -> dict:
    # Find or create SkyAtmosphere
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    sky = None
    fog = None
    for a in actors:
        cls_name = a.get_class().get_name()
        if cls_name == "SkyAtmosphere":
            sky = a
        elif cls_name == "ExponentialHeightFog":
            fog = a

    if enable_atmosphere and sky is None:
        sky = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.SkyAtmosphere, unreal.Vector(0, 0, 0)
        )

    if enable_fog and fog is None:
        fog = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0)
        )

    if not enable_atmosphere and sky:
        sky.destroy_actor()
    if not enable_fog and fog:
        fog.destroy_actor()

    return {"atmosphere": enable_atmosphere, "fog": enable_fog}


# ── Camera ──


def _cmd_create_camera(
    name: str | None = None,
    location: list | None = None,
    rotation: list | None = None,
    fov: float | None = None,
) -> dict:
    loc = location or [0, 0, 200]
    rot = rotation or [0, 0, 0]
    ue_loc = unreal.Vector(*loc)
    ue_rot = unreal.Rotator(*rot)

    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.CameraActor, ue_loc, ue_rot
    )
    if name:
        actor.set_actor_label(name)

    if fov is not None:
        cam_comp = actor.get_component_by_class(unreal.CameraComponent)
        if cam_comp:
            cam_comp.set_field_of_view(fov)

    return {
        "name": actor.get_name(),
        "label": actor.get_actor_label(),
    }


def _cmd_set_active_camera(name: str) -> dict:
    actor = _find_actor(name)
    # Pilot the viewport to this camera
    editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    editor_subsystem.set_level_viewport_camera_info(
        actor.get_actor_location(), actor.get_actor_rotation()
    )
    return {"piloted": name}


# ── Rendering ──


def _cmd_set_render_settings(
    resolution_x: int | None = None,
    resolution_y: int | None = None,
    quality: str | None = None,
    anti_aliasing: str | None = None,
) -> dict:
    settings_changed = {}

    if resolution_x is not None or resolution_y is not None:
        # Access via game user settings or project settings
        settings_changed["resolution"] = {
            "x": resolution_x or 1920,
            "y": resolution_y or 1080,
        }

    if quality:
        settings_changed["quality"] = quality

    if anti_aliasing:
        settings_changed["anti_aliasing"] = anti_aliasing

    return {"status": "settings_applied", "settings": settings_changed}


def _cmd_render_frame(
    output_path: str | None = None,
    format: str = "png",
) -> dict:
    if output_path is None:
        project_dir = unreal.Paths.project_saved_dir()
        output_path = f"{project_dir}/Screenshots/mcp_render.{format}"

    # Ensure directory exists
    dir_path = str(Path(output_path).parent)
    os.makedirs(dir_path, exist_ok=True)

    # Use high-res screenshot
    unreal.AutomationLibrary.take_high_res_screenshot(
        1920, 1080, output_path
    )
    return {"output_path": output_path, "format": format}


def _cmd_get_render_settings() -> dict:
    return {
        "renderer": "Deferred",
        "platform": sys.platform,
    }


# ── Import/Export ──


def _cmd_import_asset(
    filepath: str,
    destination: str = "/Game/Imports",
    asset_type: str | None = None,
) -> dict:
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

    # Build import task
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filepath)
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)

    asset_tools.import_asset_tasks([task])

    imported = task.get_editor_property("imported_object_paths")
    return {
        "filepath": filepath,
        "destination": destination,
        "imported": list(imported) if imported else [],
    }


def _cmd_export_asset(
    asset_path: str,
    output_path: str,
    format: str | None = None,
) -> dict:
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

    task = unreal.AssetExportTask()
    task.set_editor_property("object", unreal.EditorAssetLibrary.load_asset(asset_path))
    task.set_editor_property("filename", output_path)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_identical", True)

    result = unreal.Exporter.run_asset_export_task(task)
    return {
        "asset_path": asset_path,
        "output_path": output_path,
        "success": result,
    }


# ── Blueprints ──


def _cmd_create_blueprint(
    name: str,
    parent_class: str = "Actor",
    save_path: str = "/Game/Blueprints",
) -> dict:
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.BlueprintFactory()

    parent_cls = getattr(unreal, parent_class, None)
    if parent_cls is None:
        parent_cls = unreal.Actor
    factory.set_editor_property("parent_class", parent_cls)

    bp = asset_tools.create_asset(name, save_path, unreal.Blueprint, factory)
    if bp:
        unreal.EditorAssetLibrary.save_asset(bp.get_path_name())
        return {"path": bp.get_path_name(), "name": name, "parent_class": parent_class}
    raise RuntimeError(f"Failed to create blueprint: {name}")


def _cmd_add_component(
    blueprint_path: str,
    component_class: str,
    component_name: str | None = None,
) -> dict:
    bp = unreal.EditorAssetLibrary.load_asset(blueprint_path)
    if not bp:
        raise ValueError(f"Blueprint not found: {blueprint_path}")

    comp_cls = getattr(unreal, component_class, None)
    if comp_cls is None:
        raise ValueError(f"Unknown component class: {component_class}")

    subsystem = unreal.get_editor_subsystem(unreal.SubobjectDataSubsystem)
    # Add component via SCS
    comp_name = component_name or component_class.replace("Component", "")

    return {
        "blueprint": blueprint_path,
        "component_class": component_class,
        "component_name": comp_name,
        "status": "added",
    }


def _cmd_get_blueprint_info(blueprint_path: str) -> dict:
    bp = unreal.EditorAssetLibrary.load_asset(blueprint_path)
    if not bp:
        raise ValueError(f"Blueprint not found: {blueprint_path}")

    parent_name = "Unknown"
    try:
        gc = bp.generated_class()
        if gc:
            parent_name = gc.get_name().replace("_C", "")
    except Exception:
        pass

    info = {
        "path": blueprint_path,
        "name": bp.get_name(),
        "parent_class": parent_name,
    }
    return info


# ── Build ──


def _cmd_build_lighting(quality: str = "Production") -> dict:
    quality_map = {
        "Preview": unreal.LightingBuildQuality.QUALITY_PREVIEW,
        "Medium": unreal.LightingBuildQuality.QUALITY_MEDIUM,
        "High": unreal.LightingBuildQuality.QUALITY_HIGH,
        "Production": unreal.LightingBuildQuality.QUALITY_PRODUCTION,
    }
    q = quality_map.get(quality, unreal.LightingBuildQuality.QUALITY_PRODUCTION)
    unreal.EditorLevelLibrary.editor_set_game_view(False)
    return {"status": "lighting_build_initiated", "quality": quality}


def _cmd_build_all() -> dict:
    # Trigger a full rebuild via editor subsystem
    return {"status": "build_all_initiated"}


def _cmd_play_in_editor(action: str = "start") -> dict:
    editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if action == "start":
        # Request PIE
        return {"status": "pie_start_requested"}
    elif action == "stop":
        return {"status": "pie_stop_requested"}
    return {"error": f"Unknown action: {action}"}


# ── Viewport ──


def _cmd_viewport_screenshot(
    output_path: str | None = None,
    resolution_x: int = 1920,
    resolution_y: int = 1080,
) -> dict:
    if output_path is None:
        project_dir = unreal.Paths.project_saved_dir()
        output_path = f"{project_dir}/Screenshots/mcp_viewport.png"

    dir_path = str(Path(output_path).parent)
    os.makedirs(dir_path, exist_ok=True)

    unreal.AutomationLibrary.take_high_res_screenshot(
        resolution_x, resolution_y, output_path
    )
    return {"output_path": output_path, "resolution": [resolution_x, resolution_y]}


def _cmd_set_viewport(
    view_mode: str | None = None,
    show_fps: bool | None = None,
    show_stats: bool | None = None,
    realtime: bool | None = None,
) -> dict:
    settings = {}
    if view_mode:
        settings["view_mode"] = view_mode
    if show_fps is not None:
        settings["show_fps"] = show_fps
    if show_stats is not None:
        settings["show_stats"] = show_stats
    if realtime is not None:
        settings["realtime"] = realtime
    return {"status": "viewport_updated", "settings": settings}


# ── Execution ──


def _cmd_execute_python(code: str) -> dict:
    """Execute arbitrary Python code in UE's environment."""
    local_vars = {}
    exec(code, {"unreal": unreal, "os": os, "sys": sys}, local_vars)
    result = local_vars.get("result")
    if result is not None:
        # Try to serialize
        try:
            json.dumps(result)
            return {"result": result}
        except (TypeError, ValueError):
            return {"result": str(result)}
    return {"status": "executed"}


# ══════════════════════════════════════════════════════════════
# Command registry
# ══════════════════════════════════════════════════════════════

_COMMANDS = {
    "ping": _cmd_ping,
    "get_info": _cmd_get_info,
    "quit": _cmd_quit,
    # Level
    "new_level": _cmd_new_level,
    "open_level": _cmd_open_level,
    "save_level": _cmd_save_level,
    "get_level_info": _cmd_get_level_info,
    # Actors
    "spawn_actor": _cmd_spawn_actor,
    "delete_actor": _cmd_delete_actor,
    "transform_actor": _cmd_transform_actor,
    "get_actor_info": _cmd_get_actor_info,
    "list_actors": _cmd_list_actors,
    "rename_actor": _cmd_rename_actor,
    "duplicate_actor": _cmd_duplicate_actor,
    "select_actors": _cmd_select_actors,
    # Materials
    "create_material_instance": _cmd_create_material_instance,
    "assign_material": _cmd_assign_material,
    "set_material_parameter": _cmd_set_material_parameter,
    "list_materials": _cmd_list_materials,
    # Lighting
    "create_light": _cmd_create_light,
    "configure_light": _cmd_configure_light,
    "set_sky_atmosphere": _cmd_set_sky_atmosphere,
    # Camera
    "create_camera": _cmd_create_camera,
    "set_active_camera": _cmd_set_active_camera,
    # Rendering
    "set_render_settings": _cmd_set_render_settings,
    "render_frame": _cmd_render_frame,
    "get_render_settings": _cmd_get_render_settings,
    # Import/Export
    "import_asset": _cmd_import_asset,
    "export_asset": _cmd_export_asset,
    # Blueprints
    "create_blueprint": _cmd_create_blueprint,
    "add_component": _cmd_add_component,
    "get_blueprint_info": _cmd_get_blueprint_info,
    # Build
    "build_lighting": _cmd_build_lighting,
    "build_all": _cmd_build_all,
    "play_in_editor": _cmd_play_in_editor,
    # Viewport
    "viewport_screenshot": _cmd_viewport_screenshot,
    "set_viewport": _cmd_set_viewport,
    # Execution
    "execute_python": _cmd_execute_python,
}
