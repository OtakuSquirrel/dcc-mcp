"""Actor operation tools for UE."""

from __future__ import annotations

from ue_mcp.server import mcp, ue


@mcp.tool()
def spawn_actor(
    actor_class: str = "StaticMeshActor",
    name: str | None = None,
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
    mesh_path: str | None = None,
) -> dict:
    """Spawn an actor in the level.

    Args:
        actor_class: UE actor class name.
        name: Optional actor label.
        location: [x, y, z] world location.
        rotation: [pitch, yaw, roll] in degrees.
        scale: [x, y, z] scale.
        mesh_path: Asset path for static mesh (if StaticMeshActor).
    """
    loc = location or [0, 0, 0]
    rot = rotation or [0, 0, 0]
    scl = scale or [1, 1, 1]

    code = f"""
import unreal
loc = unreal.Vector({loc[0]}, {loc[1]}, {loc[2]})
rot = unreal.Rotator({rot[0]}, {rot[1]}, {rot[2]})
actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
    unreal.{actor_class}, loc, rot
)
actor.set_actor_scale3d(unreal.Vector({scl[0]}, {scl[1]}, {scl[2]}))
"""
    if name:
        code += f"actor.set_actor_label('{name}')\n"
    if mesh_path:
        code += f"""
mesh = unreal.EditorAssetLibrary.load_asset('{mesh_path}')
if mesh:
    actor.static_mesh_component.set_static_mesh(mesh)
"""
    code += "result = actor.get_name()\n"
    return ue.execute_python(code)


@mcp.tool()
def delete_actor(name: str) -> dict:
    """Delete an actor by label or name.

    Args:
        name: Actor label or name.
    """
    return ue.execute_python(f"""
import unreal
actors = unreal.EditorLevelLibrary.get_all_level_actors()
for a in actors:
    if a.get_actor_label() == '{name}' or a.get_name() == '{name}':
        a.destroy_actor()
        break
""")


@mcp.tool()
def transform_actor(
    name: str,
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
) -> dict:
    """Set location, rotation, and/or scale of an actor.

    Args:
        name: Actor label or name.
        location: [x, y, z] world location.
        rotation: [pitch, yaw, roll] in degrees.
        scale: [x, y, z] scale.
    """
    code = f"""
import unreal
actors = unreal.EditorLevelLibrary.get_all_level_actors()
actor = None
for a in actors:
    if a.get_actor_label() == '{name}' or a.get_name() == '{name}':
        actor = a
        break
if actor is None:
    raise ValueError("Actor not found: {name}")
"""
    if location:
        code += f"actor.set_actor_location(unreal.Vector({location[0]}, {location[1]}, {location[2]}), False, False)\n"
    if rotation:
        code += f"actor.set_actor_rotation(unreal.Rotator({rotation[0]}, {rotation[1]}, {rotation[2]}), False)\n"
    if scale:
        code += f"actor.set_actor_scale3d(unreal.Vector({scale[0]}, {scale[1]}, {scale[2]}))\n"
    return ue.execute_python(code)


@mcp.tool()
def get_actor_info(name: str) -> dict:
    """Get detailed info about an actor."""
    return ue.execute_python(f"""
import unreal, json
actors = unreal.EditorLevelLibrary.get_all_level_actors()
for a in actors:
    if a.get_actor_label() == '{name}' or a.get_name() == '{name}':
        loc = a.get_actor_location()
        rot = a.get_actor_rotation()
        scl = a.get_actor_scale3d()
        result = json.dumps({{
            "name": a.get_name(),
            "label": a.get_actor_label(),
            "class": a.get_class().get_name(),
            "location": [loc.x, loc.y, loc.z],
            "rotation": [rot.pitch, rot.yaw, rot.roll],
            "scale": [scl.x, scl.y, scl.z],
        }})
        break
""")


@mcp.tool()
def list_actors(class_filter: str | None = None) -> dict:
    """List all actors in the level.

    Args:
        class_filter: Optional class name to filter by.
    """
    filter_code = ""
    if class_filter:
        filter_code = f"if a.get_class().get_name() == '{class_filter}':"
    else:
        filter_code = "if True:"

    return ue.execute_python(f"""
import unreal, json
actors = unreal.EditorLevelLibrary.get_all_level_actors()
info = []
for a in actors:
    {filter_code}
        info.append({{"name": a.get_name(), "label": a.get_actor_label(), "class": a.get_class().get_name()}})
result = json.dumps({{"actors": info, "count": len(info)}})
""")
