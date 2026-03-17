"""Blender lifecycle tools — start, stop, health, addon management."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from dcc_mcp_core.health import check_health, is_port_open

from blender_mcp.server import mcp, blender, registry, config, get_session_id


@mcp.tool()
def start_blender(
    blender_path: str | None = None,
    wait_for_addon: bool = True,
    timeout: int = 60,
    port: int | None = None,
) -> dict:
    """Launch Blender with the MCP addon enabled.

    IMPORTANT: Blender takes 10-30 seconds to start up and load the addon.
    This is normal. The tool handles waiting automatically.

    Args:
        blender_path: Path to blender.exe. Auto-detects if None.
        wait_for_addon: Wait for the addon's socket server to be reachable.
        timeout: Max seconds to wait (default 60).
        port: Specific port for the addon. If None, auto-allocates.

    Returns:
        Dict with process info and connection status.
    """
    if port is None:
        port = registry.allocate_port()

    if is_port_open(port):
        try:
            blender.connect(port=port)
            return {
                "status": "already_running",
                "port": port,
                "session_id": get_session_id(),
            }
        except Exception:
            pass

    if blender_path is None:
        blender_path = _find_blender()

    env = _clean_env_for_dcc()
    env["BLENDER_MCP_PORT"] = str(port)
    env["BLENDER_MCP_ENABLED"] = "1"

    proc = subprocess.Popen(f'start "" "{blender_path}"', shell=True, env=env)

    blender.register_process(port, proc)

    result = {"status": "launched", "pid": proc.pid, "port": port}

    if not wait_for_addon:
        return result

    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_open(port):
            try:
                blender.connect(port=port)
                result["status"] = "ready"
                result["session_id"] = get_session_id()
                result["startup_seconds"] = int(time.time() - start_time)
                return result
            except Exception:
                pass
        time.sleep(0.5)

    result["status"] = "timeout"
    return result


@mcp.tool()
def stop_blender(force: bool = False, port: int | None = None) -> dict:
    """Stop the Blender process.

    Args:
        force: If True, force-kill. If False, try graceful shutdown.
        port: Specific port to stop. If None, stops the active connection.

    Returns:
        Dict with shutdown status.
    """
    target_port = port or blender._active_port
    target_conn = blender._connections.get(target_port) if target_port else None
    session_id = target_conn._session_id if target_conn else get_session_id()

    if not force and target_conn and target_conn.is_connected():
        try:
            target_conn.send_command("quit")
        except Exception:
            pass

    # On Windows with `start`, proc is cmd.exe (already exited).
    # Kill the real DCC process via session registry / port lookup.
    dcc_pid = None
    if session_id:
        for s in registry.list_sessions():
            if s.get("session_id") == session_id:
                dcc_pid = s.get("dcc_pid")
                break

    if dcc_pid is None and target_port:
        from dcc_mcp_core.health import find_pid_for_port
        dcc_pid = find_pid_for_port(target_port, sessions=registry.list_sessions())

    if dcc_pid:
        try:
            import signal
            os.kill(dcc_pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    proc = blender.get_process(target_port)
    if proc and proc.poll() is None:
        if force:
            proc.kill()
        else:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if target_port:
        blender.unregister_process(target_port)
        blender.disconnect(port=target_port)
    if session_id:
        registry.unregister_session(session_id)

    return {"status": "stopped", "port": target_port, "dcc_pid": dcc_pid}


@mcp.tool()
def ensure_blender_ready(
    blender_path: str | None = None,
    timeout: int = 60,
) -> dict:
    """Ensure Blender is running and connected. Start if needed."""
    if blender.is_connected():
        return {"status": "ready", "port": blender._explicit_port, "session_id": get_session_id()}

    try:
        blender.connect()
        return {"status": "ready", "port": blender._explicit_port, "session_id": get_session_id()}
    except Exception:
        pass

    return start_blender(blender_path=blender_path, timeout=timeout)


@mcp.tool()
def is_blender_healthy(port: int | None = None) -> dict:
    """Check if Blender is responsive."""
    target_port = port or blender._active_port or blender._explicit_port
    if target_port is None:
        return {"verdict": "dead", "details": "No port configured."}

    def _ping_fn(host, p):
        import socket as _s
        sock = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        sock.settimeout(3)
        try:
            sock.connect((host, p))
            sock.sendall(b'{"command": "ping"}\n')
            data = sock.recv(4096)
            return b"result" in data or b"pong" in data
        finally:
            sock.close()

    return check_health(target_port, ping_fn=_ping_fn, sessions=registry.list_sessions())


@mcp.tool()
def warm_pool(count: int = 1, blender_path: str | None = None) -> dict:
    """Batch-launch idle Blender instances into the pool."""
    if blender_path is None:
        blender_path = _find_blender()

    launched, errors = [], []
    for _ in range(count):
        try:
            port = registry.allocate_port()
            env = _clean_env_for_dcc()
            env["BLENDER_MCP_PORT"] = str(port)
            env["BLENDER_MCP_ENABLED"] = "1"
            proc = subprocess.Popen(f'start "" "{blender_path}"', shell=True, env=env)
            launched.append({"port": port, "pid": proc.pid})
        except Exception as e:
            errors.append(str(e))

    return {"launched": launched, "count": len(launched), "errors": errors}


@mcp.tool()
def install_addon(blender_path: str | None = None) -> dict:
    """Install/enable the MCP addon in Blender's addon directory."""
    addon_src = Path(__file__).resolve().parent.parent.parent.parent.parent / "plugins" / "blender"
    if not addon_src.exists():
        raise FileNotFoundError(f"Addon source not found: {addon_src}")

    return {
        "status": "info",
        "addon_source": str(addon_src),
        "message": (
            "Copy the plugins/blender/ directory to Blender's "
            "scripts/addons/blender_mcp_addon/ and enable it in preferences."
        ),
    }


def _clean_env_for_dcc() -> dict:
    """Return os.environ copy with Python-related vars stripped.

    DCC apps bundle their own Python. Inheriting PYTHONPATH/PYTHONHOME
    from the MCP server causes them to freeze or crash.
    """
    env = os.environ.copy()
    for key in list(env):
        if key.upper().startswith(("PYTHON", "VIRTUAL_ENV", "CONDA")):
            del env[key]
    return env


def _find_blender() -> str:
    """Find blender.exe on the system."""
    import shutil
    path = shutil.which("blender")
    if path:
        return path

    common_paths = [
        Path("C:/Program Files/Blender Foundation"),
        Path("C:/Program Files (x86)/Blender Foundation"),
    ]
    for base in common_paths:
        if base.exists():
            for d in sorted(base.iterdir(), reverse=True):
                exe = d / "blender.exe"
                if exe.exists():
                    return str(exe)

    raise FileNotFoundError(
        "blender.exe not found. Pass blender_path explicitly or add Blender to PATH."
    )
