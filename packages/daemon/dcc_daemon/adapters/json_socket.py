"""JSON-socket adapter — newline-delimited JSON to the vendored plugin.

Used by DCCs that embed ``plugins/common/dcc_socket_server.py`` (Blender,
Unreal). The plugin speaks:

    request : {"command": "execute_python", "params": {"code": "..."}}\\n
    reply   : {"result": ...}\\n   or   {"error": "..."}\\n

plus ``ping``, ``get_info`` and ``screenshot`` commands. This adapter
knows nothing DCC-specific; the plugin runs the code on the DCC's main
thread and normalizes the result to JSON before replying.
"""

from __future__ import annotations

import json
import logging
import socket
from typing import Any

from dcc_daemon.adapters.base import Adapter, DCCError

logger = logging.getLogger(__name__)

_RECV_SIZE = 1024 * 1024
_CONNECT_TIMEOUT = 10.0
# execute_python calls can be long (renders, sims). The daemon-level
# heartbeat/async layer keeps the agent unblocked; the socket read itself
# uses a generous timeout.
_CALL_TIMEOUT = 600.0


class JsonSocketAdapter(Adapter):
    def __init__(self, port: int, host: str = "127.0.0.1"):
        super().__init__(port, host)
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
        result = self._send("screenshot")
        if isinstance(result, dict):
            result = result.get("png_base64") or result.get("data") or ""
        return str(result)
