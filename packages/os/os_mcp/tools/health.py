"""Composite OS-level health check for DCC instances."""

from __future__ import annotations

from os_mcp.server import mcp
from os_mcp._platform import (
    check_window_responding,
    detect_modal_dialogs,
    find_pid_for_port,
    get_exe_path,
    is_port_open,
    sample_cpu_percent,
)


@mcp.tool()
def check_dcc_health(port: int) -> dict:
    """Comprehensive OS-level diagnostic for a DCC instance on the given port.

    Use this when a DCC tool call has timed out, is behaving oddly, or
    when you need to decide whether to continue waiting or force-kill. Runs
    Win32 signals (IsHungAppWindow, GetProcessTimes for CPU, EnumWindows
    for modal dialogs) and returns a verdict so the agent can choose the
    next step.

    Does NOT ping the DCC protocol itself — os-mcp has no knowledge of
    DCC protocols. For protocol-level checks, call a DCC tool and use the
    heartbeat pattern.

    Args:
        port: TCP port the DCC is listening on.

    Returns:
        {
            "verdict": "healthy" | "busy" | "hung" | "blocked" | "dead" | "no_protocol",
            "details": "...",
            "pid": int | None,
            "exe_path": str | None,
            "port_listening": bool,
            "window_responding": bool | None,
            "cpu_percent": float | None,
            "modal_dialogs": [...]
        }
    """
    port_listening = is_port_open(port)
    pid = find_pid_for_port(port)

    if pid is None:
        return {
            "verdict": "dead",
            "details": f"No process listening on port {port}",
            "pid": None,
            "exe_path": None,
            "port_listening": port_listening,
            "window_responding": None,
            "cpu_percent": None,
            "modal_dialogs": [],
        }

    exe_path = get_exe_path(pid)
    window_responding = check_window_responding(pid)
    cpu = sample_cpu_percent(pid, interval=0.5)
    dialogs = detect_modal_dialogs(pid)

    # Verdict
    if dialogs:
        verdict = "blocked"
        titles = ", ".join(d.get("title", "?") for d in dialogs)
        details = f"Modal dialog(s) blocking interaction: {titles}"
    elif window_responding is False:
        if cpu is not None and cpu > 10:
            verdict = "busy"
            details = f"Window frozen, CPU {cpu}% — likely computing"
        else:
            cpu_str = f"{cpu}%" if cpu is not None else "unknown"
            verdict = "hung"
            details = f"Window not responding, CPU {cpu_str} — appears hung"
    elif not port_listening:
        verdict = "no_protocol"
        details = "Window responding but no process listening on port"
    else:
        verdict = "healthy"
        details = "Process responding, window alive, no blocking dialogs"

    return {
        "verdict": verdict,
        "details": details,
        "pid": pid,
        "exe_path": exe_path,
        "port_listening": port_listening,
        "window_responding": window_responding,
        "cpu_percent": cpu,
        "modal_dialogs": dialogs,
    }
