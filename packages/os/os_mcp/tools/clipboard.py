"""Clipboard read/write tools."""

from __future__ import annotations

from os_mcp.server import mcp
from os_mcp._platform import (
    read_clipboard as _read,
    write_clipboard as _write,
)


@mcp.tool()
def read_clipboard() -> dict:
    """Read the system clipboard as text.

    Returns:
        {"text": str}
    """
    return {"text": _read()}


@mcp.tool()
def write_clipboard(text: str) -> dict:
    """Write text to the system clipboard.

    Args:
        text: The string to place on the clipboard.

    Returns:
        {"written": True, "length": int}
    """
    _write(text)
    return {"written": True, "length": len(text)}
