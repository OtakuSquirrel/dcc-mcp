# dcc-mcp

A local daemon that lets AI agents drive DCC applications — **Blender**,
**Houdini**, **Unreal Engine**, **Maya** — by sending Python to them over
a single, uniform channel.

## What it is

One long-lived process (`dcc-daemon`) — the **guardian** — runs on the
machine where the DCCs run. It is the single entry point between agents
and DCCs:

- **Upward**, it speaks MCP over HTTP, so any local agent (Claude Code,
  etc.) connects with a URL — no per-agent child process.
- **Downward**, it discovers running DCC instances by port and forwards
  work to them over one uniform protocol.

```
  agent ── MCP / HTTP ──▶  dcc-daemon  ──┬── JSON/TCP ──▶ Blender   ┐
  (Claude Code)            (guardian)    ├── JSON/TCP ──▶ Houdini   │ one port pool
                                         ├── JSON/TCP ──▶ Unreal    │ (e.g. 18811-18820)
                                         └── JSON/TCP ──▶ Maya      ┘
```

## Why it is built this way

**One channel instead of many tools.** The agent is given ~4 meta-tools,
not a catalogue of per-operation tools. Everything — modeling, materials,
nodes, rendering, import/export, inspection — is done by sending Python
to the DCC via `execute_python(port, code)`. DCC-specific know-how (bpy /
hou / unreal / cmds recipes) lives in agent **Skills** loaded on demand,
so the system prompt stays small and the tool surface doesn't grow with
the API.

**All DCCs are equal; the port is the only address.** A caller names a
port and sends code. DCCs are transparent — the agent doesn't know or
care which DCC is on a port; it asks `list_instances` which returns the
port + self-reported kind/process, and drives it. To make an agent work
with a given DCC you pre-configure the matching **skill**, not the daemon.

**A daemon, not a spawned subprocess.** Because it is long-lived and
process-independent, it can serve several agents at once and accept
remote agents over an outbound tunnel — all through the same routing
code. Discovery and health queries (needed constantly when an agent
connects/reconnects) are answered by this one resident process.

## Meta-tools (agent-facing)

| Tool | Purpose |
|------|---------|
| `list_instances(refresh=False)` | Discover running DCCs → `port`, `kind`, `version`, `pid`, `file` |
| `execute_python(port, code)` | The universal channel — run Python in the DCC, return what it sets as `result` |
| `screenshot(port)` | Grab the viewport/render as an image the model can see |
| `health(port)` | OS-level verdict (healthy/busy/hung/no_protocol/dead) — never hangs |

## One protocol, one port pool

Every DCC embeds the same minimal socket server
(`plugins/common/dcc_socket_server.py`) and speaks newline-delimited
JSON. On launch a plugin scans the configured **port pool**, claims the
first free port, and listens; the daemon scans the same pool to discover
what's running. The port carries no meaning — the plugin self-reports its
`kind` via `get_info`.

The only per-DCC difference is how code hops to the main thread (the DCC
APIs are not thread-safe):

| DCC | Main-thread bridge |
|-----|--------------------|
| Blender | `bpy.app.timers` + job queue |
| Unreal | `register_slate_post_tick_callback` + job queue |
| Houdini | `hdefereval.executeInMainThreadWithResult` |
| Maya | `maya.utils.executeInMainThreadWithResult` |

The shared server takes a `run_on_main` callable; everything else is
identical. (Houdini previously used RPyC/`hrpyc`; it was unified onto the
socket server so all four share one protocol and the daemon needs no
per-DCC special case.)

## Quick start

```bash
uv sync --extra dev          # create .venv, install the daemon
uv run dcc-daemon            # serve MCP-over-HTTP on 127.0.0.1:8765/mcp
```

Point a local agent at it:

```json
{ "mcpServers": { "dcc": { "type": "http", "url": "http://127.0.0.1:8765/mcp" } } }
```

## Configuration

One file, `~/.dcc-mcp/config.toml`, exposed for the user (a WebUI can
edit it later). The key setting is the DCC port pool:

```toml
[ports]
dcc = [18811, 18812, 18813, 18814, 18815, 18816, 18817, 18818, 18819, 18820]
# or a range:  min = 18811 \n max = 18830

[daemon]
host = "127.0.0.1"
port = 8765
```

Missing/malformed file → built-in defaults, so a fresh machine just works.

## Layout

```
packages/daemon/            the daemon (guardian)
  dcc_daemon/
    core.py                 DaemonCore — owns the pool + registry
    transport.py            TransportPool — one JSON adapter for every DCC
    adapters/               base + json_socket (all DCCs)
    config.py               reads ~/.dcc-mcp/config.toml (the port pool)
    registry.py             discovers live instances by scanning the pool
    health.py               OS-level, never-hangs health checks
    mcp_server.py           the 4 meta-tools over MCP/HTTP
    webui/                  monitoring dashboard (mounted on the MCP app)
    tunnel/                 cloud reverse tunnel: protocol + relay + client + tokens
    app.py                  builds the ASGI app (MCP + WebUI)
    __main__.py             `dcc-daemon` entry point
    relay_main.py           `dcc-relay` entry point
  tests/                    tests against real protocol stand-ins
plugins/common/             DCC-agnostic socket server (+ port-claiming), vendored per DCC
plugins/blender_daemon/     Blender addon (bpy.app.timers bridge)
plugins/houdini_daemon/     Houdini plugin (hdefereval bridge)
plugins/ue_daemon/          Unreal script (slate post-tick bridge)
plugins/maya_daemon/        Maya plugin (executeInMainThreadWithResult bridge)
skills/dcc-control/         agent skill: how to drive DCCs via execute_python (SKILL.md + references/)
docs/                       plugin-install guide; tunnel-hardening notes
```

## Remote agents (cloud tunnel)

A home daemon behind NAT has no public IP and opens no ports. To let a
remote agent reach it, both the daemon and the agent dial **out** to a
relay you deploy; the relay pairs them by `daemon_id` and forwards frames.
It executes nothing.

```
 cloud agent ──WSS(access_token)──▶  relay  ◀──WSS(pair_token)── home daemon ─▶ DCCs
```

```bash
# On the relay host (public):
dcc-relay add-daemon --tokens tokens.json           # -> daemon_id + pair_token
dcc-relay add-agent  --tokens tokens.json --daemon-id dccbox-...  # -> access_token
dcc-relay serve      --tokens tokens.json --certfile … --keyfile …

# On the home machine:
dcc-daemon --relay-url wss://relay.example/ --daemon-id dccbox-... --pair-token …
```

The agent side needs only the `daemon_id` + `access_token`. Two token
types: `pair_token` authenticates a daemon to the relay; `access_token`
authorizes an agent for one daemon. Both compared with `hmac.compare_digest`.

## Testing

Tests cannot launch real DCCs, so they **stand in the DCC end with the
real protocol**, exercising the daemon's actual code paths:

- `tests/test_e2e.py` — runs the real `DCCServer` from `plugins/common/`
  over a real TCP socket, parametrized over all four DCC kinds (all one
  JSON protocol now). Covers execute/inspect/health/screenshot/discovery
  and error propagation.
- `tests/test_claim_port.py` — the plugin's port-claiming: skips a taken
  port, grabs the next free one, errors on an exhausted pool.
- `tests/test_webui.py` — the dashboard + JSON APIs via Starlette's
  TestClient.
- `tests/test_tunnel.py` — the real relay + daemon tunnel client + a fake
  DCC + an agent, over loopback WebSockets: token auth (accept + reject)
  and a full agent→relay→daemon→DCC round-trip with error propagation.

```bash
uv run pytest packages/daemon/tests/   # 43 tests
uv run ruff check packages/ plugins/
```

What this does **not** cover — real bpy/hou/unreal/cmds API calls,
main-thread timing inside a live DCC, and actual viewport capture — is
verified manually against running DCCs.

## Status

- **Done:** guardian daemon; one JSON protocol across Blender, Houdini,
  Unreal, Maya; port-pool config + plugin port-claiming; instance
  discovery; health checks; MCP-over-HTTP ingress; monitoring WebUI;
  outbound WebSocket tunnel + relay + token auth for remote agents; tests.
- **Next:** one-click install + autostart; plugin-install UI in the WebUI;
  DCC-side skill packaging for cloud agents; hardening the tunnel (rate
  limits, token rotation) for real deployment.

## License

MIT
