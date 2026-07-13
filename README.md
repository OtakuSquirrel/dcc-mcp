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
closes), and the pid arrives at registration (no port-scraping).

**A daemon, not a spawned subprocess.** Long-lived and process-
independent, it serves several local agents at once. Discovery and health
queries (constant during connect/reconnect) are answered by this one
resident process.

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
JSON. On launch it **dials the daemon's register port** (default 18813),
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

## Quick start (local)

The full local loop: **run the daemon → point an agent at it → give a
DCC its plugin → drive it.** Verified end-to-end with Blender.

### 1. Install

```bash
uv sync --extra dev          # create .venv and install the daemon CLI
```

### 2. Run the daemon (keep it running)

The daemon is a resident "guardian" — start it once and leave it up; it
is independent of any agent.

```bash
uv run dcc-daemon            # serves MCP on 127.0.0.1:18812, register hub on :18813
```

On Windows, double-click **`start-daemon.bat`** instead — it opens a
console window that streams logs live; close the window to stop the
daemon.

**Is it running?** Open <http://127.0.0.1:18812/> in a browser. The local
WebUI provides instance monitoring, a bounded daemon log viewer, local DCC
detection and installation, and read-only diagnostics.
It uses initial/manual refresh rather than periodic polling. Or check the
port: `Get-NetTCPConnection -LocalPort 18812` (Windows) /
`lsof -i:18812` (macOS/Linux).

### 3. Point your agent at it

A project-scoped `.mcp.json` (already in this repo) registers the daemon
as an MCP server over HTTP:

```json
{ "mcpServers": { "dcc": { "type": "http", "url": "http://127.0.0.1:18812/mcp" } } }
```

MCP servers load at agent **startup**, and only if the endpoint is
reachable — so start the daemon *first*, then (re)start your agent
(e.g. Claude Code). The `dcc` tools (`list_instances`, `execute_python`,
`screenshot`, `health`) then appear.

### 4. Install a DCC plugin

Open the WebUI **Install** tab and click **Scan this computer**. Blender,
Houdini, Maya, and Unreal Engine support preview-and-confirm installation,
verification, and manifest-based uninstall. Blender still needs its installed
add-on enabled in Preferences; Houdini and Maya start automatically after
restart.

Unreal Engine offers a current-user startup shared by installed UE versions and
a project-scoped plugin for a selected `.uproject`. UE's Python Editor Script
Plugin must be enabled for each project. The Blender development-checkout flow
also remains available. Blender example:

Assemble a folder with **both** the per-DCC file and the shared connector:

```bash
# stage the addon (both files must sit together)
mkdir -p dcc_daemon_blender
cp plugins/blender_daemon/__init__.py     dcc_daemon_blender/
cp plugins/common/dcc_socket_server.py    dcc_daemon_blender/
```

Then either install it as an addon (Preferences → Add-ons → “DCC Daemon
Bridge”), or launch Blender with it directly:

```bash
blender --python dcc_daemon_blender/__init__.py
```

On launch it dials the daemon and registers. Full per-DCC steps (Houdini,
Unreal, Maya) are in [docs/plugin-install.md](docs/plugin-install.md).

### 5. Drive it

Ask the agent something like *"list the DCCs, then add a sphere in
Blender."* Under the hood:

```
list_instances()                    -> [{"instance_id": "blender-1", ...}]
execute_python("blender-1", "bpy.ops.mesh.primitive_uv_sphere_add()")
screenshot("blender-1")             -> the viewport image
```

There are no per-operation tools — the agent writes `bpy`/`hou`/`unreal`/
`cmds` and sends it through `execute_python`; the `dcc-control` skill
(under `skills/`) teaches the recipes.

## Configuration

One file, `~/.dcc-mcp/config.toml`, exposed for the user (a WebUI can
edit it later). DCCs dial the daemon, so there's no port pool — just the
two ports the daemon listens on:

```toml
[daemon]
host = "127.0.0.1"
port = 18812               # MCP-over-HTTP for agents
dcc_register_port = 18813  # DCCs dial here to register
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
    webui/                  overview, logs, plugin install, and diagnostics UI
    app.py                  builds the ASGI app (MCP + WebUI); starts the hub
    __main__.py             `dcc-daemon` entry point
  tests/                    tests against real protocol stand-ins
plugins/common/             DCC-agnostic connector (dials + registers), vendored per DCC
plugins/blender_daemon/     Blender addon (bpy.app.timers bridge)
plugins/houdini_daemon/     Houdini plugin (hdefereval bridge)
plugins/ue_daemon/          Unreal script (slate post-tick bridge)
plugins/maya_daemon/        Maya plugin (executeInMainThreadWithResult bridge)
skills/dcc-control/         agent skill: how to drive DCCs via execute_python (SKILL.md + references/)
docs/                       plugin-install guide + registration-model design note
```

## Testing

Tests cannot launch real DCCs, so they **stand in the DCC end with the
real protocol**, exercising the daemon's actual code paths:

- `tests/test_e2e.py` — a real `DCCServer` from `plugins/common/` dials a
  real `RegistrationHub` over loopback and registers, parametrized over
  all four DCC kinds. Covers register/execute/inspect/health/screenshot
  and error propagation.
- `tests/test_webui.py` — the dashboard + JSON APIs via Starlette's
  TestClient.
```bash
uv run pytest packages/daemon/tests/   # 37 tests
uv run ruff check packages/ plugins/
```

What this does **not** cover — real bpy/hou/unreal/cmds API calls,
main-thread timing inside a live DCC, and actual viewport capture — is
verified manually against running DCCs.

## Status

- **Done:** guardian daemon; registration model (DCCs dial in, live
  registry, free death detection); one JSON protocol across Blender,
  Houdini, Unreal, Maya; main-thread-heartbeat health; MCP-over-HTTP
  ingress; monitoring WebUI; tests.
- **Next:** one-click install + autostart; plugin-install UI in the WebUI;
  real-DCC integration coverage; protocol and reconnect hardening.

## License

MIT
