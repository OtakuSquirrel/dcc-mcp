"""Level management tools for UE."""

from __future__ import annotations

from ue_mcp.server import mcp, ue


@mcp.tool()
def new_level(name: str = "NewLevel") -> dict:
    """Create a new empty level.

    Args:
        name: Level name.
    """
    result = ue.execute_python(f"""
import unreal
unreal.EditorLevelLibrary.new_level('/Game/Maps/{name}')
result = '{name}'
""")
    return {"name": name, "output": result.get("output", "")}


@mcp.tool()
def open_level(path: str) -> dict:
    """Open a level by asset path.

    Args:
        path: Level asset path (e.g. '/Game/Maps/MyLevel').
    """
    return ue.execute_python(f"import unreal; unreal.EditorLevelLibrary.load_level('{path}')")


@mcp.tool()
def save_level() -> dict:
    """Save the current level."""
    return ue.execute_python("import unreal; unreal.EditorLevelLibrary.save_current_level()")


@mcp.tool()
def get_level_info() -> dict:
    """Get level actors and settings."""
    return ue.execute_python("""
import unreal, json
actors = unreal.EditorLevelLibrary.get_all_level_actors()
info = [{"name": a.get_name(), "class": a.get_class().get_name()} for a in actors[:100]]
result = json.dumps({"actors": info, "count": len(actors)})
""")
