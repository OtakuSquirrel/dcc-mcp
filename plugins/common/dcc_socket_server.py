"""Unified minimal socket server for DCC plugins.

Every DCC (Blender, Houdini, Unreal) embeds this same server. It speaks
newline-delimited JSON and implements exactly four commands:

    ping         -> "pong"
    get_info     -> {"kind","version","pid","file", ...}
    execute_python -> runs code, returns whatever it sets as `result`
    screenshot   -> {"png_base64": "..."}

The one thing that differs per DCC is HOW code reaches the main thread
(bpy.app.timers vs hdefereval vs UE tick). The host passes in a
``run_on_main`` callable that takes a 0-arg function and returns its
result synchronously; everything else is shared.

This module has NO DCC imports — it is pure stdlib so it can be vendored
into any DCC's Python environment.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import traceback
from typing import Any, Callable

logger = logging.getLogger("dcc_daemon.plugin")


class DCCServer:
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
            kind: "blender" | "houdini" | "ue".
            run_on_main: schedule fn on the DCC main thread, return its result.
            get_info: returns identity dict (runs on main thread).
            screenshot: returns base64 PNG (runs on main thread). Optional.
            exec_globals: returns the globals dict for execute_python
                (e.g. {"bpy": bpy}). Runs on main thread.
            host: bind host — keep 127.0.0.1; the daemon reaches DCCs
                locally, cloud access goes through the daemon tunnel.
        """
        self.kind = kind
        self._run_on_main = run_on_main
        self._get_info = get_info
        self._screenshot = screenshot
        self._exec_globals = exec_globals or (lambda: {})
        self.host = host
        self._server_sock: socket.socket | None = None
        self._running = False
        self._threads: list[threading.Thread] = []
        self.port: int | None = None

    # ── lifecycle ──

    def start(self, port: int) -> None:
        if self._running:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # NOTE: no SO_REUSEADDR — we WANT bind() to fail on a port another
        # instance already holds, so claim_and_start can move to the next.
        sock.bind((self.host, port))
        sock.listen(8)
        self._server_sock = sock
        self._running = True
        self.port = port
        t = threading.Thread(target=self._accept_loop, name="dcc-mcp-accept", daemon=True)
        t.start()
        self._threads.append(t)
        logger.info("[%s] socket server listening on %s:%d", self.kind, self.host, port)

    def claim_and_start(self, ports: list[int] | None = None) -> int:
        """Scan a pool of ports and bind the first free one.

        This is how a DCC plugin picks its port at launch: read the pool
        (from ``~/.dcc-mcp/config.toml`` if ``ports`` is None), try each
        in order, and hold the first that binds. Returns the claimed port;
        raises RuntimeError if the whole pool is taken.
        """
        pool = ports if ports is not None else read_dcc_ports()
        for port in pool:
            try:
                self.start(port)
                return port
            except OSError:
                continue  # taken by another instance; try the next
        raise RuntimeError(f"[{self.kind}] no free port in pool {pool}")

    def stop(self) -> None:
        self._running = False
        self.port = None
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

    # ── networking (background threads; only exec hops to main thread) ──

    def _accept_loop(self) -> None:
        while self._running and self._server_sock is not None:
            try:
                client, _ = self._server_sock.accept()
            except OSError:
                break
            ct = threading.Thread(target=self._client_loop, args=(client,), daemon=True)
            ct.start()
            self._threads.append(ct)

    def _client_loop(self, client: socket.socket) -> None:
        buffer = b""
        with client:
            while self._running:
                try:
                    chunk = client.recv(1024 * 1024)
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    response = self._handle(line.decode("utf-8"))
                    try:
                        client.sendall((json.dumps(response) + "\n").encode("utf-8"))
                    except OSError:
                        return

    def _handle(self, raw: str) -> dict:
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"error": f"invalid JSON: {e}"}
        command = request.get("command", "")
        params = request.get("params") or {}
        try:
            if command == "ping":
                return {"result": "pong"}
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


# Default pool — must match dcc_daemon.config.DEFAULT_DCC_PORTS.
_DEFAULT_DCC_PORTS = list(range(18811, 18831))


def read_dcc_ports() -> list[int]:
    """Read the DCC port pool from ``~/.dcc-mcp/config.toml``.

    Pure stdlib (``tomllib``, Python 3.11+, which every current DCC ships)
    so this file stays vendorable into any DCC. Accepts an explicit
    ``ports.dcc = [...]`` list or a ``ports.min``/``ports.max`` range.
    Falls back to the default block if the file is missing/malformed —
    keeping this in lock-step with dcc_daemon.config.dcc_ports().
    """
    import os.path

    path = os.path.expanduser("~/.dcc-mcp/config.toml")
    if not os.path.exists(path):
        return list(_DEFAULT_DCC_PORTS)
    try:
        import tomllib
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:  # noqa: BLE001 — any read/parse error → defaults
        return list(_DEFAULT_DCC_PORTS)
    p = data.get("ports") or {}
    raw = p.get("dcc")
    if isinstance(raw, list) and raw:
        try:
            return [int(x) for x in raw]
        except (TypeError, ValueError):
            return list(_DEFAULT_DCC_PORTS)
    if "min" in p and "max" in p:
        try:
            lo, hi = int(p["min"]), int(p["max"])
            if lo <= hi:
                return list(range(lo, hi + 1))
        except (TypeError, ValueError):
            pass
    return list(_DEFAULT_DCC_PORTS)
