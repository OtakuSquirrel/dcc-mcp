# dcc-mcp

Unified local **daemon** for agent → DCC control (Blender, Houdini,
Unreal Engine). One long-lived process is the single entry point for
local agents (MCP over HTTP) and, later, cloud agents (outbound
WebSocket tunnel), routing every request down to a DCC instance through
one channel: `execute_python(port, code)`.

See [`packages/daemon/README.md`](packages/daemon/README.md) for the
full design, wire protocol, and status.

## Quick start

```bash
uv sync --extra dev          # create .venv, install the daemon
uv run dcc-daemon            # serve MCP-over-HTTP on 127.0.0.1:8765/mcp
```

Point a local agent at it:

```json
{ "mcpServers": { "dcc": { "type": "http", "url": "http://127.0.0.1:8765/mcp" } } }
```

## Layout

```
packages/daemon/        the daemon (transport, discovery, health, MCP-over-HTTP)
plugins/common/         DCC-agnostic socket server, vendored into each DCC
plugins/blender_daemon/ Blender addon wiring the socket server to bpy.app.timers
```

## Develop

```bash
uv run pytest packages/daemon/tests/    # e2e via an in-process fake DCC
uv run ruff check packages/ plugins/
```
