# Unreal Engine — driving it with `execute_python`

Load this when the target `kind` is `ue`. You send Python that runs
inside the Unreal Editor with the full `unreal` API.

## Execution model

- Code runs on Unreal's **game thread** (the daemon plugin marshals it
  through a Slate post-tick callback), so `unreal` calls are safe and
  synchronous.
- **`unreal` is in scope automatically.** Import anything else inside
  the code.
- Return via `result`, JSON-safe only. Convert `unreal` objects: an
  actor's `get_actor_label()` or `get_name()`, a vector's components.
- Requires the Editor with the **Python Editor Script Plugin** enabled.
  Most `unreal` scripting APIs are editor-only.

## Minimal patterns

Level summary:
```python
import unreal
actors = unreal.EditorActorSubsystem().get_all_level_actors()
result = {
    "level": unreal.EditorLevelLibrary.get_editor_world().get_path_name(),
    "actor_count": len(actors),
    "sample": [a.get_actor_label() for a in actors[:10]],
}
```

Spawn an actor and capture its label:
```python
import unreal
loc = unreal.Vector(0, 0, 100)
actor = unreal.EditorActorSubsystem().spawn_actor_from_class(
    unreal.StaticMeshActor, loc, unreal.Rotator(0, 0, 0))
actor.set_actor_label("Widget")
result = actor.get_actor_label()
```

Assign a mesh asset (load assets by path via the asset registry):
```python
import unreal
mesh = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
actor = unreal.EditorActorSubsystem().spawn_actor_from_object(
    mesh, unreal.Vector(0, 0, 0))
result = actor.get_actor_label()
```

Prefer the modern **subsystems** over deprecated `EditorLevelLibrary`
free functions where both exist:
```python
import unreal
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
result = [a.get_actor_label() for a in eas.get_all_level_actors()]
```

## Traps that actually bite

- **Editor-only APIs.** Most scripting calls only work in the Editor,
  not in a packaged/PIE runtime. Assume Editor context.
- **Deprecation churn.** UE moved many `EditorLevelLibrary` /
  `EditorAssetLibrary` free functions onto subsystems
  (`EditorActorSubsystem`, `EditorAssetSubsystem`). If a call warns or
  is missing, try the subsystem form for your engine version.
- **Return plain data.** `unreal.Object` subclasses aren't
  JSON-serializable — return `get_actor_label()`, `get_name()`, path
  strings, or coordinate tuples.
- **Transactions/undo.** Editor edits may need an undo transaction to be
  clean; for scripted changes this is usually optional but be aware.
- **Asset paths** use the `/Game/...` and `/Engine/...` virtual roots,
  not OS paths.

## Screenshot

`screenshot(port)` issues a high-res screenshot of the active editor
viewport; the capture is queued for the next frame, so on the very first
call the file may not be ready yet — if you get an empty result, take it
again. For non-visual verification, read level/actor state back via
`execute_python`.

## Why UE uses the socket server (context)

UE also ships a "Python Remote Execution" feature, but it relies on UDP
multicast discovery and a reverse connection, which doesn't fit the
daemon's "scan a TCP port, connect to it" model. So UE embeds the same
socket-server plugin the other DCCs use; from your side it's identical
to Blender — just `execute_python` with `unreal` in scope.
