"""Token store for the relay.

Maps ``daemon_id`` → its ``pair_token`` (proves a connecting daemon is
who it claims) and a set of ``access_tokens`` (authorize cloud agents to
reach that daemon). Backed by a JSON file so the relay is stateless
across restarts and the operator can provision tokens out-of-band.

    {
      "daemons": {
        "dccbox-a1b2c3": {
          "pair_token": "<secret>",
          "access_tokens": ["<agent-secret-1>", "<agent-secret-2>"]
        }
      }
    }

Comparisons use ``hmac.compare_digest`` to avoid timing leaks. This is
the entire trust model: possession of the pair_token authenticates a
daemon; possession of an access_token authorizes an agent for one daemon.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)


class TokenStore:
    def __init__(self, path: Path | None = None, data: dict | None = None):
        self._path = path
        self._data = data if data is not None else self._load(path)

    @staticmethod
    def _load(path: Path | None) -> dict:
        if path is None or not path.exists():
            return {"daemons": {}}
        try:
            with path.open("r", encoding="utf-8") as f:
                obj = json.load(f)
            if not isinstance(obj, dict) or "daemons" not in obj:
                raise ValueError("missing 'daemons' key")
            return obj
        except (OSError, ValueError, json.JSONDecodeError) as e:
            logger.error("token store %s unreadable (%s) — starting empty", path, e)
            return {"daemons": {}}

    def save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    # ── validation (used by the relay) ──

    def check_daemon(self, daemon_id: str, pair_token: str) -> bool:
        entry = self._data["daemons"].get(daemon_id)
        if not entry:
            return False
        return hmac.compare_digest(str(entry.get("pair_token", "")), pair_token)

    def check_agent(self, daemon_id: str, access_token: str) -> bool:
        entry = self._data["daemons"].get(daemon_id)
        if not entry:
            return False
        return any(
            hmac.compare_digest(str(t), access_token)
            for t in entry.get("access_tokens", [])
        )

    # ── provisioning (used by an operator / CLI) ──

    def register_daemon(self, daemon_id: str | None = None) -> tuple[str, str]:
        """Create a daemon entry; return (daemon_id, pair_token)."""
        daemon_id = daemon_id or f"dccbox-{secrets.token_hex(4)}"
        pair_token = secrets.token_urlsafe(32)
        self._data["daemons"][daemon_id] = {"pair_token": pair_token, "access_tokens": []}
        self.save()
        return daemon_id, pair_token

    def issue_access_token(self, daemon_id: str) -> str:
        entry = self._data["daemons"].get(daemon_id)
        if entry is None:
            raise KeyError(f"unknown daemon_id: {daemon_id}")
        token = secrets.token_urlsafe(32)
        entry.setdefault("access_tokens", []).append(token)
        self.save()
        return token
