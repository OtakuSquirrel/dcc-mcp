"""Maya plugin — daemon socket server adapter.

Wires the shared, DCC-agnostic ``DCCServer`` (from
``plugins/common/dcc_socket_server.py``) to Maya's main thread.

Maya's ``cmds``/API are not thread-safe and must run on the main thread.
Maya ships exactly the primitive we need:
``maya.utils.executeInMainThreadWithResult`` — it blocks the calling
(network) thread until the main thread runs the callable at the next
idle and returns its result. So ``run_on_main`` is that function
verbatim; no queue or timer bridge needed (simpler than Blender/UE).

This deliberately does NOT use Maya's built-in ``commandPort`` — that is
a raw MEL-first socket with a small buffer limit and no clean way to
return values from multi-line Python. Embedding our own socket server
keeps Maya on the identical JSON protocol as every other DCC.

Install: copy this file + ``dcc_socket_server.py`` into a scripts dir on
Maya's ``PYTHONPATH`` (e.g. ``~/maya/scripts``) and start it from
``userSetup.py``:

    import dcc_daemon_maya; dcc_daemon_maya.start()
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dcc_socket_server import DCCServer, default_info  # noqa: E402

import maya.cmds as cmds  # noqa: E402  — Maya Python environment
import maya.utils  # noqa: E402

_server: "DCCServer | None" = None

# The whole main-thread story: this blocks the network thread until the
# main thread runs the callable and returns its result.
_run_on_main = maya.utils.executeInMainThreadWithResult


def _get_info() -> dict:
    try:
        version = cmds.about(version=True)
    except Exception:  # noqa: BLE001
        version = ""
    try:
        scene = cmds.file(query=True, sceneName=True) or "(unsaved)"
    except Exception:  # noqa: BLE001
        scene = ""
    return default_info("maya", str(version), scene)


def _exec_globals() -> dict:
    import maya.mel as mel
    import maya.api.OpenMaya as om
    return {"cmds": cmds, "mel": mel, "om": om}


def start(register_port: int | None = None) -> None:
    """Connect to the daemon and register. Dial ``register_port`` if
    given, else read it from the config file."""
    global _server
    if _server is not None:
        return
    _server = DCCServer(
        kind="maya",
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
