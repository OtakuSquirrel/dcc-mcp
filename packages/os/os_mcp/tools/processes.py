"""Process inspection and management tools."""

from __future__ import annotations

from dcc_mcp_core import unified_config

from os_mcp.server import mcp
from os_mcp._platform import (
    get_exe_path,
    get_main_window_title,
    get_process_info as _get_info,
    kill_process as _kill,
    list_listening_ports,
)

# Map lowercase executable name → DCC type string
_DCC_EXE_PATTERNS: dict[str, str] = {
    "blender.exe": "blender",
    "blender": "blender",
    "houdinifx.exe": "houdini",
    "houdini.exe": "houdini",
    "houdinicore.exe": "houdini",
    "hython.exe": "houdini",
    "houdinifx": "houdini",
    "houdini": "houdini",
    "hython": "houdini",
    "maya.exe": "maya",
    "maya": "maya",
    "unrealeditor.exe": "ue",
    "ue4editor.exe": "ue",
    "ue5editor.exe": "ue",
    "unrealeditor": "ue",
}

def _identify_dcc(exe_path: str | None) -> str | None:
    if not exe_path:
        return None
    exe_name = exe_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return _DCC_EXE_PATTERNS.get(exe_name)


def _default_port_range() -> tuple[int, int]:
    """Resolve the default scan range from the unified config.

    Falls back to the same defaults Rust uses (18811-20899) when the
    file is missing — the values stay in lockstep across languages
    via :mod:`dcc_mcp_core.unified_config`.
    """
    p = unified_config.port_range()
    return (p.min, p.max)


@mcp.tool()
def list_dcc_instances(
    port_min: int | None = None,
    port_max: int | None = None,
) -> dict:
    """Scan a port range and list all running DCC instances.

    Identifies DCC type by inspecting each listening process's executable
    name. Only returns ports whose owning process matches a known DCC
    executable (blender, houdini, maya, unreal). Unknown listeners are
    filtered out.

    Args:
        port_min: Start of port range (inclusive). Defaults to the
            ``[ports].min`` value in ``~/.dcc-mcp/config.toml``.
        port_max: End of port range (inclusive). Defaults to the
            ``[ports].max`` value in ``~/.dcc-mcp/config.toml``.

    Returns:
        {"instances": [{port, pid, dcc_type, exe_path, window_title}, ...],
         "count": N}
    """
    if port_min is None or port_max is None:
        default_min, default_max = _default_port_range()
        if port_min is None:
            port_min = default_min
        if port_max is None:
            port_max = default_max
    port_to_pid = list_listening_ports(port_min, port_max)
    instances = []
    for port in sorted(port_to_pid.keys()):
        pid = port_to_pid[port]
        exe = get_exe_path(pid)
        dcc_type = _identify_dcc(exe)
        if dcc_type is None:
            continue
        instances.append({
            "port": port,
            "pid": pid,
            "dcc_type": dcc_type,
            "exe_path": exe,
            "window_title": get_main_window_title(pid) or "",
        })
    return {"instances": instances, "count": len(instances)}


@mcp.tool()
def get_process_info(pid: int) -> dict:
    """Get detailed info about a process.

    Args:
        pid: Process ID.

    Returns:
        {"pid", "exe_path", "memory_mb", "cpu_percent", "start_time"}
    """
    return _get_info(pid)


@mcp.tool()
def kill_process(pid: int, force: bool = False) -> dict:
    """Terminate a process by PID.

    On Windows, this uses TerminateProcess regardless of the `force`
    flag — there is no OS-level distinction between graceful and force
    kill for an arbitrary third-party process. For graceful shutdown of a
    DCC, use the DCC's own `stop_<dcc>` tool (which sends a quit command
    through the DCC protocol).

    Args:
        pid: Process ID to terminate.
        force: Kept for API symmetry; effectively ignored on Windows.

    Returns:
        {"killed": bool, "pid": int, "method": "terminate"}
    """
    return _kill(pid, force)
