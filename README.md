# dcc-mcp

A local daemon that lets AI agents drive DCC applications — **Blender**,
**Houdini**, **Unreal Engine** — by sending Python to them over a single,
uniform channel.

## What it is

One long-lived process (`dcc-daemon`) runs on the machine where the DCCs
run. It is the single entry point between agents and DCCs:

- **Upward**, it speaks MCP over HTTP, so any local agent (Claude Code,
  etc.) connects with a URL — no per-agent child process.
- **Downward**, it discovers running DCC instances by port and forwards
  work to them, hiding whatever wire protocol each DCC happens to use.

```
  agent ── MCP / HTTP ──▶  dcc-daemon  ──┬── JSON/TCP ──▶ Blender   (:19811+)
  (Claude Code)            (this process) ├── JSON/TCP ──▶ Unreal    (:20811+)
                                          └── RPyC ──────▶ Houdini   (:18811+)
```

## Why it is built this way

**One channel instead of many tools.** The agent is given ~4 meta-tools,
not a catalogue of per-operation tools. Everything — modeling, materials,
nodes, rendering, import/export, inspection — is done by sending Python
to the DCC via `execute_python(port, code)`. DCC-specific know-how (bpy /
hou / unreal recipes) lives in agent **Skills** loaded on demand, so the
system prompt stays small and the tool surface does not grow with the API.

**The port identifies the instance; the protocol is invisible.** A caller
names a port and sends code. Which wire carries it is decided internally
by the port's range, so adding or changing a DCC's transport never
changes the agent-facing contract.

**A daemon, not a spawned subprocess.** Because it is long-lived and
process-independent, it can serve several agents at once and — in a
later phase — accept remote agents over an outbound tunnel, all through
the same routing code.

## Meta-tools (agent-facing)

| Tool | Purpose |
|------|---------|
| `list_instances(refresh=False)` | Discover running DCCs → `port`, `kind`, `version`, `pid`, `file` |
| `execute_python(port, code)` | The universal channel — run Python in the DCC, return what it sets as `result` |
| `screenshot(port)` | Grab the viewport/render as an image the model can see |
| `health(port)` | OS-level verdict (healthy/busy/hung/no_protocol/dead) — never hangs |

## Transport adapters

`execute_python` is protocol-agnostic. `TransportPool` picks the adapter
from the port's conventional range:

| DCC | Port range | Adapter | Wire |
|-----|-----------|---------|------|
| Blender, Unreal | 19811+, 20811+ | `JsonSocketAdapter` | newline-delimited JSON to a vendored socket-server plugin |
| Houdini | 18811+ | `RpycAdapter` | RPyC classic to Houdini's built-in `hrpyc` |

Blender and Unreal embed the same minimal socket server
(`plugins/common/dcc_socket_server.py`); the only per-DCC difference is
how code hops to the main thread (`bpy.app.timers` for Blender). Houdini
stays on RPyC because `hrpyc` is **hot-pluggable** — started from
Houdini's Python shell on a live session, no addon install:

```python
import hrpyc; hrpyc.start_server(port=18811)
```

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
packages/daemon/            the daemon
  dcc_daemon/
    core.py                 DaemonCore — owns the pool + registry
    transport.py            TransportPool — routes a port to its adapter
    adapters/               base + json_socket (Blender/UE) + rpyc (Houdini)
    registry.py             discovers live instances by scanning ports
    health.py               OS-level, never-hangs health checks
    mcp_server.py           the 4 meta-tools over MCP/HTTP
    webui/                  monitoring dashboard (mounted on the MCP app)
    tunnel/                 cloud reverse tunnel: protocol + relay + client + tokens
    app.py                  builds the ASGI app (MCP + WebUI)
    __main__.py             `dcc-daemon` entry point
    relay_main.py           `dcc-relay` entry point
  tests/                    e2e tests against real protocol stand-ins
plugins/common/             DCC-agnostic socket server, vendored per DCC
plugins/blender_daemon/     Blender addon wiring the socket server to bpy
plugins/ue_daemon/          Unreal script wiring the socket server to the game thread
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
  over a real TCP socket, parametrized over Blender- and UE-range ports.
  Covers the JSON path for both.
- `tests/test_rpyc_adapter.py` — runs a real `rpyc.classic` slave on a
  Houdini-range port. Covers the Houdini (RPyC) path, including the
  no-`hou` graceful-degradation case.
- `tests/test_webui.py` — the dashboard + JSON APIs via Starlette's
  TestClient.
- `tests/test_tunnel.py` — the real relay + daemon tunnel client + a fake
  DCC + an agent, over loopback WebSockets: token auth (accept + reject)
  and a full agent→relay→daemon→DCC round-trip with error propagation.

```bash
uv run pytest packages/daemon/tests/   # 31 tests
uv run ruff check packages/ plugins/
```

What this does **not** cover — real bpy/hou/unreal API calls, main-thread
timing inside a live DCC, and actual viewport capture — is verified
manually against running DCCs.

## Status

- **Done:** daemon core; transport with JSON + RPyC adapters; instance
  discovery; health checks; MCP-over-HTTP ingress; Blender + Unreal
  plugins (Houdini via hot-pluggable RPyC); monitoring WebUI; outbound
  WebSocket tunnel + relay + token auth for remote agents; tests.
- **Next:** plugin-install guides in the WebUI; DCC-side skills; hardening
  the tunnel (rate limits, token rotation) for real deployment.

## License

MIT
