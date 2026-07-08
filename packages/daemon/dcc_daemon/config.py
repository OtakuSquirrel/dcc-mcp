"""Daemon configuration — thin reader over ``~/.dcc-mcp/config.toml``.

In the registration model DCCs dial the daemon, so there is no port pool
to configure. The knobs are the two ports the daemon listens on:

    [daemon]
    host = "127.0.0.1"
    port = 8765              # MCP-over-HTTP for agents
    dcc_register_port = 8766 # DCCs dial here to register

Falls back to hard defaults if the file is missing or malformed, so a
fresh machine behaves identically to a configured one.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765
DEFAULT_REGISTER_PORT = 8766


def config_path() -> Path:
    return Path.home() / ".dcc-mcp" / "config.toml"


def _read() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.warning("failed to read %s, using defaults: %s", path, e)
        return {}


def _daemon_section() -> dict:
    return _read().get("daemon") or {}


def http_bind() -> tuple[str, int]:
    d = _daemon_section()
    host = str(d.get("host", DEFAULT_HTTP_HOST))
    try:
        port = int(d.get("port", DEFAULT_HTTP_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_HTTP_PORT
    return host, port


def register_bind() -> tuple[str, int]:
    """Host + port the DCC registration hub listens on (localhost)."""
    d = _daemon_section()
    host = str(d.get("host", DEFAULT_HTTP_HOST))
    try:
        port = int(d.get("dcc_register_port", DEFAULT_REGISTER_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_REGISTER_PORT
    return host, port
