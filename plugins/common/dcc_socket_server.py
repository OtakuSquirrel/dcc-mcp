"""Unified DCC-side connector for the dcc-daemon (registration model).

Every DCC (Blender, Houdini, Unreal, Maya) embeds this. On launch it
**dials the daemon** (outbound TCP to the daemon's DCC-register port),
registers itself, and holds one long connection. The daemon then pushes
request frames down that connection; this connector runs them on the
DCC's main thread and replies. When the connection drops (daemon
restart, network blip) it reconnects with backoff.

This inverts the old model — the DCC no longer listens on a port and the
daemon no longer scans. One held connection per DCC; the daemon keeps a
live registry keyed by a daemon-assigned instance id.

Wire (newline-delimited JSON, both directions):

    DCC → daemon (once, on connect):
        {"type":"register","kind","pid","version","file"}
    daemon → DCC (reply):
        {"type":"registered","instance_id":"..."}
    daemon → DCC (per request):
        {"id":N,"command":"execute_python","params":{"code":"..."}}
    DCC → daemon (reply, tagged by id):
        {"id":N,"result":...}  |  {"id":N,"error":"...","traceback":"..."}

The one thing that differs per DCC is ``run_on_main`` (how code reaches
the main thread); everything here is shared and pure stdlib so it can be
vendored into any DCC's Python environment.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import traceback
from typing import Any, Callable

logger = logging.getLogger("dcc_daemon.plugin")

_RECONNECT_START = 1.0
_RECONNECT_MAX = 15.0
_RECV_SIZE = 1024 * 1024


class DCCServer:
    """Connects to the daemon, registers, and serves pushed requests.

    (Name kept for continuity; it "serves" execute_python requests, now
    over a reversed, daemon-initiated connection.)
    """

    def __init__(
        self,
        *,
        kind: str,
        run_on_main: Callable[[Callable[[], Any]], Any],
        get_info: Callable[[], dict],
        screenshot: Callable[[], str] | None = None,
        exec_globals: Callable[[], dict] | None = None,
        host: str = "127.0.0.1",
    ):
        """
        Args:
            kind: "blender" | "houdini" | "ue" | "maya".
            run_on_main: schedule fn on the DCC main thread, return result.
            get_info: identity dict (runs on main thread).
            screenshot: base64 PNG (runs on main thread). Optional.
            exec_globals: globals dict for execute_python (e.g. {"bpy": bpy}).
            host: daemon registration host. It defaults to localhost and
                may be set to an explicitly configured backend address.
        """
        self.kind = kind
        self._run_on_main = run_on_main
        self._get_info = get_info
        self._screenshot = screenshot
        self._exec_globals = exec_globals or (lambda: {})
        self.host = host
        self._sock: socket.socket | None = None
        self._running = False
        self.instance_id: str | None = None
        self.connected = False

    # ── lifecycle ──

    def start(self, register_port: int | None = None) -> None:
        """Begin connecting to the daemon in a background thread."""
        if self._running:
            return
        self._running = True
        port = register_port if register_port is not None else read_register_port()
        t = threading.Thread(
            target=self._connect_loop, args=(port,),
            name="dcc-daemon-conn", daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False
        self.connected = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # ── connection with reconnect/backoff ──

    def _connect_loop(self, register_port: int) -> None:
        backoff = _RECONNECT_START
        while self._running:
            try:
                self._session(register_port)
                backoff = _RECONNECT_START  # clean drop → reset
            except OSError as e:
                logger.debug("[%s] connect failed (%s)", self.kind, e)
            if not self._running:
                break
            time.sleep(backoff)
            backoff = min(backoff * 2, _RECONNECT_MAX)

    def _session(self, register_port: int) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((self.host, register_port))
        sock.settimeout(None)
        self._sock = sock

        # Register — gather identity on the main thread.
        info = self._run_on_main(self._get_info)
        hello = {"type": "register", **info}
        sock.sendall((json.dumps(hello) + "\n").encode("utf-8"))

        buffer = b""
        while self._running:
            # Read at least the registration reply, then request frames.
            try:
                chunk = sock.recv(_RECV_SIZE)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                self._on_frame(sock, line.decode("utf-8"))
        self.connected = False
        self.instance_id = None
        try:
            sock.close()
        except OSError:
            pass
        self._sock = None

    def _on_frame(self, sock: socket.socket, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            return
        if frame.get("type") == "registered":
            self.instance_id = frame.get("instance_id")
            self.connected = True
            logger.info("[%s] registered with daemon as %s", self.kind, self.instance_id)
            return
        # A request frame: handle in its own thread so a long execute or a
        # wedged main thread never blocks reading the next request (e.g. a
        # health heartbeat the daemon sends concurrently).
        threading.Thread(
            target=self._serve_request, args=(sock, frame), daemon=True).start()

    def _serve_request(self, sock: socket.socket, frame: dict) -> None:
        req_id = frame.get("id")
        response = self._handle(frame)
        response["id"] = req_id
        try:
            sock.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except OSError:
            pass

    # ── request handling (unchanged dispatch; runs code on main thread) ──

    def _handle(self, request: dict) -> dict:
        command = request.get("command", "")
        params = request.get("params") or {}
        try:
            if command == "ping":
                # Heartbeat that touches the MAIN THREAD, so a wedged DCC
                # fails it (the network thread alone would falsely pass).
                return {"result": self._run_on_main(lambda: "pong")}
            if command == "get_info":
                return {"result": self._run_on_main(self._get_info)}
            if command == "execute_python":
                return {"result": self._run_on_main(lambda: self._exec(params.get("code", "")))}
            if command == "screenshot":
                if self._screenshot is None:
                    return {"error": f"screenshot not supported for {self.kind}"}
                return {"result": {"png_base64": self._run_on_main(self._screenshot)}}
            return {"error": f"unknown command: {command}"}
        except Exception as e:  # noqa: BLE001 — report any DCC-side error to the daemon
            return {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}

    def _exec(self, code: str) -> Any:
        g = self._exec_globals()
        g.setdefault("__builtins__", __builtins__)
        local: dict[str, Any] = {}
        exec(code, g, local)  # noqa: S102 — this IS the intended escape hatch
        result = local.get("result", g.get("result"))
        if result is None:
            return None
        try:
            json.dumps(result)
            return result
        except (TypeError, ValueError):
            return repr(result)


def default_info(kind: str, version: str, file: str = "") -> dict:
    return {"kind": kind, "version": version, "pid": os.getpid(), "file": file}


# Default register port — must match dcc_daemon.config.DEFAULT_REGISTER_PORT.
_DEFAULT_REGISTER_PORT = 18813


def read_register_port() -> int:
    """Read the daemon's DCC-register port from ``~/.dcc-mcp/config.toml``.

    Pure stdlib (``tomllib``, Python 3.11+, which every current DCC ships)
    so this file stays vendorable into any DCC. Falls back to the default
    if the file is missing/malformed — in lock-step with
    dcc_daemon.config.register_port().
    """
    path = os.path.expanduser("~/.dcc-mcp/config.toml")
    if not os.path.exists(path):
        return _DEFAULT_REGISTER_PORT
    try:
        import tomllib
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:  # noqa: BLE001 — any read/parse error → default
        return _DEFAULT_REGISTER_PORT
    d = data.get("daemon") or {}
    try:
        return int(d.get("dcc_register_port", _DEFAULT_REGISTER_PORT))
    except (TypeError, ValueError):
        return _DEFAULT_REGISTER_PORT
