"""Daemon configuration — thin reader over ``~/.dcc-mcp/config.toml``.

The Tauri manager (and the daemon's own WebUI) own writes; the daemon
reads. Kept intentionally tiny: the daemon needs the port pool to scan,
the DCC kind→port-range hints, and the local HTTP bind address.

Falls back to hard defaults if the file is missing or malformed, so a
fresh machine behaves identically to a configured one.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Per-DCC conventional port ranges (used to guess kind from a port and to
# scope scans). The unified pool spans them all.
DCC_PORT_RANGES: dict[str, tuple[int, int]] = {
    "houdini": (18811, 18899),
    "blender": (19811, 19899),
    "ue": (20811, 20899),
}

DEFAULT_POOL = (18811, 20899)
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765


class Ports(NamedTuple):
    min: int
    max: int


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


def port_pool() -> Ports:
    data = _read()
    p = data.get("ports") or {}
    try:
        return Ports(int(p.get("min", DEFAULT_POOL[0])),
                     int(p.get("max", DEFAULT_POOL[1])))
    except (TypeError, ValueError):
        return Ports(*DEFAULT_POOL)


def http_bind() -> tuple[str, int]:
    data = _read()
    d = data.get("daemon") or {}
    host = str(d.get("host", DEFAULT_HTTP_HOST))
    try:
        port = int(d.get("port", DEFAULT_HTTP_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_HTTP_PORT
    return host, port


def kind_for_port(port: int) -> str | None:
    """Best-effort DCC kind from a port, using conventional ranges."""
    for kind, (lo, hi) in DCC_PORT_RANGES.items():
        if lo <= port <= hi:
            return kind
    return None
