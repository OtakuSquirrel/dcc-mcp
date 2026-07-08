# Meta-tools reference

The daemon's entire agent-facing surface. Load this when you need exact
semantics: the `execute_python` contract, error shapes, addressing, and
when to reach for `health`/`screenshot`.

## Why so few tools

The daemon deliberately exposes ~4 tools instead of a large catalogue.
DCC APIs are huge and change per version; a fixed tool per operation
would bloat the prompt and still lag the API. Instead the daemon gives
you a **Python channel** into each DCC and lets you use the real API.
Domain know-how lives in per-DCC references, loaded on demand — not in
tool schemas.

---

## `list_instances(refresh=False)`

Returns the DCCs currently registered with the daemon:

```json
[{"instance_id": "blender-1", "kind": "blender", "version": "4.2.0",
  "pid": 12345, "file": "scene.blend", "connected": true}]
```

- `kind` ∈ `blender` | `houdini` | `ue` | `maya` | `null` (unknown).
- `instance_id` is the handle every other tool takes (e.g. `blender-1`).
- `connected: false` — the registration exists but its connection just
  dropped; treat as gone.
- `refresh` is ignored — the registry is always live (DCCs dial in and
  hold a connection), so there is nothing to re-scan.

Always start here. Never hard-code an `instance_id` you didn't get from
this — ids are assigned by the daemon and change between runs.

## `execute_python(instance_id, code)`

Runs `code` inside the DCC `instance_id`, on that DCC's **main thread**,
with the DCC's Python API in scope. Returns:

```json
{"instance_id": "blender-1", "result": <whatever you assigned to `result`>}
```

### The result contract

- Assign to a variable named **`result`** to send a value back. No
  assignment → `result` is `null`.
- The value must be **JSON-serializable** (str/num/bool/list/dict/None).
  Anything else is returned as its `repr()` string — so convert before
  returning: send `obj.name`, `list(vec)`, `[o.name for o in …]`, not
  the live object.
- `print(...)` output is **not** captured. Use `result`, not prints.

```python
# good — returns structured, checkable data
result = {"objects": [o.name for o in bpy.data.objects],
          "active": bpy.context.active_object.name}
```

### Errors

If the code raises inside the DCC, the tool call fails with the
exception message and a traceback from the DCC process — read it, it's
the real Python traceback from inside Blender/Houdini/UE/Maya. Fix and
resend. A transport failure (DCC disconnected) surfaces as a connection
error; re-`list_instances()` to see if the instance is still there.

### Timeouts

Long operations (renders, simulations, bakes) are fine — the call
returns when the DCC finishes, up to a generous ceiling (~10 min). If a
call is taking suspiciously long, call `health(instance_id)` from the
daemon's perspective; it never hangs even when the DCC is frozen.

## `screenshot(instance_id)`

Returns an image (PNG) of the DCC's viewport / latest render so you can
*see* the result. Use it to verify visual work — framing, materials,
lighting — that you can't confirm by reading state. The capture
mechanism is DCC-specific (see each DCC reference).

## `health(instance_id)`

Diagnosis that **never hangs**, even if the DCC is fully frozen. Combines
the live connection state with a **main-thread heartbeat** (a frozen DCC
keeps its socket open, so only a main-thread ping reveals the freeze) and
OS window/CPU signals. Returns a verdict:

| verdict | meaning | what to do |
|---------|---------|------------|
| `healthy` | connected + main thread answered | proceed |
| `busy` | connected but main thread not answering; high CPU or briefly blocked | wait, retry later |
| `hung` | connected, main thread silent, window not responding | likely stuck; may need manual/kill |
| `dead` | no live registration | instance gone |
| `unknown` | indeterminate | inspect manually |

Reach for this only when `execute_python` misbehaves — for normal work
you don't need it.

---

## Multi-instance

Several DCCs (even several of the same kind) can be registered at once,
each with its own `instance_id` (`blender-1`, `blender-2`, …). The id is
the address; the daemon keeps no "active" instance. Track which id maps
to which task in your own reasoning and pass it explicitly every call.

## What you should NOT do

- Don't hunt for a per-operation tool — write Python.
- Don't return live DCC objects from `result` — return plain data.
- Don't rely on `print`; use `result`.
- Don't assume an edit succeeded — read it back or screenshot.
