# Houdini — driving it with `execute_python`

Load this when the target `kind` is `houdini`. You send Python that runs
inside Houdini with the full `hou` API.

## Execution model

- Code runs on Houdini's **main thread** (the daemon plugin marshals it
  through `hdefereval.executeInMainThreadWithResult`), so `hou` calls are
  safe and synchronous.
- **`hou` is in scope automatically.** Import anything else inside the
  code as usual.
- Return via `result`, JSON-safe only. Convert `hou` objects: a node's
  `.path()`, a vector's `list(...)`, a parm's `.eval()`.
- Houdini uses the same socket-server plugin and the same JSON protocol
  as every other DCC — from your side it's identical to Blender.

## Minimal patterns

Scene summary:
```python
result = {
    "hip": hou.hipFile.path(),
    "fps": hou.fps(),
    "frame": hou.frame(),
    "obj_children": [n.path() for n in hou.node("/obj").children()],
}
```

Create nodes and wire them (capture real paths — Houdini auto-numbers):
```python
geo = hou.node("/obj").createNode("geo", "widget")
box = geo.createNode("box")
xf  = geo.createNode("xform")
xf.setInput(0, box)
xf.parm("tx").set(2)
geo.layoutChildren()
result = {"geo": geo.path(), "xform": xf.path()}
```

Read/write parameters:
```python
n = hou.node("/obj/widget/box")
n.parm("sizex").set(3)
result = {"sizex": n.parm("sizex").eval()}
```

Cook / detect errors (Houdini defers cooking; force it and report):
```python
n = hou.node("/obj/widget/xform")
n.cook(force=True)
result = {"errors": n.errors(), "warnings": n.warnings()}
```

Inspect geometry:
```python
geo = hou.node("/obj/widget/box").geometry()
result = {
    "npoints": len(geo.points()),
    "nprims": len(geo.prims()),
    "point_attribs": [a.name() for a in geo.pointAttribs()],
}
```

## Traps that actually bite

- **Cooking is lazy.** Setting a parm doesn't recompute geometry until
  something cooks. Call `node.cook(force=True)` before reading results
  you expect to have changed, and check `node.errors()`.
- **Node names auto-increment** (`box1`, `box2`). Use the object
  returned by `createNode(...)`, capture `.path()`, and re-fetch by path
  in later calls — don't assume the name.
- **Contexts/categories.** Nodes only create inside a compatible parent
  (SOPs inside a `geo`, DOPs inside a `dopnet`, etc.). Create the
  container first.
- **Each call is independent.** Don't rely on Python variables persisting
  between `execute_python` calls; re-fetch nodes with `hou.node("<path>")`.
- **Parms are typed.** `.set()` accepts the matching type; `.eval()`
  returns the evaluated value (channels/expressions resolved).

## Screenshot

`screenshot(instance_id)` uses the Scene Viewer flipbook to grab the viewport.
It needs a running Houdini **GUI** with a Scene Viewer pane — on a
headless/batch Houdini it will error. For headless verification, read
geometry stats back via `execute_python` instead.

## Starting the plugin (context, not something you do)

Houdini's side is the same socket-server plugin as the other DCCs, wired
to the main thread via `hdefereval`. A human starts it (from a startup
script or the Python Shell); it dials the daemon's registration port and
receives an `instance_id`. If `list_instances` doesn't show a Houdini you
expect, its plugin may not be started or connected yet.
