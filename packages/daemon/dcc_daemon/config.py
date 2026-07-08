"""Daemon configuration — thin reader over ``~/.dcc-mcp/config.toml``.

The one knob that matters: **which ports belong to DCCs**. DCC plugins
scan this pool on launch and claim the first free one; the daemon scans
the same pool to discover what's running. All DCCs are equal — the port
carries no meaning beyond "a DCC might be here"; the plugin self-reports
its kind via ``get_info``.

Config schema::

    [ports]
    dcc = [18811, 18812, 18813, 18814, 18815, 18816]   # explicit list
    # -- or, as a convenience, a contiguous range --
    # min = 18811
    # max = 18830

    [daemon]
    host = "127.0.0.1"
    port = 8765

Falls back to hard defaults if the file is missing or malformed, so a
fresh machine behaves identically to a configured one.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

# Default DCC port pool: a small contiguous block. Enough for several
# concurrent instances; override in config.toml for more.
DEFAULT_DCC_PORTS = list(range(18811, 18831))
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765


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


def dcc_ports() -> list[int]:
    """The pool of ports DCCs may listen on.

    Accepts either an explicit ``dcc = [...]`` list or a ``min``/``max``
    range under ``[ports]``. Returns the default block if neither is set
    or the value is malformed.
    """
    p = _read().get("ports") or {}
    raw = p.get("dcc")
    if isinstance(raw, list) and raw:
        try:
            return [int(x) for x in raw]
        except (TypeError, ValueError):
            logger.warning("ports.dcc has non-int entries; using defaults")
            return list(DEFAULT_DCC_PORTS)
    if "min" in p and "max" in p:
        try:
            lo, hi = int(p["min"]), int(p["max"])
            if lo <= hi:
                return list(range(lo, hi + 1))
        except (TypeError, ValueError):
            pass
        logger.warning("ports.min/max malformed; using defaults")
    return list(DEFAULT_DCC_PORTS)


def http_bind() -> tuple[str, int]:
    d = _read().get("daemon") or {}
    host = str(d.get("host", DEFAULT_HTTP_HOST))
    try:
        port = int(d.get("port", DEFAULT_HTTP_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_HTTP_PORT
    return host, port
