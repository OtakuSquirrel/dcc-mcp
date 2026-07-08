"""Unreal Engine plugin — daemon socket server adapter.

Wires the shared, DCC-agnostic ``DCCServer`` (from
``plugins/common/dcc_socket_server.py``) to Unreal's game thread.

Why not UE's built-in Python Remote Execution? That protocol uses UDP
multicast discovery plus a *reverse* connection (the editor dials back to
the client), which breaks the daemon's uniform "scan a TCP port, connect
to it" model. Embedding the same socket server every other DCC uses keeps
UE on the identical JSON channel and the identical adapter
(``JsonSocketAdapter``, selected by the 20811+ port range) — the daemon
needs no UE-specific code.

The only UE-specific piece is ``run_on_main``: the ``unreal`` API must be
touched on the game thread, so network threads enqueue jobs that a
Slate post-tick callback drains — exactly parallel to Blender's
``bpy.app.timers`` bridge.

Install (Editor): put this file on the project's Python path and run it
from  Edit > Project Settings > Python > Startup Scripts, or paste into
the Output Log Python console. Headless:
  UnrealEditor-Cmd.exe <project> -run=pythonscript -script="ue_startup.py"
"""

from __future__ import annotations

import base64
import os
import queue
import sys
import threading

import unreal  # provided by the UE Python environment

sys.path.insert(0, os.path.dirname(__file__))
from dcc_socket_server import DCCServer, default_info  # noqa: E402

_DEFAULT_PORT = 20811
_server: "DCCServer | None" = None

# ── main-thread bridge ──────────────────────────────────────────────
# Network threads enqueue work; a Slate post-tick callback drains it on
# the game thread. Each job carries an Event so the caller blocks for the
# result, matching DCCServer.run_on_main's synchronous contract.
_jobs: "queue.Queue[tuple]" = queue.Queue()
_tick_handle = None


def _run_on_main(fn):
    box: dict = {}
    ev = threading.Event()
    _jobs.put((fn, box, ev))
    if not ev.wait(timeout=590):
        raise TimeoutError("game-thread job did not complete in time")
    if "err" in box:
        raise box["err"]
    return box["res"]


def _drain_jobs(_delta_seconds: float) -> None:
    # Runs on UE's game thread (registered as a slate post-tick callback).
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


# ── DCC-specific hooks (all run on the game thread) ─────────────────

def _get_info() -> dict:
    try:
        version = unreal.SystemLibrary.get_engine_version()
    except Exception:  # noqa: BLE001
        version = ""
    try:
        level = unreal.EditorLevelLibrary.get_editor_world().get_path_name()
    except Exception:  # noqa: BLE001
        level = ""
    return default_info("ue", str(version), level)


def _exec_globals() -> dict:
    return {"unreal": unreal}


def _screenshot() -> str:
    path = os.path.join(unreal.Paths.project_saved_dir(), "dcc_daemon_shot.png")
    # High-res screenshot of the active editor viewport.
    unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, path)
    # take_high_res_screenshot is queued for the next frame; the file may
    # not exist yet on the very first call. Read best-effort.
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def start(port: int = _DEFAULT_PORT) -> None:
    global _server, _tick_handle
    if _server is not None:
        return
    _server = DCCServer(
        kind="ue",
        run_on_main=_run_on_main,
        get_info=_get_info,
        exec_globals=_exec_globals,
        screenshot=_screenshot,
    )
    _server.start(port)
    _tick_handle = unreal.register_slate_post_tick_callback(_drain_jobs)
    unreal.log("[dcc-daemon] UE socket server started on port %d" % port)


def stop() -> None:
    global _server, _tick_handle
    if _server is not None:
        _server.stop()
        _server = None
    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None


if __name__ == "__main__":
    port = int(os.environ.get("DCC_DAEMON_PORT", _DEFAULT_PORT))
    start(port)
