# dcc-daemon

Unified local daemon for agent → DCC control. One long-lived process is
the MCP-over-HTTP entry point, routing requests to live DCC instances
through one universal Python channel:
`execute_python(instance_id, code)`.

```text
  local agent ── MCP/HTTP ──▶ dcc-daemon ◀── register ── Blender
                                  │         ├─ register ── Houdini
                                  │         ├─ register ── Unreal
                                  │         └─ register ── Maya
                                  └── live registry keyed by instance_id
```

DCC plugins dial the daemon's registration port, report their identity,
and hold the connection. The daemon assigns an `instance_id` such as
`blender-1`; it does not scan ports or select a transport from a DCC-specific
port range. All four DCCs use the same newline-delimited JSON protocol.

There are no per-operation tools. DCC domain knowledge lives in Skills,
while the daemon keeps its agent-facing surface small.

## Meta-tools

| Tool | Purpose |
|------|---------|
| `list_instances(refresh=False)` | List live DCCs and their `instance_id`, kind, version, pid, and file |
| `execute_python(instance_id, code)` | Run Python on the DCC main thread and return `result` |
| `health(instance_id)` | Return a healthy/busy/hung/dead verdict without hanging |
| `screenshot(instance_id)` | Capture the DCC viewport or render as an image |

`refresh` is retained for API compatibility but ignored because the
registration table is already live.

## Run

```bash
dcc-daemon                       # MCP: 127.0.0.1:18812/mcp, dashboard: /
dcc-daemon --port 9000 --path /mcp
```

Point a local MCP client at it:

```json
{ "mcpServers": { "dcc": { "type": "http", "url": "http://127.0.0.1:18812/mcp" } } }
```

The daemon also listens for DCC registrations on `127.0.0.1:18813` by
default. Both listen addresses can be configured in
`~/.dcc-mcp/config.toml`.

The dashboard includes four read-only/local-operations areas: registered
instances, a bounded in-memory log viewer, a preview-and-confirm DCC installer,
and daemon/configuration diagnostics. The installer currently supports a
Blender user add-on, Houdini Packages, and Maya Modules; it records a manifest
for verification and safe uninstall, and never writes during scanning. Data refreshes on initial
load or explicit user action; there is no periodic polling.

## Registration protocol

Every DCC embeds `plugins/common/dcc_socket_server.py`. On connection it
registers once, then receives tagged requests and returns tagged replies:

```text
DCC → daemon  {"type":"register","kind":"blender","pid":123,...}
daemon → DCC  {"type":"registered","instance_id":"blender-1"}
daemon → DCC  {"id":1,"command":"execute_python","params":{"code":"result=1+1"}}
DCC → daemon  {"id":1,"result":2}
```

The only per-DCC difference is its main-thread bridge:

| DCC | Main-thread bridge |
|-----|--------------------|
| Blender | `bpy.app.timers` + job queue |
| Houdini | `hdefereval.executeInMainThreadWithResult` |
| Unreal Engine | Slate post-tick callback + job queue |
| Maya | `maya.utils.executeInMainThreadWithResult` |

## Test

```bash
uv run pytest packages/daemon/tests/
uv run ruff check packages/ plugins/
```

The tests exercise registration and disconnect handling, all four DCC
kinds through protocol stand-ins, MCP core behavior, and WebUI APIs. Live
DCC APIs and viewport capture still require manual integration tests.
