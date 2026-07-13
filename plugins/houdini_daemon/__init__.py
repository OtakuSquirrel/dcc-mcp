"""Houdini plugin — daemon socket server adapter.

Wires the shared, DCC-agnostic ``DCCServer`` (from
``plugins/common/dcc_socket_server.py``) to Houdini's main thread.

Houdini used to be driven over RPyC (``hrpyc``); it now uses the same
embedded socket server as every other DCC, so all four speak one
protocol and the daemon needs no Houdini-special case. It dials the
daemon and registers; no port to pick.
The only Houdini-specific piece is ``run_on_main``: ``hou`` is not
thread-safe, so code must run on the main thread — Houdini provides
``hdefereval.executeInMainThreadWithResult`` for exactly this (the
equivalent of Maya's utility and Blender's timer bridge).

Install: copy this file + ``dcc_socket_server.py`` somewhere on
``$HOUDINI_PATH`` and import it from a ``123.py``/``456.py`` startup
script, or paste into the Python Shell:

    import dcc_daemon_houdini as d; d.start()
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dcc_socket_server import DCCServer, default_info  # noqa: E402

import hou  # noqa: E402  — provided by the Houdini Python environment

_server: "DCCServer | None" = None


# ── main-thread bridge ──────────────────────────────────────────────
# Houdini ships a blocking "run this on the main thread and give me the
# result" primitive — it IS our run_on_main. It blocks the calling
# (network) thread until the main thread runs the callable at idle.
def _run_on_main(fn):
    import hdefereval
    return hdefereval.executeInMainThreadWithResult(fn)


# ── DCC-specific hooks (run on the main thread) ─────────────────────

def _get_info() -> dict:
    try:
        version = hou.applicationVersionString()
    except Exception:  # noqa: BLE001
        version = ""
    try:
        hip = hou.hipFile.path()
    except Exception:  # noqa: BLE001
        hip = ""
    return default_info("houdini", version, hip)


def _exec_globals() -> dict:
    return {"hou": hou}


def start(register_port: int | None = None) -> None:
    """Connect to the daemon and register. Dial ``register_port`` if
    given, else read it from the config file."""
    global _server
    if _server is not None:
        return
    _server = DCCServer(
        kind="houdini",
        run_on_main=_run_on_main,
        get_info=_get_info,
        exec_globals=_exec_globals,
    )
    _server.start(register_port)


def stop() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None


if __name__ == "__main__":
    env = os.environ.get("DCC_DAEMON_REGISTER_PORT")
    start(int(env) if env else None)
