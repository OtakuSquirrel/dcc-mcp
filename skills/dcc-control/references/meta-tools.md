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

Returns a list of running DCCs discovered on the local machine:

```json
[{"port": 19811, "kind": "blender", "version": "4.2.0",
  "pid": 12345, "file": "scene.blend", "reachable": true}]
```

- `kind` ∈ `blender` | `houdini` | `ue` | `null` (unknown).
- `port` is what every other tool takes.
- `reachable: false` — a listener is on the port but didn't answer the
  identity probe (starting up, busy, or not our plugin).
- Results are cached ~3 s. Pass `refresh=True` to force a rescan (e.g.
  right after launching a DCC).

Always start here. Never hard-code a port you didn't get from this.

## `execute_python(port, code)`

Runs `code` inside the DCC on `port`, on that DCC's **main thread**,
with the DCC's Python API in scope. Returns:

```json
{"port": 19811, "result": <whatever you assigned to `result`>}
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
the real Python traceback from inside Blender/Houdini/UE. Fix and resend.
A transport failure (DCC crashed / port closed) surfaces as a connection
error; re-`list_instances()` to see if the instance is still alive.

### Timeouts

Long operations (renders, simulations, bakes) are fine — the call
returns when the DCC finishes, up to a generous ceiling (~10 min). If a
call is taking suspiciously long, call `health(port)` from the daemon's
perspective; it never hangs even when the DCC is frozen.

## `screenshot(port)`

Returns an image (PNG) of the DCC's viewport / latest render so you can
*see* the result. Use it to verify visual work — framing, materials,
lighting — that you can't confirm by reading state. The capture
mechanism is DCC-specific (see each DCC reference).

## `health(port)`

OS-level diagnosis that **never hangs**, even if the DCC is fully frozen.
Returns a verdict:

| verdict | meaning | what to do |
|---------|---------|------------|
| `healthy` | responsive | proceed |
| `busy` | main thread working (render/sim) or high CPU | wait, retry later |
| `hung` | unresponsive, low CPU | likely stuck; may need manual/kill |
| `no_protocol` | process alive, plugin port not answering | plugin not started/loaded |
| `dead` | nothing on the port | instance gone |
| `unknown` | port listening, PID undetermined | inspect manually |

Reach for this only when `execute_python` misbehaves — for normal work
you don't need it.

---

## Multi-instance

Several DCCs (even several of the same kind) can run at once, each on its
own port. The port is the address; the daemon keeps no "active" instance.
Track which port maps to which task in your own reasoning and pass it
explicitly every call.

## What you should NOT do

- Don't hunt for a per-operation tool — write Python.
- Don't return live DCC objects from `result` — return plain data.
- Don't rely on `print`; use `result`.
- Don't assume an edit succeeded — read it back or screenshot.
