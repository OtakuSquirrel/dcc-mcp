"""Read-only Python view of the unified ``~/.dcc-mcp/config.toml``.

The Tauri manager owns writes to this file; Python MCP servers read from
it at startup (port range) and on every tool invocation (disabled tools,
via :class:`~dcc_mcp_core.tool_registry.ToolRegistry`).

Schema mirrors :mod:`tauri-manager/src-tauri/src/config.rs`::

    [ports]
    min = 18811
    max = 20899

    [tools.blender]
    disabled = ["execute_blender_code"]

    [tools.os]
    disabled = []

If the file is missing or malformed, every accessor returns the same
defaults the Rust side does — Python servers therefore behave identically
on a fresh machine where the manager has never run.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


# Defaults match :class:`config::Ports::default` in Rust + ``DEFAULT_CONFIG``
# in ``tauri-manager/src/lib/config.ts``. Keep all three in sync.
DEFAULT_PORT_MIN = 18811
DEFAULT_PORT_MAX = 20899


class Ports(NamedTuple):
    min: int
    max: int


def config_path() -> Path:
    """Return ``~/.dcc-mcp/config.toml`` (without checking for existence)."""
    return Path.home() / ".dcc-mcp" / "config.toml"


def exists() -> bool:
    """True iff the unified config file is present on disk."""
    return config_path().exists()


def _read() -> dict:
    """Parse the file, returning ``{}`` on any error.

    Caller-side parse failures are silent (logged at warning level) so
    that a hand-edited corrupt file falls back to defaults rather than
    crashing every MCP server. The Tauri manager surfaces the same
    error to the user via the UI; fixing it there propagates to Python.
    """
    path = config_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.warning("Failed to read %s, using defaults: %s", path, e)
        return {}


def port_range() -> Ports:
    """Return the configured (or default) port pool as a NamedTuple."""
    data = _read()
    p = data.get("ports") or {}
    try:
        return Ports(
            int(p.get("min", DEFAULT_PORT_MIN)),
            int(p.get("max", DEFAULT_PORT_MAX)),
        )
    except (TypeError, ValueError):
        return Ports(DEFAULT_PORT_MIN, DEFAULT_PORT_MAX)


def has_disabled_tools_section(mcp_name: str) -> bool:
    """True iff ``[tools.<mcp_name>]`` is explicitly present.

    Distinguishes "user has never touched this server's tools" (fall
    back to legacy DCCConfig) from "user explicitly enabled everything"
    (empty disabled list — authoritative).
    """
    data = _read()
    tools = data.get("tools") or {}
    return mcp_name in tools


def disabled_tools(mcp_name: str) -> list[str]:
    """Return the disabled-tool list for an MCP server.

    Empty list if the section is missing or malformed. Callers wanting
    to distinguish "absent" from "explicitly empty" should use
    :func:`has_disabled_tools_section` first.
    """
    data = _read()
    tools = data.get("tools") or {}
    section = tools.get(mcp_name) or {}
    raw = section.get("disabled", [])
    if not isinstance(raw, list):
        return []
    return [str(t) for t in raw if isinstance(t, (str, bytes))]
