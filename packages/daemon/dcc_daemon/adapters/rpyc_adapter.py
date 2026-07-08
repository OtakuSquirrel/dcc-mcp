"""RPyC adapter — Houdini via its built-in ``hrpyc`` server.

Houdini is kept on RPyC precisely because it is **hot-pluggable**: a
user starts the server from Houdini's Python shell with

    import hrpyc; hrpyc.start_server(port=18811)

— no addon install, no restart, works on an already-open session. That
convenience is why we did not port Houdini to the vendored socket
server.

Everything the daemon needs (execute_python / get_info / screenshot) is
funneled through a single teleported helper that runs code on the
Houdini side and returns a JSON string, so no fragile netref proxies
cross the wire — only plain JSON values by value.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dcc_daemon.adapters.base import Adapter, DCCError

logger = logging.getLogger(__name__)

_CALL_TIMEOUT = 600.0


def _remote_exec(code):
    """Runs INSIDE Houdini (teleported). Returns a JSON string.

    Must be fully self-contained — teleport ships only this function's
    bytecode, so every import happens here.
    """
    import json

    g = {"__builtins__": __builtins__}
    try:
        import hou  # noqa: F401 — expose to executed code when present
        g["hou"] = hou
    except Exception:  # noqa: BLE001 — headless / no hou in test slave
        pass
    local = {}
    try:
        exec(code, g, local)  # noqa: S102 — this IS the intended escape hatch
    except Exception as e:  # noqa: BLE001
        import traceback as _tb
        return json.dumps({"error": f"{type(e).__name__}: {e}",
                           "traceback": _tb.format_exc()})
    result = local.get("result", g.get("result"))
    if result is None:
        return json.dumps({"result": None})
    try:
        json.dumps(result)
        return json.dumps({"result": result})
    except (TypeError, ValueError):
        return json.dumps({"result": repr(result)})


# Snippet run via _remote_exec to build the identity dict. Guards hou so
# it also works against a bare RPyC slave (tests).
_INFO_CODE = """
import os as _os
_info = {"kind": "houdini", "pid": _os.getpid(), "version": "", "file": ""}
try:
    import hou as _hou
    _info["version"] = _hou.applicationVersionString()
    _info["file"] = _hou.hipFile.path()
except Exception:
    pass
result = _info
"""

# Viewport grab → base64 PNG. Requires a running Houdini GUI with a
# scene viewer; raises inside Houdini otherwise (surfaced as DCCError).
_SCREENSHOT_CODE = """
import base64 as _b64, os as _os, tempfile as _tf
import hou as _hou
_path = _os.path.join(_tf.gettempdir(), "dcc_daemon_hou_shot.png")
_view = _hou.ui.paneTabOfType(_hou.paneTabType.SceneViewer)
_view.flipbookSettings().output(_path)
_view.flipbook(_view.curViewport(), _view.flipbookSettings())
with open(_path, "rb") as _f:
    result = _b64.b64encode(_f.read()).decode("ascii")
"""


class RpycAdapter(Adapter):
    def __init__(self, port: int, host: str = "127.0.0.1"):
        super().__init__(port, host)
        self._conn = None
        self._remote_fn = None

    def connect(self) -> None:
        import rpyc
        from rpyc.utils.classic import teleport_function

        self.close()
        conn = rpyc.classic.connect(self.host, self.port)
        conn._config["sync_request_timeout"] = _CALL_TIMEOUT
        self._conn = conn
        # Teleport the helper once; reused for every call on this connection.
        self._remote_fn = teleport_function(conn, _remote_exec)

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None
            self._remote_fn = None

    def _run(self, code: str) -> Any:
        if self._conn is None or self._remote_fn is None:
            raise ConnectionError("not connected")
        try:
            raw = self._remote_fn(code)
        except EOFError as e:
            self.close()
            raise ConnectionError(f"rpyc connection lost on port {self.port}: {e}") from e
        except Exception as e:  # noqa: BLE001 — rpyc surfaces remote errors here
            # A transport-level failure (not a user-code error, which is
            # reported in the JSON payload below).
            self.close()
            raise ConnectionError(f"rpyc error on port {self.port}: {e}") from e
        payload = json.loads(raw)
        if "error" in payload:
            raise DCCError(payload["error"], traceback=payload.get("traceback"))
        return payload.get("result")

    def execute_python(self, code: str) -> Any:
        return self._run(code)

    def ping(self) -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.ping()
            return True
        except Exception:  # noqa: BLE001
            self.close()
            return False

    def get_info(self) -> dict:
        info = self._run(_INFO_CODE)
        return info if isinstance(info, dict) else {"kind": "houdini"}

    def screenshot(self) -> str:
        return str(self._run(_SCREENSHOT_CODE))
