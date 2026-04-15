"""Window inspection and manipulation tools."""

from __future__ import annotations

from os_mcp.server import mcp
from os_mcp._platform import (
    bring_window_to_front as _bring,
    check_window_responding as _responding,
    detect_modal_dialogs as _dialogs,
)


@mcp.tool()
def is_window_responding(pid: int) -> dict:
    """Check if a process's main window is responding.

    Uses Win32 IsHungAppWindow under the hood. The check is OS-level and
    cannot hang, even if the process is completely frozen.

    Args:
        pid: Process ID.

    Returns:
        {"pid": int, "responding": bool | None}
        (responding is None if the process has no visible titled window)
    """
    return {"pid": pid, "responding": _responding(pid)}


@mcp.tool()
def find_modal_dialogs(pid: int) -> dict:
    """Find modal/popup dialog windows belonging to a process.

    Useful when a DCC appears stuck — often a modal error dialog is
    blocking its main window and the DCC cannot process further commands
    until the dialog is dismissed. This returns dialog titles and child
    control text so the agent can describe what's on screen to the user
    or decide to force-kill.

    Args:
        pid: Process ID.

    Returns:
        {"pid": int,
         "dialogs": [{"title", "class", "child_text", "width", "height", "owned"}, ...]}
    """
    return {"pid": pid, "dialogs": _dialogs(pid)}


@mcp.tool()
def bring_window_to_front(pid: int) -> dict:
    """Bring a process's main window to the foreground and restore it.

    Calls Win32 ShowWindow(SW_RESTORE) + SetForegroundWindow.

    Args:
        pid: Process ID.

    Returns:
        {"pid": int, "brought_to_front": bool}
    """
    return _bring(pid)
