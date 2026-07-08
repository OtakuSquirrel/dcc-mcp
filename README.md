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
- **Downward**, DCCs dial the daemon and register; it keeps a live table
  and pushes work to them over one uniform protocol.

```
  agent ── MCP / HTTP ──▶  dcc-daemon  ◀── register ── Blender  ┐
  (Claude Code)            (guardian)  ◀── register ── Houdini  │ DCCs dial IN
                                       ◀── register ── Unreal   │ and hold a
                                       ◀── register ── Maya     ┘ connection
```

## Why it is built this way

**One channel instead of many tools.** The agent is given ~4 meta-tools,
not a catalogue of per-operation tools. Everything — modeling, materials,
nodes, rendering, import/export, inspection — is done by sending Python
to the DCC via `execute_python(instance_id, code)`. DCC-specific know-how
(bpy / hou / unreal / cmds recipes) lives in agent **Skills** loaded on
demand, so the system prompt stays small and the tool surface doesn't
grow with the API.

**All DCCs are equal; the `instance_id` is the only address.** A caller
names an instance and sends code. DCCs are transparent — the agent
doesn't know or care which DCC is which; it asks `list_instances` which
returns each `instance_id` + self-reported kind/process, and drives it.
To make an agent work with a given DCC you pre-configure the matching
**skill**, not the daemon.

**DCCs register; the daemon doesn't scan.** Each DCC dials the daemon on
launch and holds one connection. So the daemon has a **live registry** —
`list_instances` is a memory read, death detection is free (socket
closes), and the pid arrives at registration (no port-scraping). This is
the same inversion the cloud tunnel uses (dial out, hold, push down).

**A daemon, not a spawned subprocess.** Long-lived and process-
independent, it serves several agents at once and accepts remote agents
over an outbound tunnel — all through the same routing code. Discovery
and health queries (constant during connect/reconnect) are answered by
this one resident process.

## Meta-tools (agent-facing)

| Tool | Purpose |
|------|---------|
| `list_instances()` | List registered DCCs → `instance_id`, `kind`, `version`, `pid`, `file`, `connected` |
| `execute_python(instance_id, code)` | The universal channel — run Python in the DCC, return what it sets as `result` |
| `screenshot(instance_id)` | Grab the viewport/render as an image the model can see |
| `health(instance_id)` | Verdict (healthy/busy/hung/dead) via a main-thread heartbeat — never hangs |

## One protocol, registration model

Every DCC embeds the same minimal connector
(`plugins/common/dcc_socket_server.py`) and speaks newline-delimited
JSON. On launch it **dials the daemon's register port** (default 8766),
sends its identity, and holds the connection; the daemon assigns an
`instance_id` and pushes requests down it. No listening port per DCC, no
scanning — the plugin self-reports its `kind`, and a dropped socket means
the instance is gone.

The only per-DCC difference is how code hops to the main thread (the DCC
APIs are not thread-safe):

| DCC | Main-thread bridge |
|-----|--------------------|
| Blender | `bpy.app.timers` + job queue |
| Unreal | `register_slate_post_tick_callback` + job queue |
| Houdini | `hdefereval.executeInMainThreadWithResult` |
| Maya | `maya.utils.executeInMainThreadWithResult` |

The shared connector takes a `run_on_main` callable; everything else is
identical. (Houdini previously used RPyC/`hrpyc`; it was unified onto the
same connector so all four share one protocol and the daemon needs no
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
edit it later). DCCs dial the daemon, so there's no port pool — just the
two ports the daemon listens on:

```toml
[daemon]
host = "127.0.0.1"
port = 8765               # MCP-over-HTTP for agents
dcc_register_port = 8766  # DCCs dial here to register
```

Missing/malformed file → built-in defaults, so a fresh machine just works.

## Layout

```
packages/daemon/            the daemon (guardian)
  dcc_daemon/
    core.py                 DaemonCore — owns the registration hub
    hub.py                  RegistrationHub — accepts DCC registrations, routes requests by id
    config.py               reads ~/.dcc-mcp/config.toml (the two listen ports)
    health.py               liveness + main-thread heartbeat; never hangs
    mcp_server.py           the 4 meta-tools over MCP/HTTP
    webui/                  monitoring dashboard (mounted on the MCP app)
    tunnel/                 cloud reverse tunnel: protocol + relay + client + tokens
    app.py                  builds the ASGI app (MCP + WebUI); starts the hub
    __main__.py             `dcc-daemon` entry point
    relay_main.py           `dcc-relay` entry point
  tests/                    tests against real protocol stand-ins
plugins/common/             DCC-agnostic connector (dials + registers), vendored per DCC
plugins/blender_daemon/     Blender addon (bpy.app.timers bridge)
plugins/houdini_daemon/     Houdini plugin (hdefereval bridge)
plugins/ue_daemon/          Unreal script (slate post-tick bridge)
plugins/maya_daemon/        Maya plugin (executeInMainThreadWithResult bridge)
skills/dcc-control/         agent skill: how to drive DCCs via execute_python (SKILL.md + references/)
docs/                       plugin-install guide; registration-model + tunnel-hardening notes
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

- `tests/test_e2e.py` — a real `DCCServer` from `plugins/common/` dials a
  real `RegistrationHub` over loopback and registers, parametrized over
  all four DCC kinds. Covers register/execute/inspect/health/screenshot
  and error propagation.
- `tests/test_webui.py` — the dashboard + JSON APIs via Starlette's
  TestClient.
- `tests/test_tunnel.py` — the real relay + daemon tunnel client + a
  registered fake DCC + an agent, over loopback WebSockets: token auth
  (accept + reject) and a full agent→relay→daemon→DCC round-trip with
  error propagation.

```bash
uv run pytest packages/daemon/tests/   # 39 tests
uv run ruff check packages/ plugins/
```

What this does **not** cover — real bpy/hou/unreal/cmds API calls,
main-thread timing inside a live DCC, and actual viewport capture — is
verified manually against running DCCs.

## Status

- **Done:** guardian daemon; registration model (DCCs dial in, live
  registry, free death detection); one JSON protocol across Blender,
  Houdini, Unreal, Maya; main-thread-heartbeat health; MCP-over-HTTP
  ingress; monitoring WebUI; outbound WebSocket tunnel + relay + token
  auth for remote agents; tests.
- **Next:** one-click install + autostart; plugin-install UI in the WebUI;
  DCC-side skill packaging for cloud agents; hardening the tunnel (rate
  limits, token rotation) for real deployment.

## License

MIT
