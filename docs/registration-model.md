# Design: registration model for daemon ↔ DCC

Status: **implemented.** The second segment (daemon ↔ DCC) is now a
*registration* model: each DCC dials the daemon on launch, registers, and
holds one connection; the daemon keeps a live table and pushes requests
down. This doc records the design and rationale. The agent-facing side
remains MCP-over-HTTP.

## Why

The pull model rediscovers everything on demand: scan the port pool,
`get_info` each listener, `find_pid_for_port` via powershell/lsof, judge
liveness by "can I still connect." That throws away information the DCC
already knows and re-derives it every query.

Registration keeps a **live table** in the daemon:

- **No port scan.** `list_instances` reads memory (O(1)), not a scan.
- **Metadata registered once.** kind/pid/version/file arrive at connect
  and are held, not re-probed.
- **Free, precise death detection.** DCC exits → socket closes → daemon
  drops it immediately (no "failed to connect ⇒ maybe dead" guess).
- **PID handed over directly.** Deletes the fragile `find_pid_for_port`
  (powershell/lsof) path.
- **One listening port total** (the daemon's), instead of one per DCC +
  a scanned pool. Smaller system footprint — closer to the "guardian"
  goal.

## What does NOT change

- Agent → daemon: MCP-over-HTTP is unchanged.
- The main-thread bridge in each plugin (`run_on_main`: bpy.app.timers /
  slate tick / hdefereval / maya.utils) is unchanged.
- The DCC command set: `execute_python` / `get_info` / (ping). Screenshots
  are captured by the daemon from the registered process's Windows window.
- `DCCServer._exec`, `_handle` dispatch, JSON framing — reused verbatim.

## Architecture

### Registration channel

Daemon opens **one** listening socket for DCC registration (config:
`[daemon] dcc_register_port`, default e.g. 18813, localhost only). Each DCC
plugin, on launch:

1. Connects to `127.0.0.1:<dcc_register_port>` (retry with backoff until
   the daemon is up).
2. Sends a `register` frame: `{"kind","pid","version","file"}`.
3. Holds the connection. The daemon now **pushes requests down it**:
   `{"id","command","params"}`; the plugin runs them on the main thread
   and replies `{"id","result"|"error"}` — exactly today's `_handle`,
   just multiplexed by `id` over a persistent, reversed socket.

The plugin's socket loop changes from `accept()` (server) to
`connect()+reconnect` (client). The request-handling body is identical.

### Instance identity: `instance_id`, not `port`

With no per-DCC port, the agent handle becomes a daemon-assigned
`instance_id` (e.g. `blender-1`, or a short uid). This touches:

- meta-tools: `execute_python(instance_id, code)`, `health(instance_id)`,
  `screenshot(instance_id)`. `list_instances` returns `instance_id`
  instead of `port`.
- skill text (`SKILL.md`, `references/*`): "pick the `port`" → "pick the
  `instance_id`"; keep the discover→act→verify loop.

`port` was always an implementation detail leaking to the agent; a
logical id is cleaner. (pid is also unique but recycles; a daemon-issued
id avoids that.)

### Daemon-side registry (rewritten)

`InstanceRegistry` stops scanning and becomes a table of live
registrations:

```
register(conn, meta) -> instance_id      # on DCC connect
drop(instance_id)                         # on socket close
list() -> [ {instance_id, kind, pid, version, file, connected_at} ]
send(instance_id, command, params) -> result   # push down held conn, await reply by id
```

`TransportPool` (port-keyed connect cache) is **replaced** by this
registration hub — the daemon no longer initiates DCC connections at all.

### Health, redone (the important detail)

Connection up/down gives **liveness** for free, but NOT **responsiveness**
— a frozen DCC (modal dialog, infinite loop) keeps its socket open on the
network thread while the main thread is wedged. So:

- `connected` — socket present (from the registry). Free.
- `responsive` — a heartbeat that runs **on the main thread**
  (`run_on_main(lambda: True)` with a short timeout). No reply in time ⇒
  main thread is busy/hung. This is the real "is it healthy" signal.
- OS checks (`IsHungAppWindow`, CPU sampling) stay, to split "busy
  computing" from "truly hung." `find_pid_for_port` is deleted — pid
  comes from registration.

Verdicts stay: `healthy | busy | hung | dead(=disconnected) | unknown`.

### Keepalive / half-open detection

A dropped socket normally surfaces as `recv` returning empty. But some
DCC operations (notably in Blender: file reload, GPU stalls,
crash-recovery) can leave the TCP connection **half-open** — dead with no
FIN/RST — so both ends' `recv` block forever and the stale registration
lingers. To close this gap the connection is kept alive at the
application layer:

- **DCC → daemon heartbeat.** Every few seconds
  (`_HEARTBEAT_INTERVAL`, 5s) each connector writes a tiny
  `{"type":"heartbeat"}` frame. If that write fails, the link is
  (half-)dead: the connector drops the socket, unblocking its reader, and
  the reconnect loop re-registers.
- **Daemon reaper.** The hub records `last_seen` on every received frame
  and a background reaper (`_REAPER_INTERVAL`) closes any connection
  silent past `_HEARTBEAT_TIMEOUT` (20s), which unregisters the stale
  instance. Heartbeat frames are consumed silently — they only refresh
  `last_seen`, never routed as request replies.

This applies to every DCC: the Python connector
(`plugins/common/dcc_socket_server.py`, shared by Blender/Houdini/UE/Maya)
and the C# connector (`plugins/tuanjie_daemon/DccDaemonServer.cs`).

## Obstacles and how they're handled

| Obstacle | Handling |
|----------|----------|
| DCC starts before daemon / daemon restarts | Plugin retries `connect` with exponential backoff. Daemon restart ⇒ all DCCs reconnect; a few-second gap where they were unreachable anyway. |
| Frozen DCC still holds socket | Main-thread heartbeat (above), not socket state, decides responsiveness. |
| Half-open connection (TCP dead, no FIN/RST — e.g. Blender after a heavy op) | App-level keepalive: DCC writes a periodic heartbeat (failed write ⇒ drop & reconnect); daemon reaps connections silent past the timeout. See "Keepalive / half-open detection." |
| Agent handle churn | `port` → `instance_id` across meta-tools + skill. One-time, mechanical. |
| Ordering of replies over one socket | Multiplex by request `id`. Per-instance lock keeps main-thread calls serialized. |
| Config | Drop `[ports] dcc = [...]` pool entirely. Add `[daemon] dcc_register_port`. `read_dcc_ports`/`dcc_ports`/`claim_and_start` removed. |
| Old pull model references | `TransportPool`, port scanning in `registry.py`, `find_pid_for_port` — removed. |

## What stays a real cost (not oversold)

- It's still a localhost TCP socket, just reversed and fewer of them —
  not "zero networking." True zero would need named pipes / UDS (a
  separate, bigger change; not proposed).
- Daemon becomes stateful about connections (must handle reconnect,
  dedup a DCC that reconnects after a network blip). Manageable, but more
  moving parts than "scan on demand."

## Files touched

- `plugins/common/dcc_socket_server.py`: `accept()` server → `connect()`
  client with register handshake + reconnect loop; drop
  `claim_and_start`/`read_dcc_ports`.
- `src/dcc_mcp/hub.py`: scan → live registration hub
  + `send()`.
- `.../transport.py`: removed (folded into the hub) or reduced to the
  frame codec.
- `.../core.py`: `execute_python(instance_id,…)` etc. via the hub.
- `.../health.py`: main-thread heartbeat + OS checks; drop
  `find_pid_for_port`.
- `.../config.py`: drop port pool; add `dcc_register_port`.
- `.../mcp_server.py`: `port` → `instance_id` in the 4 tools + docstrings.
- 4 plugins: call the new register-and-hold entry instead of
  `claim_and_start`.
- skill `SKILL.md` + `references/*`: port → instance_id wording.
- tests: registry/e2e fixtures drive the register handshake
  instead of starting a listening server; drop `test_claim_port`.
- docs: README + plugin-install updated (no port pool; register port).

## Migration note

This is a breaking change to the daemon↔DCC contract and the agent
handle. Since nothing is deployed yet, no compatibility shim — replace
outright.
