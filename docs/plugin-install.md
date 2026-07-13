# DCC plugin installation guide

The WebUI **Install** tab is the primary installation path. It detects the
operating system and local DCC preference directories, previews exact file
changes, and requires explicit confirmation before writing. Installations are
recorded under `~/.dcc-mcp/installations/` for verification and safe uninstall.

All four DCC installation flows are automated. Blender requires one final
enable action in Preferences. Unreal Engine supports both a current-user Python
startup and a plugin installed into a selected project.

Every DCC embeds the **same** small connector
(`plugins/common/dcc_socket_server.py`). On launch it **dials the daemon**
(the daemon's `dcc_register_port`, default 18813), registers its identity,
and holds the connection; the daemon assigns an `instance_id` and pushes
requests down it. There is no listening port per DCC and no scanning. All
DCCs are equal — the connector self-reports its kind.

The daemon must be running first (or the connector retries until it is).
The register port comes from `~/.dcc-mcp/config.toml`:

```toml
[daemon]
dcc_register_port = 18813
```

Plugin files:
- `plugins/common/dcc_socket_server.py` — shared connector (needed by all)
- `plugins/blender_daemon/` — Blender addon
- `plugins/houdini_daemon/` — Houdini plugin
- `plugins/ue_daemon/` — Unreal startup script
- `plugins/maya_daemon/` — Maya startup script

In every case, put `dcc_socket_server.py` **next to** the per-DCC
`__init__.py` (each plugin adds its own dir to `sys.path`). To override
the register port for one DCC, set `DCC_DAEMON_REGISTER_PORT` before
launching it.

---

## Blender

Wires the shared server to Blender's main thread via `bpy.app.timers`.

### Recommended — WebUI user add-on installer

Scan, select the Blender version, preview, and confirm. Restart Blender, then
enable **DCC Daemon Bridge** in Preferences > Add-ons. The installer avoids
editing Blender's binary preferences while Blender may be running.

### Manual fallback — addon

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
blender --python plugins/blender_daemon/__init__.py                         # register with daemon
blender --python plugins/blender_daemon/__init__.py -- --register-port 18813  # override port
```

---

## Houdini

Wires the shared server to the main thread via
`hdefereval.executeInMainThreadWithResult`. (Previously Houdini used
`hrpyc`/RPyC; it now uses the same socket plugin as everything else.)

### Recommended — WebUI Package installer

Scan in the WebUI, select the Houdini version, preview the plan, and confirm.
The installer writes `dcc_daemon.json` to that version's `packages` directory.
It points at `~/.dcc-mcp/plugins/houdini/<version>/`, which contains the adapter plus
`scripts/123.py` and `scripts/456.py`. It does not modify `houdini.env` or an
existing personal startup script. Restart Houdini after installation.

### Manual fallback — startup script

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

### Recommended — WebUI current-user startup

Scan and install `UE <version> · Current user`. This writes the managed adapter
under `~/Documents/UnrealEngine/Python`, an official Unreal Python search path,
and safely adds a marked block to `init_unreal.py`. It applies to installed UE
Editor versions for the current OS user without modifying Program Files.

Unreal requires **Python Editor Script Plugin** to be enabled separately in
each project. Enable it under Edit > Plugins > Scripting and restart the Editor.

### Project-scoped plugin

Paste a `.uproject` path (or its containing directory) into the UE card and
select **Add project**. The installer previews and writes:

```text
<Project>/Plugins/DCCDaemon/
  DCCDaemon.uplugin
  Content/Python/init_unreal.py
  Content/Python/dcc_daemon_ue/
```

The descriptor declares the PythonScriptPlugin dependency and affects only
that project. Managed projects remain visible after the daemon restarts.

### Manual alternatives

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

### Recommended — WebUI Module installer

Scan in the WebUI, select the Maya version, preview the plan, and confirm. The
installer writes `dcc_daemon.mod` under that version's `modules` directory.
The module points at `~/.dcc-mcp/plugins/maya/<version>/`, whose `scripts` directory has
an isolated `userSetup.py`. It does not edit your personal `userSetup.py`.
Restart Maya after installation.

### Manual fallback — `userSetup.py`

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

Just launch them — each dials the daemon and registers independently. The
daemon assigns each a distinct `instance_id` (`blender-1`, `blender-2`, …);
address each by its id.

## Troubleshooting

- **Not shown in `list_instances`** — the connector hasn't registered:
  the daemon wasn't running when the DCC started (it retries with
  backoff, so check again), or the DCC's console shows a connection
  error. Confirm `dcc_register_port` matches on both sides.
- **`connected: false`** — the registration dropped (DCC quit or the
  socket broke); it will re-register on reconnect.
- **`health` says `busy`/`hung`** — connected but the main thread isn't
  answering the heartbeat (heavy compute, modal dialog, or a wedge).
- **Connector never registers** — verify the daemon is up and reachable
  at `127.0.0.1:<dcc_register_port>`.
