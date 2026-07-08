# DCC plugin installation guide

> Draft for review. Describes how to install the daemon-side plugin into
> each DCC so the daemon can discover and drive it. Once reviewed, some
> of this can be automated (one-click install from the WebUI); for now
> these are the manual steps.

Each DCC needs a small plugin that opens a socket the daemon connects to
(Blender, Unreal) or a built-in RPyC server (Houdini). All of them run a
Python channel on a fixed port; the daemon scans these ranges to
discover instances:

| DCC | Default port | Range scanned |
|-----|--------------|---------------|
| Houdini | 18811 | 18811–18899 |
| Blender | 19811 | 19811–19899 |
| Unreal | 20811 | 20811–20899 |

The plugin files live in `plugins/`:
- `plugins/common/dcc_socket_server.py` — shared socket server (Blender, UE)
- `plugins/blender_daemon/` — Blender addon
- `plugins/ue_daemon/` — Unreal startup script
- Houdini needs no file — it uses the built-in `hrpyc`.

---

## Blender

The addon wires the shared socket server to Blender's main thread via
`bpy.app.timers`.

### Option A — install as an addon (persistent)

1. Make a folder `dcc_daemon_blender/` containing **both**:
   - `plugins/blender_daemon/__init__.py`
   - `plugins/common/dcc_socket_server.py`
2. Copy that folder into Blender's addons directory:
   - Windows: `%APPDATA%\Blender Foundation\Blender\<ver>\scripts\addons\`
   - macOS: `~/Library/Application Support/Blender/<ver>/scripts/addons/`
   - Linux: `~/.config/blender/<ver>/scripts/addons/`
3. Blender → Edit > Preferences > Add-ons → enable **“DCC Daemon Bridge.”**
   It starts the server on port 19811 (override with the `DCC_DAEMON_PORT`
   env var before launching Blender).

### Option B — headless / one-off

```bash
blender --python plugins/blender_daemon/__init__.py -- --port 19811
```

### Verify

With Blender running, `list_instances()` from the daemon should show a
`blender` entry on 19811.

---

## Unreal Engine

Unreal uses the same socket server, wired to the game thread via a Slate
post-tick callback. Requires the **Python Editor Script Plugin** enabled
(Edit > Plugins > “Python Editor Script Plugin” → restart).

### Option A — startup script (persistent)

1. Put `plugins/ue_daemon/__init__.py` and
   `plugins/common/dcc_socket_server.py` on the project's Python path
   (e.g. `<Project>/Content/Python/`).
2. Edit > Project Settings > Plugins > Python > **Startup Scripts** → add
   the path to `__init__.py`.
3. Restart the editor. Server starts on 20811 (override via
   `DCC_DAEMON_PORT`).

### Option B — paste into the console

Open Output Log → set the console to **Python** → paste the contents of
`__init__.py` (or `exec(open(r"...\__init__.py").read())`).

### Option C — headless

```bash
UnrealEditor-Cmd.exe <Project.uproject> -run=pythonscript -script="<path>\__init__.py"
```

### Verify

`list_instances()` should show a `ue` entry on 20811.

---

## Houdini

No plugin file to install — Houdini ships `hrpyc`. It is **hot-pluggable**:
start it from a running session, no addon, no restart.

1. In Houdini, open the Python Shell (Windows > Python Shell).
2. Run:
   ```python
   import hrpyc
   hrpyc.start_server(port=18811)
   ```
   To start it automatically, put that in a `123.py` startup script on
   `$HOUDINI_PATH`.

### Verify

`list_instances()` should show a `houdini` entry on 18811. Note: the
daemon reads Houdini over RPyC, so a headless Houdini works for data
operations but `screenshot` needs a GUI with a Scene Viewer.

---

## Running multiple instances

Give each instance a distinct port within its DCC's range (via
`DCC_DAEMON_PORT` for Blender/UE, or the `port=` arg for Houdini). The
daemon discovers all of them; address each by its port.

## Troubleshooting

- **Not shown in `list_instances`** — plugin not started, or on a port
  outside the scanned range. Check the DCC's console/log for the
  “socket server started” / hrpyc message.
- **`reachable: false`** — a listener answered but not our protocol
  (still starting, or a port clash). Confirm the port and that the
  correct plugin is loaded.
- **`health` says `no_protocol`** — the process is up but the plugin
  port isn't answering; re-enable/re-run the plugin.
