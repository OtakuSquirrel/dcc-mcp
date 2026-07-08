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
(`bpy.app.timers` / `hdefereval` / UE tick). The shared server takes a
`run_on_main` callable; everything else is identical across DCCs.

## Status

- **Phase 1 (done):** Python daemon, unified TCP+JSON transport, instance
  discovery, health checks, MCP-over-HTTP ingress, Blender plugin adapter,
  e2e tests. RPyC retired — Houdini/UE plugins port to the shared server.
- **Phase 2 (planned):** outbound WSS reverse tunnel + relay + token auth
  for cloud agents; WebUI for monitoring & plugin-install guides. Ingress
  is already unified in `DaemonCore`, so this is "add a new door."
