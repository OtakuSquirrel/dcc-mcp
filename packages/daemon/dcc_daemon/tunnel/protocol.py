"""Tunnel frame protocol — the minimal wire format between a cloud agent,
the relay, and a home daemon.

Kept deliberately small: a request names a method (one of the daemon's
meta-operations) and carries params; a response carries a result or an
error, tagged by the request ``id`` so many can be in flight. The relay
never inspects the payload beyond ``id`` — it only routes between the
paired agent and daemon sockets.

Handshake (first message on every WS connection, before any frames):

    daemon → relay : {"role":"daemon","daemon_id":...,"token":<pair_token>}
    agent  → relay : {"role":"agent", "daemon_id":...,"token":<access_token>}
    relay  → either: {"ok":true} | {"ok":false,"error":...}
"""

from __future__ import annotations

import json
from typing import Any

ROLE_DAEMON = "daemon"
ROLE_AGENT = "agent"

# Methods a cloud agent may invoke — exactly the daemon's meta-tools.
METHODS = frozenset({"list_instances", "execute_python", "health", "screenshot"})


def encode(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def decode(raw: str | bytes) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("frame is not a JSON object")
    return obj


def make_hello(role: str, daemon_id: str, token: str) -> dict:
    return {"role": role, "daemon_id": daemon_id, "token": token}


def make_request(req_id: int, method: str, params: dict | None = None) -> dict:
    return {"id": req_id, "method": method, "params": params or {}}


def make_result(req_id: int, result: Any) -> dict:
    return {"id": req_id, "result": result}


def make_error(req_id: int | None, error: str, *, traceback: str | None = None) -> dict:
    frame: dict[str, Any] = {"id": req_id, "error": error}
    if traceback:
        frame["traceback"] = traceback
    return frame
