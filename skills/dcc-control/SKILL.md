---
name: dcc-control
description: Control local DCC applications (Blender, Houdini, Unreal Engine, Maya) through the dcc-daemon. Use this whenever the task involves creating, editing, inspecting, or rendering in a 3D DCC — modeling, materials, node graphs, animation, lighting, cameras, import/export, screenshots. You drive the DCC by sending Python, not by calling many per-operation tools.
---

# Controlling DCCs via the daemon

You operate DCC applications through **one channel: Python**. The daemon
exposes only a handful of tools — you do the actual work by sending
Python code into the target DCC with `execute_python`. There is **no**
`create_cube` / `add_material` / `render` tool; there is `bpy`, `hou`,
and `unreal`. Treat this like a Python REPL attached to a live DCC.

## The only tools you have

| Tool | What it's for |
|------|---------------|
| `list_instances()` | Find running DCCs → each has a `port` and `kind` |
| `execute_python(port, code)` | **The workhorse.** Run Python in that DCC |
| `screenshot(port)` | See the viewport/render as an image |
| `health(port)` | Diagnose a stuck/frozen instance (never hangs) |

These four are the *entire* interface. `list_instances`, `screenshot`,
and `health` are infrastructure; **everything creative or inspective is
`execute_python`**. Do not look for other tools — write Python instead.

## Core loop

1. **Discover** — `list_instances()`; pick the `port` whose `kind`
   matches the task (`blender` / `houdini` / `ue` / `maya`).
2. **Act** — `execute_python(port, code)`. Return data by assigning to
   `result`:
   ```python
   result = [o.name for o in bpy.data.objects]   # comes back to you
   ```
3. **Verify** — `screenshot(port)` to look, or another `execute_python`
   to read state back. Don't assume an edit worked; confirm it.

## Before writing DCC code — load the right reference

The DCC APIs differ. Read the one guide for the DCC you're driving; each
covers the execution model, what's in scope, the result/return contract,
and the traps that actually bite:

- Blender → [references/blender.md](references/blender.md)
- Houdini → [references/houdini.md](references/houdini.md)
- Unreal Engine → [references/unreal.md](references/unreal.md)
- Maya → [references/maya.md](references/maya.md)

For the exact tool semantics — the `execute_python` result contract,
error shapes, timeouts, multi-instance addressing — see
[references/meta-tools.md](references/meta-tools.md).

## Rules of thumb

- **Prefer small, checkable steps.** Send code that returns a value you
  can verify over a big blind batch.
- **Idempotence & names.** Objects/nodes get auto-suffixed on collision
  (`Cube.001`). Capture the created name in `result` rather than assuming.
- **Main-thread cost.** Each call runs on the DCC's main thread and
  blocks its UI briefly. Batch related work into one `execute_python`
  instead of many chatty round-trips.
- **Long ops (renders, sims) can take a while.** That's expected; the
  call returns when the DCC finishes. If it seems hung, use `health`.
