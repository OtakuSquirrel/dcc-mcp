"""Non-blocking TCP socket server running on bpy.app.timers.

All incoming JSON commands are queued and executed on Blender's main thread
via the timer callback. This ensures thread-safe access to the bpy API.

Protocol: newline-delimited JSON. Each request is a JSON object with:
  {"command": "...", "params": {...}}
Response is a JSON object with:
  {"result": ...} or {"error": "..."}
"""

from __future__ import annotations

import json
import logging
import os
import select
import socket
import traceback
from typing import Any

import bpy

logger = logging.getLogger(__name__)

_server_socket: socket.socket | None = None
_client_sockets: list[socket.socket] = []
_port: int = 19811
_running: bool = False


def is_running() -> bool:
    return _running


def get_port() -> int:
    return _port


def start(port: int = 19811) -> None:
    """Start the socket server on the given port."""
    global _server_socket, _port, _running

    if _running:
        return

    _port = port
    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind(("localhost", port))
    _server_socket.listen(5)
    _server_socket.setblocking(False)
    _running = True

    bpy.app.timers.register(_poll_timer, first_interval=0.05, persistent=True)
    logger.info("[BlenderMCP] Socket server started on port %d", port)


def stop() -> None:
    """Stop the socket server and close all connections."""
    global _server_socket, _running

    _running = False

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

    logger.info("[BlenderMCP] Socket server stopped")


def _poll_timer() -> float | None:
    """Timer callback — polls for new connections and incoming data.

    Returns the interval for the next call (0.05s = 20 Hz).
    Returns None to unregister.
    """
    if not _running or _server_socket is None:
        return None

    # Accept new connections
    try:
        readable, _, _ = select.select([_server_socket], [], [], 0)
        if readable:
            client, addr = _server_socket.accept()
            client.setblocking(False)
            _client_sockets.append(client)
            logger.info("[BlenderMCP] Client connected from %s", addr)
    except Exception:
        pass

    # Process data from connected clients
    dead_clients = []
    for client in _client_sockets:
        try:
            readable, _, _ = select.select([client], [], [], 0)
            if not readable:
                continue

            data = client.recv(1024 * 1024)
            if not data:
                dead_clients.append(client)
                continue

            # Handle potentially multiple newline-delimited messages
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

    # Clean up dead connections
    for client in dead_clients:
        try:
            client.close()
        except Exception:
            pass
        if client in _client_sockets:
            _client_sockets.remove(client)

    return 0.05  # 20 Hz polling


def _handle_command(request: dict) -> dict:
    """Dispatch a command to its handler.

    Runs on Blender's main thread (called from timer).
    """
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
# Command handlers — each runs on main thread, has full bpy access
# ══════════════════════════════════════════════════════════════


def _cmd_ping() -> str:
    return "pong"


def _cmd_get_info() -> dict:
    return {
        "version": ".".join(str(v) for v in bpy.app.version),
        "pid": os.getpid(),
        "file": bpy.data.filepath or "(unsaved)",
    }


def _cmd_get_scene_info() -> dict:
    scene = bpy.context.scene
    objects = [{"name": obj.name, "type": obj.type} for obj in scene.objects]
    collections = [c.name for c in scene.collection.children]
    return {
        "name": scene.name,
        "objects": objects,
        "object_count": len(objects),
        "collections": collections,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "render_engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    }


def _cmd_new_scene(name: str = "Scene") -> dict:
    bpy.ops.scene.new(type="NEW")
    scene = bpy.context.scene
    scene.name = name
    return {"name": scene.name}


def _cmd_open_file(filepath: str) -> dict:
    bpy.ops.wm.open_mainfile(filepath=filepath)
    return {"filepath": bpy.data.filepath, "name": bpy.context.scene.name}


def _cmd_save_file(filepath: str | None = None) -> dict:
    if filepath:
        bpy.ops.wm.save_as_mainfile(filepath=filepath)
    else:
        bpy.ops.wm.save_mainfile()
    return {"filepath": bpy.data.filepath}


def _cmd_create_object(
    type: str = "MESH",
    mesh_type: str = "cube",
    name: str | None = None,
    location: list | None = None,
    rotation: list | None = None,
    scale: list | None = None,
) -> dict:
    import mathutils

    mesh_ops = {
        "cube": bpy.ops.mesh.primitive_cube_add,
        "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
        "plane": bpy.ops.mesh.primitive_plane_add,
        "cylinder": bpy.ops.mesh.primitive_cylinder_add,
        "cone": bpy.ops.mesh.primitive_cone_add,
        "torus": bpy.ops.mesh.primitive_torus_add,
        "monkey": bpy.ops.mesh.primitive_monkey_add,
        "circle": bpy.ops.mesh.primitive_circle_add,
        "ico_sphere": bpy.ops.mesh.primitive_ico_sphere_add,
    }

    loc = tuple(location) if location else (0, 0, 0)
    rot = tuple(rotation) if rotation else (0, 0, 0)

    if type == "MESH":
        op = mesh_ops.get(mesh_type)
        if op is None:
            raise ValueError(f"Unknown mesh type: {mesh_type}. Available: {list(mesh_ops.keys())}")
        op(location=loc, rotation=rot)
    elif type == "EMPTY":
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=loc, rotation=rot)
    elif type == "CURVE":
        bpy.ops.curve.primitive_bezier_curve_add(location=loc, rotation=rot)
    elif type == "ARMATURE":
        bpy.ops.object.armature_add(location=loc, rotation=rot)
    else:
        raise ValueError(f"Unknown object type: {type}")

    obj = bpy.context.active_object
    if name:
        obj.name = name
    if scale:
        obj.scale = tuple(scale)

    return {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation": list(obj.rotation_euler),
        "scale": list(obj.scale),
    }


def _cmd_delete_object(name: str) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": name}


def _cmd_select_objects(
    names: list | None = None,
    pattern: str | None = None,
    deselect_all: bool = True,
) -> dict:
    import fnmatch

    if deselect_all:
        bpy.ops.object.select_all(action="DESELECT")

    selected = []
    if names:
        for n in names:
            obj = bpy.data.objects.get(n)
            if obj:
                obj.select_set(True)
                selected.append(n)
    if pattern:
        for obj in bpy.data.objects:
            if fnmatch.fnmatch(obj.name, pattern):
                obj.select_set(True)
                selected.append(obj.name)

    return {"selected": selected}


def _cmd_get_object_info(name: str) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")

    info = {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "dimensions": list(obj.dimensions),
        "parent": obj.parent.name if obj.parent else None,
        "visible": obj.visible_get(),
        "modifiers": [{"name": m.name, "type": m.type} for m in obj.modifiers],
        "materials": [m.name if m else None for m in obj.data.materials] if hasattr(obj.data, "materials") else [],
    }

    if obj.type == "MESH" and obj.data:
        info["vertices"] = len(obj.data.vertices)
        info["edges"] = len(obj.data.edges)
        info["polygons"] = len(obj.data.polygons)

    return info


def _cmd_transform_object(
    name: str,
    location: list | None = None,
    rotation: list | None = None,
    scale: list | None = None,
) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    if location is not None:
        obj.location = tuple(location)
    if rotation is not None:
        obj.rotation_euler = tuple(rotation)
    if scale is not None:
        obj.scale = tuple(scale)
    return {
        "name": obj.name,
        "location": list(obj.location),
        "rotation": list(obj.rotation_euler),
        "scale": list(obj.scale),
    }


def _cmd_duplicate_object(name: str, new_name: str | None = None, linked: bool = False) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")

    if linked:
        new_obj = obj.copy()
    else:
        new_obj = obj.copy()
        if obj.data:
            new_obj.data = obj.data.copy()

    if new_name:
        new_obj.name = new_name
    bpy.context.collection.objects.link(new_obj)
    return {"name": new_obj.name, "type": new_obj.type}


def _cmd_list_objects(type_filter: str | None = None) -> dict:
    objects = []
    for obj in bpy.data.objects:
        if type_filter and obj.type != type_filter:
            continue
        objects.append({"name": obj.name, "type": obj.type})
    return {"objects": objects, "count": len(objects)}


def _cmd_create_material(name: str, color: list | None = None) -> dict:
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    if color:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = tuple(color[:4] if len(color) >= 4 else color + [1.0])
    return {"name": mat.name}


def _cmd_assign_material(object_name: str, material_name: str, slot: int = 0) -> dict:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    mat = bpy.data.materials.get(material_name)
    if mat is None:
        raise ValueError(f"Material not found: {material_name}")

    if len(obj.data.materials) <= slot:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[slot] = mat
    return {"object": object_name, "material": material_name, "slot": slot}


def _cmd_add_shader_node(material_name: str, node_type: str, location: list | None = None) -> dict:
    mat = bpy.data.materials.get(material_name)
    if mat is None:
        raise ValueError(f"Material not found: {material_name}")
    if not mat.use_nodes:
        mat.use_nodes = True
    node = mat.node_tree.nodes.new(type=node_type)
    if location:
        node.location = tuple(location)
    return {"name": node.name, "type": node.bl_idname}


def _cmd_connect_shader_nodes(
    material_name: str,
    from_node: str,
    from_output: int | str,
    to_node: str,
    to_input: int | str,
) -> dict:
    mat = bpy.data.materials.get(material_name)
    if mat is None:
        raise ValueError(f"Material not found: {material_name}")
    tree = mat.node_tree
    fn = tree.nodes.get(from_node)
    tn = tree.nodes.get(to_node)
    if fn is None:
        raise ValueError(f"Node not found: {from_node}")
    if tn is None:
        raise ValueError(f"Node not found: {to_node}")

    out = fn.outputs[from_output]
    inp = tn.inputs[to_input]
    tree.links.new(out, inp)
    return {"from": from_node, "to": to_node}


def _cmd_get_material_info(material_name: str) -> dict:
    mat = bpy.data.materials.get(material_name)
    if mat is None:
        raise ValueError(f"Material not found: {material_name}")
    nodes = []
    if mat.use_nodes:
        for n in mat.node_tree.nodes:
            nodes.append({"name": n.name, "type": n.bl_idname, "location": list(n.location)})
    return {"name": mat.name, "nodes": nodes}


def _cmd_add_modifier(object_name: str, modifier_type: str, name: str | None = None, settings: dict | None = None) -> dict:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    mod = obj.modifiers.new(name=name or modifier_type, type=modifier_type)
    if settings:
        for k, v in settings.items():
            setattr(mod, k, v)
    return {"name": mod.name, "type": mod.type}


def _cmd_remove_modifier(object_name: str, modifier_name: str) -> dict:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    mod = obj.modifiers.get(modifier_name)
    if mod is None:
        raise ValueError(f"Modifier not found: {modifier_name}")
    obj.modifiers.remove(mod)
    return {"removed": modifier_name}


def _cmd_apply_modifier(object_name: str, modifier_name: str) -> dict:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier_name)
    return {"applied": modifier_name}


def _cmd_get_modifiers(object_name: str) -> dict:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    mods = [{"name": m.name, "type": m.type} for m in obj.modifiers]
    return {"modifiers": mods, "count": len(mods)}


def _cmd_insert_keyframe(object_name: str, data_path: str, frame: int | None = None, value: float | None = None) -> dict:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    if frame is not None:
        bpy.context.scene.frame_set(frame)
    if value is not None:
        exec(f"obj.{data_path} = {value}")
    obj.keyframe_insert(data_path=data_path)
    return {"object": object_name, "data_path": data_path, "frame": bpy.context.scene.frame_current}


def _cmd_remove_keyframe(object_name: str, data_path: str, frame: int | None = None) -> dict:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    if frame is not None:
        bpy.context.scene.frame_set(frame)
    obj.keyframe_delete(data_path=data_path)
    return {"removed": True}


def _cmd_set_frame(frame: int) -> dict:
    bpy.context.scene.frame_set(frame)
    return {"frame": frame}


def _cmd_get_timeline_info() -> dict:
    scene = bpy.context.scene
    return {
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "fps": scene.render.fps,
    }


def _cmd_create_camera(
    name: str = "Camera",
    location: list | None = None,
    rotation: list | None = None,
    focal_length: float = 50.0,
) -> dict:
    cam = bpy.data.cameras.new(name=name)
    cam.lens = focal_length
    obj = bpy.data.objects.new(name, cam)
    bpy.context.collection.objects.link(obj)
    if location:
        obj.location = tuple(location)
    if rotation:
        obj.rotation_euler = tuple(rotation)
    return {"name": obj.name, "focal_length": cam.lens}


def _cmd_set_active_camera(name: str) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "CAMERA":
        raise ValueError(f"Camera not found: {name}")
    bpy.context.scene.camera = obj
    return {"active_camera": name}


def _cmd_configure_camera(name: str, **kwargs) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "CAMERA":
        raise ValueError(f"Camera not found: {name}")
    cam = obj.data
    for k, v in kwargs.items():
        if k == "focal_length":
            cam.lens = v
        elif k == "sensor_width":
            cam.sensor_width = v
        elif k == "clip_start":
            cam.clip_start = v
        elif k == "clip_end":
            cam.clip_end = v
        elif k == "dof_focus_distance":
            cam.dof.use_dof = True
            cam.dof.focus_distance = v
        elif k == "dof_fstop":
            cam.dof.use_dof = True
            cam.dof.aperture_fstop = v
    return {"name": name, "focal_length": cam.lens}


def _cmd_create_light(
    type: str = "POINT",
    name: str | None = None,
    location: list | None = None,
    energy: float = 1000.0,
    color: list | None = None,
) -> dict:
    light = bpy.data.lights.new(name=name or type, type=type)
    light.energy = energy
    if color:
        light.color = tuple(color[:3])
    obj = bpy.data.objects.new(name or type, light)
    bpy.context.collection.objects.link(obj)
    if location:
        obj.location = tuple(location)
    return {"name": obj.name, "type": type, "energy": energy}


def _cmd_configure_light(name: str, **kwargs) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "LIGHT":
        raise ValueError(f"Light not found: {name}")
    light = obj.data
    for k, v in kwargs.items():
        if k == "energy":
            light.energy = v
        elif k == "color":
            light.color = tuple(v[:3])
        elif k == "shadow_soft_size":
            light.shadow_soft_size = v
        elif k == "spot_size":
            light.spot_size = v
        elif k == "spot_blend":
            light.spot_blend = v
    return {"name": name}


def _cmd_set_hdri(filepath: str, strength: float = 1.0, rotation: float = 0.0) -> dict:
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    tree.nodes.clear()

    output = tree.nodes.new("ShaderNodeOutputWorld")
    bg = tree.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    env = tree.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(filepath)
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = rotation
    coord = tree.nodes.new("ShaderNodeTexCoord")

    tree.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    tree.links.new(env.outputs["Color"], bg.inputs["Color"])
    tree.links.new(bg.outputs["Background"], output.inputs["Surface"])

    return {"filepath": filepath, "strength": strength}


def _cmd_set_render_engine(engine: str = "CYCLES", device: str = "GPU") -> dict:
    bpy.context.scene.render.engine = engine
    if engine == "CYCLES":
        bpy.context.preferences.addons["cycles"].preferences.compute_device_type = "CUDA"
        bpy.context.scene.cycles.device = device
    return {"engine": engine, "device": device}


def _cmd_set_resolution(width: int = 1920, height: int = 1080, percentage: int = 100) -> dict:
    r = bpy.context.scene.render
    r.resolution_x = width
    r.resolution_y = height
    r.resolution_percentage = percentage
    return {"width": width, "height": height, "percentage": percentage}


def _cmd_render_frame(output_path: str, frame: int | None = None, samples: int | None = None) -> dict:
    scene = bpy.context.scene
    if frame is not None:
        scene.frame_set(frame)
    if samples is not None and scene.render.engine == "CYCLES":
        scene.cycles.samples = samples
    scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)
    return {"output_path": output_path, "frame": scene.frame_current}


def _cmd_render_preview(output_path: str, quality: str = "medium") -> dict:
    scene = bpy.context.scene
    scene.render.filepath = output_path
    # Use viewport render (OpenGL)
    bpy.ops.render.opengl(write_still=True)
    return {"output_path": output_path}


def _cmd_viewport_screenshot(output_path: str) -> dict:
    bpy.ops.screen.screenshot(filepath=output_path)
    return {"output_path": output_path}


def _cmd_set_viewport_shading(mode: str = "MATERIAL") -> dict:
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = mode
                    return {"mode": mode}
    return {"error": "No 3D viewport found"}


def _cmd_set_viewport_camera(camera_name: str | None = None) -> dict:
    if camera_name:
        cam = bpy.data.objects.get(camera_name)
        if cam and cam.type == "CAMERA":
            bpy.context.scene.camera = cam
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces[0].region_3d.view_perspective = "CAMERA"
            return {"camera_view": True}
    return {"error": "No 3D viewport found"}


def _cmd_import_file(filepath: str, format: str | None = None) -> dict:
    import os
    ext = format or os.path.splitext(filepath)[1].lower().lstrip(".")
    importers = {
        "fbx": lambda: bpy.ops.import_scene.fbx(filepath=filepath),
        "obj": lambda: bpy.ops.wm.obj_import(filepath=filepath),
        "gltf": lambda: bpy.ops.import_scene.gltf(filepath=filepath),
        "glb": lambda: bpy.ops.import_scene.gltf(filepath=filepath),
        "usd": lambda: bpy.ops.wm.usd_import(filepath=filepath),
        "usdc": lambda: bpy.ops.wm.usd_import(filepath=filepath),
        "usda": lambda: bpy.ops.wm.usd_import(filepath=filepath),
        "abc": lambda: bpy.ops.wm.alembic_import(filepath=filepath),
    }
    importer = importers.get(ext)
    if importer is None:
        raise ValueError(f"Unsupported format: {ext}")
    importer()
    return {"imported": filepath, "format": ext}


def _cmd_export_file(filepath: str, format: str | None = None, selected_only: bool = False) -> dict:
    import os
    ext = format or os.path.splitext(filepath)[1].lower().lstrip(".")
    exporters = {
        "fbx": lambda: bpy.ops.export_scene.fbx(filepath=filepath, use_selection=selected_only),
        "obj": lambda: bpy.ops.wm.obj_export(filepath=filepath, export_selected_objects=selected_only),
        "gltf": lambda: bpy.ops.export_scene.gltf(filepath=filepath, use_selection=selected_only),
        "glb": lambda: bpy.ops.export_scene.gltf(filepath=filepath, use_selection=selected_only, export_format="GLB"),
        "usd": lambda: bpy.ops.wm.usd_export(filepath=filepath, selected_objects_only=selected_only),
        "usdc": lambda: bpy.ops.wm.usd_export(filepath=filepath, selected_objects_only=selected_only),
    }
    exporter = exporters.get(ext)
    if exporter is None:
        raise ValueError(f"Unsupported format: {ext}")
    exporter()
    return {"exported": filepath, "format": ext}


def _cmd_execute_code(code: str) -> dict:
    """Execute arbitrary Python code. Use `result = ...` to return data."""
    local_vars = {}
    exec(code, {"bpy": bpy, "__builtins__": __builtins__}, local_vars)
    result = local_vars.get("result", None)
    if result is not None:
        # Try to make it JSON-serializable
        try:
            json.dumps(result)
            return {"result": result}
        except (TypeError, ValueError):
            return {"result": str(result)}
    return {"executed": True}


def _cmd_quit() -> dict:
    """Quit Blender."""
    bpy.ops.wm.quit_blender()
    return {"quit": True}


# ── Command registry ──

_COMMANDS: dict[str, Any] = {
    "ping": _cmd_ping,
    "get_info": _cmd_get_info,
    "get_scene_info": _cmd_get_scene_info,
    "new_scene": _cmd_new_scene,
    "open_file": _cmd_open_file,
    "save_file": _cmd_save_file,
    "create_object": _cmd_create_object,
    "delete_object": _cmd_delete_object,
    "select_objects": _cmd_select_objects,
    "get_object_info": _cmd_get_object_info,
    "transform_object": _cmd_transform_object,
    "duplicate_object": _cmd_duplicate_object,
    "list_objects": _cmd_list_objects,
    "create_material": _cmd_create_material,
    "assign_material": _cmd_assign_material,
    "add_shader_node": _cmd_add_shader_node,
    "connect_shader_nodes": _cmd_connect_shader_nodes,
    "get_material_info": _cmd_get_material_info,
    "add_modifier": _cmd_add_modifier,
    "remove_modifier": _cmd_remove_modifier,
    "apply_modifier": _cmd_apply_modifier,
    "get_modifiers": _cmd_get_modifiers,
    "insert_keyframe": _cmd_insert_keyframe,
    "remove_keyframe": _cmd_remove_keyframe,
    "set_frame": _cmd_set_frame,
    "get_timeline_info": _cmd_get_timeline_info,
    "create_camera": _cmd_create_camera,
    "set_active_camera": _cmd_set_active_camera,
    "configure_camera": _cmd_configure_camera,
    "create_light": _cmd_create_light,
    "configure_light": _cmd_configure_light,
    "set_hdri": _cmd_set_hdri,
    "set_render_engine": _cmd_set_render_engine,
    "set_resolution": _cmd_set_resolution,
    "render_frame": _cmd_render_frame,
    "render_preview": _cmd_render_preview,
    "viewport_screenshot": _cmd_viewport_screenshot,
    "set_viewport_shading": _cmd_set_viewport_shading,
    "set_viewport_camera": _cmd_set_viewport_camera,
    "import_file": _cmd_import_file,
    "export_file": _cmd_export_file,
    "execute_code": _cmd_execute_code,
    "quit": _cmd_quit,
}
