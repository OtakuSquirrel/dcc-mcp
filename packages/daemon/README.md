# dcc-daemon

Unified local daemon for agent → DCC control. One long-lived process is
the single entry point for both **local agents** (MCP over HTTP) and
**cloud agents** (outbound WebSocket tunnel, Phase 2), routing every
request down to a DCC instance through **one channel**:
`execute_python(port, code)`.

```
  local agent  ── MCP/HTTP  ─┐                        ┌─▶ Blender  (:19811)
  (Claude Code)              ├──▶  dcc-daemon  ────────┼─▶ Houdini  (:18811)
  cloud agent  ── WSS tunnel ┘   (this process,        └─▶ Unreal   (:20811)
  (Phase 2)                       routing + discovery)
                                                        TCP + newline JSON
```

Design tenet: **端口 + 命令解决一切** — port + command solves everything.
There are no per-operation tools. The agent sees ~4 meta-tools; all DCC
domain knowledge lives in **Skills** loaded on demand, never in tool
schemas (which would sit in the system prompt every turn).

## Meta-tools

| Tool | Purpose |
|------|---------|
| `list_instances(refresh=False)` | Discover running DCCs → `port`, `kind`, `version`, `pid`, `file` |
| `execute_python(port, code)` | The universal channel. Runs code in the DCC main thread; returns `result` |
| `health(port)` | OS-level verdict (healthy/busy/hung/no_protocol/dead) — never hangs |
| `screenshot(port)` | Grab viewport/render as an image the model can see |

## Run

```bash
dcc-daemon                       # serves MCP-over-HTTP on 127.0.0.1:8765/mcp
dcc-daemon --port 9000 --path /mcp
```

Point a local agent at it:

```json
{ "mcpServers": { "dcc": { "type": "http", "url": "http://127.0.0.1:8765/mcp" } } }
```

## Wire protocol (daemon ↔ DCC)

Every DCC plugin embeds the same minimal socket server
(`plugins/common/dcc_socket_server.py`) speaking newline-delimited JSON:

```
→ {"command": "execute_python", "params": {"code": "result = 1+1"}}
← {"result": 2}
→ {"command": "ping"}           ← {"result": "pong"}
→ {"command": "get_info"}       ← {"result": {"kind","version","pid","file"}}
→ {"command": "screenshot"}     ← {"result": {"png_base64": "..."}}
```

The only per-DCC difference is how code reaches the main thread
(`bpy.app.timers` / UE tick). The shared server takes a `run_on_main`
callable; everything else is identical across these DCCs.

## Adapters — one channel, two wires

`execute_python(port, code)` is protocol-agnostic. `TransportPool` picks
the adapter by the port's conventional DCC range, so callers never care
which wire is used:

| DCC | Range | Adapter | Wire |
|-----|-------|---------|------|
| Blender, Unreal | 19811–, 20811– | `JsonSocketAdapter` | newline JSON to the vendored socket plugin |
| Houdini | 18811– | `RpycAdapter` | RPyC classic to Houdini's built-in `hrpyc` |

Houdini stays on RPyC because it is **hot-pluggable** — start it from
Houdini's Python shell on an already-open session, no addon install:

```python
import hrpyc; hrpyc.start_server(port=18811)
```

The RPyC adapter teleports one self-contained helper that runs code on
the Houdini side and returns a JSON string, so only plain JSON values
cross the wire (no fragile netref proxies).

## Status

- **Phase 1 (done):** Python daemon, transport, instance discovery,
  health checks, MCP-over-HTTP ingress, Blender plugin, e2e tests.
- **Phase 2 (in progress):** Houdini via a hot-pluggable RPyC adapter
  (done — no plugin rebuild needed). Next: UE plugin adapter; daemon
  WebUI (monitor + plugin-install guides); outbound WSS reverse tunnel +
  relay + token auth for cloud agents. Ingress is already unified in
  `DaemonCore`, so cloud is "add a new door."
