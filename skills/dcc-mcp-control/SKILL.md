---
name: dcc-control
description: Control local DCC applications (Blender, Houdini, Unreal Engine, Maya, Tuanjie 团结引擎) through the dcc-daemon. Use this whenever the task involves creating, editing, inspecting, or rendering in a 3D DCC — modeling, materials, node graphs, animation, lighting, cameras, import/export, screenshots. You drive the DCC by sending code, not by calling many per-operation tools.
allowed-tools: 
disable: true
---

# Controlling DCCs via the daemon

You operate DCC applications through **one channel: `execute_python`**. The
daemon exposes only a handful of tools — you do the actual work by sending
code into the target DCC. There is **no** `create_cube` / `add_material` /
`render` tool; there is `bpy`, `hou`, `unreal`, `cmds`.

One exception to the name: **Tuanjie (团结引擎) scripts in C#, not Python** (it
has no embedded interpreter). For a `tuanjie` instance the same `execute_python`
channel carries **C# source**, which the connector compiles and runs; assign
to `result` exactly as elsewhere. Everything else — the tools, the loop, the
result contract — is identical. Treat this like a REPL attached to a live DCC.

## The only tools you have

| Tool | What it's for |
|------|---------------|
| `list_instances()` | Find running DCCs → each has an `instance_id` and `kind` |
| `execute_python(instance_id, code)` | **The workhorse.** Run code in that DCC (Python; C# for `tuanjie`) |
| `screenshot(instance_id)` | See the viewport/render as an image |
| `health(instance_id)` | Diagnose a stuck/frozen instance (never hangs) |

These four are the *entire* interface. `list_instances`, `screenshot`,
and `health` are infrastructure; **everything creative or inspective is
`execute_python`**. Do not look for other tools — write Python instead.

## Core loop

1. **Discover** — `list_instances()`; pick the `instance_id` whose `kind`
   matches the task (`blender` / `houdini` / `ue` / `maya` / `tuanjie`).
2. **Act** — `execute_python(instance_id, code)`. Return data by assigning to
   `result`:
   ```python
   result = [o.name for o in bpy.data.objects]   # comes back to you
   ```
3. **Verify** — `screenshot(instance_id)` to look, or another `execute_python`
   to read state back. Don't assume an edit worked; confirm it.

## Before writing DCC code — load the right reference

The DCC APIs differ. Read the one guide for the DCC you're driving; each
covers the execution model, what's in scope, the result/return contract,
and the traps that actually bite:

- Blender → [references/blender.md](references/blender.md)
- Houdini → [references/houdini.md](references/houdini.md)
- Unreal Engine → [references/unreal.md](references/unreal.md)
- Maya → [references/maya.md](references/maya.md)
- Tuanjie 团结引擎 (C#) → [references/tuanjie.md](references/tuanjie.md)

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
