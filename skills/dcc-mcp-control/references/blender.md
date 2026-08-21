# Blender — driving it with `execute_python`

Load this when the target `kind` is `blender`. You send Python that runs
inside Blender with the full `bpy` API.

## Execution model

- Code runs on Blender's **main thread** (the daemon plugin marshals it
  through `bpy.app.timers`), so `bpy` calls are safe and synchronous.
- In scope automatically: **`bpy`** and **`mathutils`**. Import anything
  else you need inside the code (`import bmesh`, `import math`).
- Return data via `result` (see meta-tools reference). JSON-safe only —
  convert vectors/objects: `list(obj.location)`, `obj.name`.

## Minimal patterns

Inspect the scene:
```python
result = {
    "objects": [(o.name, o.type) for o in bpy.data.objects],
    "active": getattr(bpy.context.active_object, "name", None),
    "frame": bpy.context.scene.frame_current,
}
```

Create and capture the real name (Blender auto-suffixes on collision):
```python
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
result = bpy.context.active_object.name   # e.g. "Cube" or "Cube.001"
```

Prefer `bpy.data` over `bpy.ops` when you can — it's order-independent
and doesn't depend on context/selection:
```python
mesh = bpy.data.meshes.new("m")
obj = bpy.data.objects.new("Widget", mesh)
bpy.context.collection.objects.link(obj)
result = obj.name
```

Set a material:
```python
mat = bpy.data.materials.new("Red")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (1, 0, 0, 1)
obj = bpy.data.objects["Widget"]
obj.data.materials.append(mat)
result = mat.name
```

Render to a file (then `screenshot(instance_id)` won't show a saved render —
read the file path back instead, or use the viewport):
```python
scene = bpy.context.scene
scene.render.filepath = "//out.png"     # // = .blend-relative
scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)
result = bpy.path.abspath(scene.render.filepath)
```

## Traps that actually bite

- **`bpy.ops` needs the right context.** Many operators act on the
  active object / selection / area. If an operator errors with a context
  message, set `bpy.context.view_layer.objects.active` and selection
  first, or switch to the `bpy.data` equivalent.
- **Names are unique and auto-suffixed.** Never assume the name you
  passed is the name you got — read `bpy.context.active_object.name`.
- **Units & rotation.** `rotation_euler` is radians. Locations are in
  scene units (usually metres).
- **Modes.** Some edits require Object vs Edit mode
  (`bpy.ops.object.mode_set(mode="OBJECT")`). `bmesh` edits need
  `bm.to_mesh(mesh)` + `mesh.update()` to commit.
- **Unsaved scene** shows as `file: "(unsaved)"` in `list_instances`.

## Screenshot

`screenshot(instance_id)` calls `bpy.ops.screen.screenshot` — it captures the
Blender **window/UI**, not a clean render. For a rendered image, render
to a file (above) and report the path; for framing/layout checks the
screenshot is fine.

## When unsure of an API

Blender's Python API is stable and well-known; write it directly. If you
need to discover attributes at runtime, introspect and return it:
```python
result = [m.name for m in bpy.data.objects["Widget"].modifiers]
```
