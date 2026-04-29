"""Blender lifecycle tools — start, stop, warm-pool, install.

Cross-platform: Windows uses `start "" "..."` to detach Blender via
cmd.exe; macOS/Linux use direct Popen with start_new_session=True.

No is_blender_healthy (use os-mcp.check_dcc_health(port) instead).
No force-kill in stop_blender (use os-mcp.kill_process(pid, force=True)).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from dcc_mcp_core import unified_config

from blender_mcp.server import mcp, blender

# Per-DCC fallback when the user has never run the Tauri manager (no
# ~/.dcc-mcp/config.toml exists yet). Once the manager has materialised
# the file, the unified pool wins — see `_port_range()` below.
_FALLBACK_PORT_RANGE: tuple[int, int] = (19811, 19910)


def _port_range() -> tuple[int, int]:
    """Resolved port range for Blender allocation.

    If ``~/.dcc-mcp/config.toml`` exists, use the unified pool the
    Tauri manager writes there (single shared range across all DCCs).
    Otherwise stay on Blender's historical 19811–19910 so behaviour
    on a stock checkout is unchanged.
    """
    if unified_config.exists():
        p = unified_config.port_range()
        return (p.min, p.max)
    return _FALLBACK_PORT_RANGE


# ── Helpers ──


def _clean_env_for_dcc() -> dict[str, str]:
    """Strip Python-related env vars.

    DCC apps bundle their own Python. Inheriting PYTHONPATH/PYTHONHOME
    from the MCP server causes them to freeze or crash.
    """
    env = os.environ.copy()
    for key in list(env):
        if key.upper().startswith(("PYTHON", "VIRTUAL_ENV", "CONDA")):
            del env[key]
    return env


def _find_blender(given_path: str | None = None) -> str:
    """Locate the Blender executable, trying platform-specific defaults."""
    if given_path:
        p = Path(given_path)
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"Blender not found at {given_path}")

    # macOS default install
    if sys.platform == "darwin":
        mac_default = Path("/Applications/Blender.app/Contents/MacOS/Blender")
        if mac_default.exists():
            return str(mac_default)

    # Windows default install
    if sys.platform == "win32":
        for base in [
            Path("C:/Program Files/Blender Foundation"),
            Path("C:/Program Files (x86)/Blender Foundation"),
        ]:
            if base.exists():
                for d in sorted(base.iterdir(), reverse=True):
                    exe = d / "blender.exe"
                    if exe.exists():
                        return str(exe)

    # Anywhere on PATH
    path = shutil.which("blender")
    if path:
        return path

    raise FileNotFoundError(
        "Blender executable not found. Pass blender_path explicitly, or "
        "install Blender to a default location."
    )


def _is_port_listening(port: int, timeout: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("localhost", port)) == 0


def _allocate_free_port() -> int:
    """Scan the port range, return the first free port."""
    lo, hi = _port_range()
    for p in range(lo, hi + 1):
        if not _is_port_listening(p):
            return p
    raise RuntimeError(f"No free port in range {lo}-{hi}")


def _launch_blender(blender_path: str, env: dict) -> subprocess.Popen:
    """Cross-platform Blender launch, detached from this process."""
    if sys.platform == "win32":
        # Windows: `start ""` wraps in cmd.exe so Blender detaches cleanly
        return subprocess.Popen(
            f'start "" "{blender_path}"', shell=True, env=env
        )
    # macOS / Linux: direct Popen with new session keeps Blender alive
    # even if this MCP server exits.
    return subprocess.Popen(
        [blender_path],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# ── Tools ──


@mcp.tool()
def start_blender(
    blender_path: str | None = None,
    wait_for_addon: bool = True,
    timeout: int = 60,
    port: int | None = None,
) -> dict:
    """Launch a new Blender instance with the MCP socket server enabled.

    The Blender addon (plugins/blender/) must be installed for this to
    work. When launched with BLENDER_MCP_ENABLED=1, the addon auto-starts
    its socket server on the port given by BLENDER_MCP_PORT.

    IMPORTANT: this tool returns the allocated `port` — Claude should
    remember it to address this Blender instance in subsequent tool calls
    (e.g. create_object(port=...)).

    Args:
        blender_path: Path to the Blender executable. Auto-detects on
                      macOS (/Applications/Blender.app/...) and Windows
                      (C:\\Program Files\\Blender Foundation\\...) if None.
        wait_for_addon: Wait until the addon's socket server is reachable.
        timeout: Max seconds to wait for the addon.
        port: Specific port to use. If None, picks the first free port
              in the configured range (19811-19910).

    Returns:
        {"status": "ready" | "launched" | "timeout",
         "port": int, "pid": int, "blender_path": str,
         "startup_seconds": int | None}
    """
    if port is None:
        port = _allocate_free_port()
    elif _is_port_listening(port):
        raise RuntimeError(f"Port {port} is already in use")

    blender_exe = _find_blender(blender_path)

    env = _clean_env_for_dcc()
    env["BLENDER_MCP_PORT"] = str(port)
    env["BLENDER_MCP_ENABLED"] = "1"

    proc = _launch_blender(blender_exe, env)
    blender.register_process(port, proc)

    result = {
        "status": "launched",
        "port": port,
        "pid": proc.pid,
        "blender_path": blender_exe,
    }

    if not wait_for_addon:
        return result

    start_time = time.time()
    while time.time() - start_time < timeout:
        if _is_port_listening(port):
            try:
                # Warm the connection cache so the first tool call is fast
                blender.send_command(port, "ping")
                result["status"] = "ready"
                result["startup_seconds"] = int(time.time() - start_time)
                return result
            except Exception:
                pass
        time.sleep(0.5)

    result["status"] = "timeout"
    return result


@mcp.tool()
def stop_blender(port: int) -> dict:
    """Gracefully stop a Blender instance.

    Sends a `quit` command through the MCP protocol. Does NOT force-kill.
    If Blender is unresponsive, use os-mcp.kill_process(pid, force=True)
    — that is the OS-level force kill path.

    Args:
        port: Port of the Blender instance to stop.

    Returns:
        {"status": "quit_sent" | "not_running", "port": int,
         "pid": int | None}
    """
    if not _is_port_listening(port):
        blender.drop_connection(port)
        blender.unregister_process(port)
        return {"status": "not_running", "port": port, "pid": None}

    proc = blender.get_process(port)
    pid = proc.pid if proc else None

    try:
        blender.send_command(port, "quit")
    except Exception:
        # quit likely closed the connection before we got a reply; fine.
        pass

    blender.drop_connection(port)
    if proc:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Don't force-kill here — that's os-mcp's job.
            pass
    blender.unregister_process(port)

    return {"status": "quit_sent", "port": port, "pid": pid}


@mcp.tool()
def ensure_blender_ready(
    port: int | None = None,
    blender_path: str | None = None,
    timeout: int = 60,
) -> dict:
    """Ensure a Blender instance is running.

    If `port` is given and something is listening there, verify it
    responds and return. If `port` is given but nothing is listening,
    launch a new Blender on that port. If `port` is None, launch a new
    Blender on the first free port.

    Args:
        port: Specific port to use or check. None = pick the first free
              port in the configured range.
        blender_path: Path to Blender. Auto-detects if None.
        timeout: Max seconds to wait for launch.

    Returns:
        Same shape as start_blender().
    """
    if port is not None and _is_port_listening(port):
        try:
            blender.send_command(port, "ping")
            return {
                "status": "ready",
                "port": port,
                "pid": None,
                "startup_seconds": 0,
            }
        except Exception:
            # Port is listening but not speaking our protocol — start fresh
            pass
    return start_blender(
        blender_path=blender_path, timeout=timeout, port=port
    )


@mcp.tool()
def warm_pool(count: int = 1, blender_path: str | None = None) -> dict:
    """Launch N Blender instances with the MCP socket server enabled.

    Returns the allocated ports. Claude should remember them to operate
    on specific instances later.

    Args:
        count: Number of instances to launch.
        blender_path: Path to Blender. Auto-detects if None.

    Returns:
        {"launched": [{"port": int, "pid": int}, ...],
         "count": int, "errors": [str, ...]}
    """
    blender_exe = _find_blender(blender_path)
    env_base = _clean_env_for_dcc()
    env_base["BLENDER_MCP_ENABLED"] = "1"

    launched: list[dict] = []
    errors: list[str] = []
    for _ in range(count):
        try:
            port = _allocate_free_port()
            env = dict(env_base)
            env["BLENDER_MCP_PORT"] = str(port)
            proc = _launch_blender(blender_exe, env)
            blender.register_process(port, proc)
            launched.append({"port": port, "pid": proc.pid})
        except Exception as e:
            errors.append(str(e))

    return {"launched": launched, "count": len(launched), "errors": errors}


@mcp.tool()
def install_addon(blender_path: str | None = None) -> dict:
    """Return instructions for installing the blender_mcp addon.

    The addon source is at plugins/blender/ in the dcc-mcp repo. Copy
    or symlink it into Blender's addons directory, then enable in
    Preferences > Add-ons. Phase 3 will automate this via the Tauri
    manager.

    Returns:
        {"addon_source": str, "message": str,
         "target_hint": {"macos": str, "windows": str}}
    """
    # Walk up from tools/lifecycle.py to the repo root, then find plugins/blender/
    addon_src = (
        Path(__file__).resolve().parents[4] / "plugins" / "blender"
    )
    if not addon_src.exists():
        raise FileNotFoundError(
            f"Addon source not found at {addon_src} — wrong repo layout?"
        )

    return {
        "addon_source": str(addon_src),
        "message": (
            f"Copy {addon_src} (as 'blender_mcp/') into Blender's "
            "scripts/addons/ directory and enable it in Preferences > "
            "Add-ons. Tauri manager will automate this in a later phase."
        ),
        "target_hint": {
            "macos": "~/Library/Application Support/Blender/<version>/scripts/addons/blender_mcp/",
            "windows": "%APPDATA%\\Blender Foundation\\Blender\\<version>\\scripts\\addons\\blender_mcp\\",
        },
    }
