# DCC plugin installation guide

> Draft for review. Describes how to install the daemon-side plugin into
> each DCC so the daemon can discover and drive it. Once reviewed, some
> of this can be automated (one-click install from the WebUI); for now
> these are the manual steps.

Every DCC embeds the **same** small socket-server plugin
(`plugins/common/dcc_socket_server.py`). On launch the plugin reads the
port pool from `~/.dcc-mcp/config.toml`, scans it, and **claims the first
free port**. The daemon scans the same pool to discover instances. All
DCCs are equal — the plugin self-reports its kind; the port carries no
meaning.

Configure the pool once (`~/.dcc-mcp/config.toml`):

```toml
[ports]
dcc = [18811, 18812, 18813, 18814, 18815, 18816, 18817, 18818, 18819, 18820]
```

Plugin files:
- `plugins/common/dcc_socket_server.py` — shared server (needed by all)
- `plugins/blender_daemon/` — Blender addon
- `plugins/houdini_daemon/` — Houdini plugin
- `plugins/ue_daemon/` — Unreal startup script
- `plugins/maya_daemon/` — Maya startup script

In every case, put `dcc_socket_server.py` **next to** the per-DCC
`__init__.py` (each plugin adds its own dir to `sys.path`). To pin a
specific port instead of claiming from the pool, set `DCC_DAEMON_PORT`
before launching the DCC.

---

## Blender

Wires the shared server to Blender's main thread via `bpy.app.timers`.

### Option A — addon (persistent)

1. Make a folder `dcc_daemon_blender/` containing **both**
   `plugins/blender_daemon/__init__.py` and
   `plugins/common/dcc_socket_server.py`.
2. Copy it into Blender's addons directory:
   - Windows: `%APPDATA%\Blender Foundation\Blender\<ver>\scripts\addons\`
   - macOS: `~/Library/Application Support/Blender/<ver>/scripts/addons/`
   - Linux: `~/.config/blender/<ver>/scripts/addons/`
3. Edit > Preferences > Add-ons → enable **“DCC Daemon Bridge.”**

### Option B — headless / one-off

```bash
blender --python plugins/blender_daemon/__init__.py       # claim from pool
blender --python plugins/blender_daemon/__init__.py -- --port 18811
```

---

## Houdini

Wires the shared server to the main thread via
`hdefereval.executeInMainThreadWithResult`. (Previously Houdini used
`hrpyc`/RPyC; it now uses the same socket plugin as everything else.)

### Option A — startup script (persistent)

1. Put `plugins/houdini_daemon/__init__.py` and
   `plugins/common/dcc_socket_server.py` on `$HOUDINI_PATH` (e.g.
   `$HOUDINI_USER_PREF_DIR/scripts/`).
2. In a `123.py` (or `456.py`) startup script:
   ```python
   import dcc_daemon_houdini; dcc_daemon_houdini.start()
   ```

### Option B — Python Shell (hot start on a live session)

Windows > Python Shell:
```python
import sys; sys.path.append(r"<path-to-plugins/houdini_daemon>")
import dcc_daemon_houdini as d; d.start()
```

### Verify

`list_instances()` shows a `houdini` entry. Data ops work headless;
`screenshot` needs a GUI with a Scene Viewer.

---

## Unreal Engine

Wires the shared server to the game thread via a Slate post-tick
callback. Requires the **Python Editor Script Plugin** (Edit > Plugins →
enable → restart).

### Option A — startup script (persistent)

1. Put `plugins/ue_daemon/__init__.py` and
   `plugins/common/dcc_socket_server.py` on the project's Python path
   (e.g. `<Project>/Content/Python/`).
2. Edit > Project Settings > Plugins > Python > **Startup Scripts** → add
   the path to `__init__.py`.
3. Restart the editor.

### Option B — console

Output Log → set console to **Python** →
`exec(open(r"...\ue_daemon\__init__.py").read())`.

### Option C — headless

```bash
UnrealEditor-Cmd.exe <Project.uproject> -run=pythonscript -script="<path>\__init__.py"
```

---

## Maya

Wires the shared server to the main thread via
`maya.utils.executeInMainThreadWithResult` (simplest of the four — no
queue/timer). Requires interactive GUI Maya (not batch `mayapy`). The
daemon deliberately does **not** use Maya's built-in `commandPort`.

### Option A — `userSetup.py` (persistent)

1. Put `plugins/maya_daemon/__init__.py` and
   `plugins/common/dcc_socket_server.py` in a scripts dir on Maya's
   `PYTHONPATH` (e.g. `~/maya/scripts/`).
2. In `~/maya/scripts/userSetup.py`:
   ```python
   import dcc_daemon_maya; dcc_daemon_maya.start()
   ```

### Option B — Script Editor (hot start)

```python
import sys; sys.path.append(r"<path-to-plugins/maya_daemon>")
import dcc_daemon_maya; dcc_daemon_maya.start()
```

### Verify

`list_instances()` shows a `maya` entry. `screenshot` uses a playblast of
the active viewport (GUI only).

---

## Running multiple instances

Just launch them — each plugin claims the next free port in the pool
automatically. The daemon discovers them all; address each by its port.

## Troubleshooting

- **Not shown in `list_instances`** — plugin not started, or the pool is
  full / misconfigured. Check the DCC's console for the “socket server
  listening on …” line.
- **`reachable: false`** — a listener answered but not our protocol
  (still starting, or a non-DCC service claimed the port).
- **`health` says `no_protocol`** — process up but the plugin port isn't
  answering; re-run the plugin.
- **“no free port in pool”** — every pool port is taken; widen
  `ports.dcc` in `~/.dcc-mcp/config.toml`.
