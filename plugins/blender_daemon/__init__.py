"""Blender addon — daemon socket server adapter.

Wires the shared, DCC-agnostic ``DCCServer`` (from
``plugins/common/dcc_socket_server.py``) to Blender's main thread. The
only Blender-specific piece is ``run_on_main``: Blender is not
thread-safe, so code must run inside a ``bpy.app.timers`` callback.

Install: copy this folder + ``dcc_socket_server.py`` into Blender's
addons dir as ``dcc_daemon_blender``, enable in Preferences > Add-ons.
Or launch headless:  blender --python start.py -- --port 19811
"""

from __future__ import annotations

import base64
import os
import queue
import sys
import threading

bl_info = {
    "name": "DCC Daemon Bridge",
    "author": "dcc-mcp",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "N-panel > DCC",
    "description": "Minimal socket server: execute_python channel for the dcc-daemon",
    "category": "System",
}

import bpy  # noqa: E402

# Make the shared server importable when vendored next to this file.
sys.path.insert(0, os.path.dirname(__file__))
from dcc_socket_server import DCCServer, default_info  # noqa: E402

_DEFAULT_PORT = 19811
_server: DCCServer | None = None

# ── main-thread bridge ──────────────────────────────────────────────
# Network threads enqueue work; a persistent timer drains it on the main
# thread. Each job carries an Event so the caller blocks for the result.
_jobs: "queue.Queue[tuple]" = queue.Queue()


def _run_on_main(fn):
    box: dict = {}
    ev = threading.Event()
    _jobs.put((fn, box, ev))
    if not ev.wait(timeout=590):
        raise TimeoutError("main-thread job did not complete in time")
    if "err" in box:
        raise box["err"]
    return box["res"]


def _drain_jobs():
    # Runs on Blender's main thread (registered as a timer).
    while True:
        try:
            fn, box, ev = _jobs.get_nowait()
        except queue.Empty:
            break
        try:
            box["res"] = fn()
        except Exception as e:  # noqa: BLE001
            box["err"] = e
        finally:
            ev.set()
    return 0.02  # poll at 50 Hz


# ── DCC-specific hooks ──────────────────────────────────────────────

def _get_info() -> dict:
    return default_info(
        "blender",
        ".".join(str(v) for v in bpy.app.version),
        bpy.data.filepath or "(unsaved)",
    )


def _exec_globals() -> dict:
    import mathutils
    return {"bpy": bpy, "mathutils": mathutils}


def _screenshot() -> str:
    path = os.path.join(bpy.app.tempdir, "dcc_daemon_shot.png")
    bpy.ops.screen.screenshot(filepath=path)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def start(port: int = _DEFAULT_PORT) -> None:
    global _server
    if _server is not None:
        return
    _server = DCCServer(
        kind="blender",
        run_on_main=_run_on_main,
        get_info=_get_info,
        exec_globals=_exec_globals,
        screenshot=_screenshot,
    )
    _server.start(port)
    if not bpy.app.timers.is_registered(_drain_jobs):
        bpy.app.timers.register(_drain_jobs, first_interval=0.02, persistent=True)


def stop() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None
    if bpy.app.timers.is_registered(_drain_jobs):
        bpy.app.timers.unregister(_drain_jobs)


def register() -> None:
    port = int(os.environ.get("DCC_DAEMON_PORT", _DEFAULT_PORT))
    start(port)


def unregister() -> None:
    stop()


if __name__ == "__main__":
    # Headless launch path: `blender --python __init__.py -- --port 19811`
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else _DEFAULT_PORT
    start(port)
