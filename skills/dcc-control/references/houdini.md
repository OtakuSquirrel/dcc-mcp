# Houdini — driving it with `execute_python`

Load this when the target `kind` is `houdini`. You send Python that runs
inside Houdini with the full `hou` API.

## Execution model (important — differs from Blender/UE)

- Houdini is reached over **RPyC**, not the socket-server plugin. The
  daemon teleports a small helper that runs your code inside Houdini and
  returns the result as JSON.
- **`hou` is in scope automatically.** Import anything else inside the
  code as usual.
- Return via `result`, JSON-safe only. Convert `hou` objects: a node's
  `.path()`, a vector's `list(...)`, a parm's `.eval()`.
- Because only JSON crosses the wire (not live netref proxies), you
  cannot hold a `hou.Node` across calls — re-fetch it by path each time:
  `hou.node("/obj/geo1")`.

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
- **No persistent references.** Every call is a fresh teleport; a node
  handle from a previous call is gone. Always `hou.node("<path>")`.
- **Parms are typed.** `.set()` accepts the matching type; `.eval()`
  returns the evaluated value (channels/expressions resolved).

## Screenshot

`screenshot(port)` uses the Scene Viewer flipbook to grab the viewport.
It needs a running Houdini **GUI** with a Scene Viewer pane — on a
headless/batch Houdini it will error. For headless verification, read
geometry stats back via `execute_python` instead.

## Hot-plugging the server (context, not something you do)

Houdini's side is started by a human running
`import hrpyc; hrpyc.start_server(port=18811)` in Houdini's Python shell
— no addon install. If `list_instances` doesn't show a Houdini you
expect, that server may not be started yet.
