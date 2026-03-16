"""Houdini lifecycle tools — start, stop, health, setup.

Rewrite using dcc-mcp-core health checks.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from dcc_mcp_core.health import check_health, is_port_open

from houdini_mcp.server import mcp, houdini, registry, config, get_session_id, set_port


_PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "plugins" / "houdini"
_STARTUP_SCRIPT = _PLUGIN_DIR / "houdini_mcp_startup.py"

_HOOK_TAG = "# [HoudiniMCP]"
_HOOK_LINE = (
    'exec(open(hou.homeHoudiniDirectory() + "/scripts/houdini_mcp_startup.py").read())'
    f'  {_HOOK_TAG}'
)


def _find_houdini_installations() -> list[dict]:
    results = []
    seen = set()
    for search_path_str in config.get_dcc_search_paths():
        search_root = Path(search_path_str)
        if not search_root.exists():
            continue
        for d in sorted(search_root.iterdir(), reverse=True):
            if d.name.startswith("Houdini ") and d.is_dir():
                version = d.name.replace("Houdini ", "")
                if version in seen:
                    continue
                hython = d / "bin" / "hython.exe"
                gui_exe = d / "bin" / "houdinifx.exe"
                if not gui_exe.exists():
                    gui_exe = d / "bin" / "houdini.exe"
                entry = {"version": version, "dir": str(d)}
                if gui_exe.exists():
                    entry["gui_exe"] = str(gui_exe)
                if hython.exists():
                    entry["hython"] = str(hython)
                if gui_exe.exists() or hython.exists():
                    seen.add(version)
                    results.append(entry)
    return results


def _get_houdini_prefs_dir(version: str) -> Path:
    match = re.match(r"(\d+\.\d+)", version)
    if not match:
        raise ValueError(f"Cannot parse Houdini version: {version}")
    major_minor = match.group(1)
    if os.name == "nt":
        return Path.home() / "Documents" / f"houdini{major_minor}"
    return Path.home() / f"houdini{major_minor}"


@mcp.tool()
def install_startup_scripts(version: str | None = None) -> dict:
    """Install MCP startup hook into Houdini's scripts directory."""
    if not _STARTUP_SCRIPT.exists():
        raise FileNotFoundError(f"Startup script not found: {_STARTUP_SCRIPT}")

    installations = _find_houdini_installations()
    if not installations:
        raise RuntimeError("No Houdini installations found.")

    if version:
        targets = [i for i in installations if i["version"].startswith(version)]
        if not targets:
            raise ValueError(f"Version '{version}' not found. Available: {[i['version'] for i in installations]}")
    else:
        targets = installations

    results = {}
    for inst in targets:
        ver = inst["version"]
        prefs_dir = _get_houdini_prefs_dir(ver)
        scripts_dir = prefs_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        dest = scripts_dir / "houdini_mcp_startup.py"
        shutil.copy2(str(_STARTUP_SCRIPT), str(dest))

        hook_file = scripts_dir / "456.py"
        if hook_file.exists():
            content = hook_file.read_text(encoding="utf-8")
            if _HOOK_TAG not in content:
                if not content.endswith("\n"):
                    content += "\n"
                content += f"\n{_HOOK_LINE}\n"
                hook_file.write_text(content, encoding="utf-8")
                status = "injected"
            else:
                status = "already_present"
        else:
            hook_file.write_text(f"{_HOOK_LINE}\n", encoding="utf-8")
            status = "created"

        results[ver] = {"scripts_dir": str(scripts_dir), "hook_status": status}

    return {"status": "installed", "versions": results}


@mcp.tool()
def uninstall_startup_scripts(version: str) -> dict:
    """Remove MCP startup hook from Houdini."""
    prefs_dir = _get_houdini_prefs_dir(version)
    scripts_dir = prefs_dir / "scripts"

    hook_file = scripts_dir / "456.py"
    if hook_file.exists():
        content = hook_file.read_text(encoding="utf-8")
        if _HOOK_TAG in content:
            lines = [l for l in content.splitlines() if _HOOK_TAG not in l]
            while lines and not lines[-1].strip():
                lines.pop()
            hook_file.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")

    startup = scripts_dir / "houdini_mcp_startup.py"
    removed = []
    if startup.exists():
        startup.unlink()
        removed.append(str(startup))

    return {"status": "uninstalled", "version": version, "removed": removed}


@mcp.tool()
def get_houdini_status() -> dict:
    """Check Houdini process and connection status."""
    rpyc_reachable = is_port_open(houdini.port) if houdini.port else False
    proc = houdini.get_process()
    process_alive = proc is not None and proc.poll() is None

    return {
        "rpyc_reachable": rpyc_reachable,
        "rpyc_port": houdini.port,
        "session_id": get_session_id(),
        "managed_process_alive": process_alive,
        "mcp_connected": houdini.is_connected(),
        "installed_versions": _find_houdini_installations(),
        "connections": houdini.list_connections(),
    }


@mcp.tool()
def start_houdini(
    version: str | None = None,
    mode: str = "gui",
    wait_for_rpyc: bool = True,
    timeout: int = 120,
    port: int | None = None,
) -> dict:
    """Launch Houdini and wait for RPyC. Takes 30-90s for GUI mode."""
    if port is None:
        port = registry.allocate_port()

    if is_port_open(port):
        try:
            houdini.connect(port=port)
            return {"status": "already_running", "port": port, "session_id": get_session_id()}
        except Exception:
            pass

    installations = _find_houdini_installations()
    if not installations:
        raise RuntimeError("No Houdini installation found.")

    inst = None
    if version:
        for i in installations:
            if i["version"].startswith(version):
                inst = i
                break
        if not inst:
            raise ValueError(f"Version {version} not found.")
    else:
        inst = installations[0]
        version = inst["version"]

    env = os.environ.copy()
    env["HOUDINI_MCP_ENABLED"] = "1"
    env["HOUDINI_MCP_AGENT_LAUNCH"] = "1"
    env["HOUDINI_MCP_PORT"] = str(port)

    if mode == "hython":
        hython = inst.get("hython")
        if not hython:
            raise RuntimeError(f"hython.exe not found for {version}")
        script = (
            f"import hrpyc, time; hrpyc.start_server(port={port}); "
            f"[time.sleep(1) for _ in iter(int,1)]"
        )
        proc = subprocess.Popen(
            [hython, "-c", script], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        gui_exe = inst.get("gui_exe")
        if not gui_exe:
            raise RuntimeError(f"houdinifx.exe not found for {version}")
        proc = subprocess.Popen(f'start "" "{gui_exe}"', shell=True, env=env)

    houdini.register_process(port, proc)
    set_port(port)

    result = {"status": "launched", "version": version, "mode": mode, "pid": proc.pid, "port": port}

    if not wait_for_rpyc:
        return result

    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_open(port):
            try:
                houdini.connect(port=port)
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
def stop_houdini(force: bool = False, port: int | None = None) -> dict:
    """Stop the Houdini process."""
    target_port = port or houdini._active_port
    target_conn = houdini._connections.get(target_port) if target_port else None
    session_id = target_conn._session_id if target_conn else get_session_id()

    if not force and target_conn and target_conn.is_connected():
        try:
            target_conn.hou.exit(exit_code=0, suppress_save_prompt=True)
        except Exception:
            pass

    # Kill the actual DCC process (not the cmd.exe wrapper).
    # On Windows, `start "" "houdinifx.exe"` creates a cmd.exe child,
    # so proc.kill() only kills cmd.exe. We need to kill the real PID.
    dcc_pid = None

    # Try to get DCC PID from session registry
    if session_id:
        for s in registry.list_sessions():
            if s.get("session_id") == session_id:
                dcc_pid = s.get("dcc_pid")
                break

    # Try to get DCC PID from health check (OS-level port→PID lookup)
    if dcc_pid is None and target_port:
        from dcc_mcp_core.health import find_pid_for_port
        dcc_pid = find_pid_for_port(target_port, sessions=registry.list_sessions())

    # Kill the DCC process directly via OS
    if dcc_pid:
        try:
            import signal
            os.kill(dcc_pid, signal.SIGTERM if not force else signal.SIGTERM)
            # On Windows, os.kill with SIGTERM calls TerminateProcess
        except (OSError, ProcessLookupError):
            pass

    # Also kill the wrapper process if we have one
    proc = houdini.get_process(target_port)
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
        houdini.unregister_process(target_port)
        houdini.disconnect(port=target_port)
    if session_id:
        registry.unregister_session(session_id)

    return {"status": "stopped", "port": target_port, "dcc_pid": dcc_pid}


@mcp.tool()
def ensure_houdini_ready(version: str | None = None, mode: str = "gui", timeout: int = 120) -> dict:
    """Start Houdini if not running (idempotent)."""
    if houdini.is_connected():
        return {"status": "ready", "port": houdini._explicit_port, "session_id": get_session_id()}
    try:
        houdini.connect()
        return {"status": "ready", "port": houdini._explicit_port, "session_id": get_session_id()}
    except Exception:
        pass
    return start_houdini(version=version, mode=mode, timeout=timeout)


@mcp.tool()
def warm_pool(instances: list[dict], mode: str = "gui", timeout: int = 120) -> dict:
    """Batch-launch idle Houdini instances."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    launched = []
    errors = []

    for spec in instances:
        version = spec.get("version")
        count = spec.get("count", 1)
        for _ in range(count):
            try:
                port = registry.allocate_port()
                # Fire and forget
                installations = _find_houdini_installations()
                inst = installations[0] if installations else None
                if version:
                    inst = next((i for i in installations if i["version"].startswith(version)), inst)
                if not inst:
                    raise RuntimeError("No Houdini found")

                env = os.environ.copy()
                env["HOUDINI_MCP_ENABLED"] = "1"
                env["HOUDINI_MCP_AGENT_LAUNCH"] = "1"
                env["HOUDINI_MCP_PORT"] = str(port)

                if mode == "hython":
                    script = f"import hrpyc, time; hrpyc.start_server(port={port}); [time.sleep(1) for _ in iter(int,1)]"
                    subprocess.Popen(
                        [inst["hython"], "-c", script], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    )
                else:
                    subprocess.Popen(f'start "" "{inst["gui_exe"]}"', shell=True, env=env)

                launched.append({"port": port, "version": inst["version"]})
            except Exception as e:
                errors.append(str(e))

    return {"launched": len(launched), "ports": [l["port"] for l in launched], "errors": errors}


@mcp.tool()
def is_houdini_healthy(port: int | None = None) -> dict:
    """Check if Houdini is responsive. Every check has a hard timeout."""
    target_port = port or houdini._active_port or houdini._explicit_port
    if not target_port:
        return {"verdict": "dead", "details": "No port configured."}

    import rpyc

    def _rpyc_ping(host, p):
        try:
            conn = rpyc.classic.connect(host, p)
            conn.ping()
            conn.close()
            return True
        except Exception:
            return False

    return check_health(target_port, ping_fn=_rpyc_ping, sessions=registry.list_sessions())
