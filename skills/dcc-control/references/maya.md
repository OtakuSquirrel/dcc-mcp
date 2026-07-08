# Maya — driving it with `execute_python`

Load this when the target `kind` is `maya`. You send Python that runs
inside Maya with the full `cmds` (and `maya.api.OpenMaya`) API.

## Execution model

- Code runs on Maya's **main thread** (the daemon plugin marshals it
  through `maya.utils.executeInMainThreadWithResult`), so `cmds` calls
  are safe and synchronous.
- In scope automatically: **`cmds`** (`maya.cmds`), **`mel`**
  (`maya.mel`), **`om`** (`maya.api.OpenMaya`). Import anything else
  inside the code.
- Return via `result`, JSON-safe only. Maya `cmds` mostly returns plain
  strings/lists already, which is convenient.
- Requires **interactive GUI Maya** (the editor). Batch `mayapy` has no
  idle loop and the main-thread bridge is unavailable there.

## Minimal patterns

Scene summary:
```python
result = {
    "scene": cmds.file(query=True, sceneName=True) or "(unsaved)",
    "selection": cmds.ls(selection=True) or [],
    "mesh_count": len(cmds.ls(type="mesh") or []),
}
```

Create and capture the real name (Maya returns the actual name):
```python
name = cmds.polyCube(name="widget")[0]   # e.g. "widget" or "widget1"
cmds.move(0, 1, 0, name)
result = name
```

Query/set attributes:
```python
cmds.setAttr("widget.translateY", 5)
result = cmds.getAttr("widget.translateY")
```

Assign a material (Maya's shading-group dance):
```python
shader = cmds.shadingNode("lambert", asShader=True, name="redMat")
cmds.setAttr(shader + ".color", 1, 0, 0, type="double3")
sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
cmds.sets("widget", edit=True, forceElement=sg)
result = shader
```

Use the OpenMaya API when `cmds` is awkward:
```python
import maya.api.OpenMaya as om
sel = om.MSelectionList(); sel.add("widget")
dag = sel.getDagPath(0)
result = str(dag.fullPathName())
```

## Traps that actually bite

- **Names vs full paths.** Duplicate short names are disambiguated by DAG
  path (`|group1|widget`). If a short name is ambiguous, use the full
  path Maya returns; capture the name from the create command.
- **`cmds` returns the created name** — use it; don't assume your
  requested name survived (`widget` → `widget1` on collision).
- **Materials need a shading group**, not just a shader — connect the
  shader to an `SG` set and assign the SG to the object (above).
- **Units.** Default linear unit is centimetres, angular is degrees —
  check `cmds.currentUnit(query=True, linear=True)` if precision matters.
- **Undo.** Scripted changes go on the undo queue; large batches can bloat
  it. Wrap in `cmds.undoInfo(openChunk=True)` / `closeChunk=True` if you
  want them collapsed, but it's usually optional.

## Screenshot

`screenshot(port)` does a single-frame `playblast` of the active viewport
to a PNG. It needs the GUI viewport; on headless Maya it won't work. For
non-visual checks, read scene state back via `execute_python`.

## Note on `commandPort`

Maya has a built-in `commandPort`, but the daemon does **not** use it —
it embeds the same socket-server plugin as the other DCCs, so Maya speaks
the identical JSON protocol. From your side it's just `execute_python`
with `cmds` in scope.
