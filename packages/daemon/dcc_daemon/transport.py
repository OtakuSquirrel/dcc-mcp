"""Unified TCP+JSON transport to a DCC instance.

Every DCC plugin (Blender, Houdini, UE) runs the same minimal socket
server that speaks newline-delimited JSON:

    request : {"command": "execute_python", "params": {"code": "..."}}\\n
    reply   : {"result": ...}\\n   or   {"error": "..."}\\n

There is only ONE command that matters — ``execute_python`` — plus
``ping`` and ``get_info`` for liveness/identity. This module knows
nothing DCC-specific; the port identifies the instance, the plugin on
the other end runs the code on its own main thread.

Connections are opened lazily per port, reused, and dropped on error
(reconnect on next call). Per-port locks serialize concurrent calls to
the same instance — a DCC main thread can only do one thing at a time.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Any

logger = logging.getLogger(__name__)

_RECV_SIZE = 1024 * 1024
_CONNECT_TIMEOUT = 10.0
# execute_python calls can be long (renders, sims). The daemon-level
# heartbeat/async layer is responsible for not blocking the agent; the
# socket read itself uses a generous timeout.
_CALL_TIMEOUT = 600.0


class DCCConnection:
    """A single newline-delimited JSON socket to one DCC on a known port."""

    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.host = host
        self.port = port
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        self.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_CONNECT_TIMEOUT)
        sock.connect((self.host, self.port))
        sock.settimeout(_CALL_TIMEOUT)
        self._socket = sock

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _send(self, command: str, params: dict | None = None) -> Any:
        if self._socket is None:
            raise ConnectionError("not connected")
        request: dict[str, Any] = {"command": command}
        if params:
            request["params"] = params
        payload = (json.dumps(request) + "\n").encode("utf-8")
        try:
            self._socket.sendall(payload)
            line = self._recv_line()
            response = json.loads(line)
        except (OSError, json.JSONDecodeError) as e:
            self.close()
            raise ConnectionError(f"transport error on port {self.port}: {e}") from e
        if isinstance(response, dict) and "error" in response:
            raise DCCError(str(response["error"]), traceback=response.get("traceback"))
        return response.get("result") if isinstance(response, dict) else response

    def _recv_line(self) -> str:
        buffer = b""
        while True:
            if self._socket is None:
                raise ConnectionError("connection lost during recv")
            chunk = self._socket.recv(_RECV_SIZE)
            if not chunk:
                raise ConnectionError("connection closed by DCC")
            buffer += chunk
            if b"\n" in buffer:
                line, _ = buffer.split(b"\n", 1)
                return line.decode("utf-8")

    # ── the three commands every plugin implements ──

    def execute_python(self, code: str) -> Any:
        return self._send("execute_python", {"code": code})

    def ping(self) -> bool:
        try:
            return self._send("ping") is not None
        except (ConnectionError, DCCError):
            return False

    def get_info(self) -> dict:
        result = self._send("get_info")
        return result if isinstance(result, dict) else {}

    def screenshot(self) -> str:
        """Return a base64-encoded PNG of the DCC viewport/render."""
        result = self._send("screenshot")
        if isinstance(result, dict):
            result = result.get("png_base64") or result.get("data") or ""
        return str(result)


class DCCError(RuntimeError):
    """The DCC executed the command but it raised inside the DCC process."""

    def __init__(self, message: str, traceback: str | None = None):
        super().__init__(message)
        self.traceback = traceback


class TransportPool:
    """Lazy, port-keyed connection cache with per-port locks.

    No 'active port'. Every call names a port. The daemon owns exactly
    one of these for the whole process.
    """

    def __init__(self):
        self._conns: dict[int, DCCConnection] = {}
        self._locks: dict[int, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    def _lock_for(self, port: int) -> threading.Lock:
        with self._registry_lock:
            return self._locks.setdefault(port, threading.Lock())

    def execute_python(self, port: int, code: str) -> Any:
        """Run ``code`` inside the DCC on ``port`` and return its result."""
        lock = self._lock_for(port)
        with lock:
            conn = self._get_or_open(port)
            try:
                return conn.execute_python(code)
            except ConnectionError:
                self._conns.pop(port, None)
                # one automatic reconnect+retry — DCC may have restarted
                conn = self._get_or_open(port)
                return conn.execute_python(code)

    def ping(self, port: int) -> bool:
        lock = self._lock_for(port)
        with lock:
            try:
                conn = self._get_or_open(port)
            except OSError:
                return False
            ok = conn.ping()
            if not ok:
                self._conns.pop(port, None)
            return ok

    def get_info(self, port: int) -> dict:
        lock = self._lock_for(port)
        with lock:
            conn = self._get_or_open(port)
            return conn.get_info()

    def screenshot(self, port: int) -> str:
        lock = self._lock_for(port)
        with lock:
            conn = self._get_or_open(port)
            return conn.screenshot()

    def _get_or_open(self, port: int) -> DCCConnection:
        conn = self._conns.get(port)
        if conn is None:
            conn = DCCConnection(port)
            conn.connect()
            self._conns[port] = conn
        return conn

    def drop(self, port: int) -> None:
        conn = self._conns.pop(port, None)
        if conn is not None:
            conn.close()
