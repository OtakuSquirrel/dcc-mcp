"""Session management tools for Houdini — rewrite using dcc-mcp-core."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from dcc_mcp_core.registry import is_pid_alive, is_port_in_use

from houdini_mcp.server import mcp, houdini, registry, config, get_session_id


@mcp.tool()
def list_all_sessions() -> dict:
    """List all registered Houdini MCP sessions."""
    cleaned = registry.cleanup_stale_sessions()
    sessions = registry.list_sessions()
    return {"sessions": sessions, "total": len(sessions), "cleaned_stale": cleaned, "current_session_id": get_session_id()}


@mcp.tool()
def disconnect_houdini() -> dict:
    """Disconnect from the current Houdini instance."""
    session_id = get_session_id()
    was_connected = houdini.is_connected()
    port = houdini._active_port
    houdini.release(port=port)
    import houdini_mcp.server as _srv
    _srv._session_id = houdini._session_id
    return {"disconnected": was_connected, "session_id": session_id, "port": port}


@mcp.tool()
def get_current_session() -> dict:
    """Get this MCP server's session info."""
    session_id = get_session_id()
    return {
        "session_id": session_id,
        "port": houdini.port,
        "connected": houdini.is_connected(),
        "registry_info": registry.get_session(session_id) if session_id else None,
        "connections": houdini.list_connections(),
    }


@mcp.tool()
def cleanup_stale_sessions() -> dict:
    """Remove sessions with dead processes."""
    cleaned = registry.cleanup_stale_sessions()
    return {"cleaned": cleaned, "cleaned_count": len(cleaned), "remaining": len(registry.list_sessions())}


@mcp.tool()
def scan_ports() -> dict:
    """Scan port range for Houdini/MCP status."""
    min_port, max_port = config.get_port_range()
    sessions = registry.list_sessions()
    session_ports = {s["port"]: s for s in sessions if "port" in s}

    ports = list(range(min_port, max_port + 1))
    with ThreadPoolExecutor(max_workers=30) as executor:
        listening_flags = list(executor.map(is_port_in_use, ports))

    session_pids_alive = {p: is_pid_alive(s.get("pid")) if s.get("pid") else False for p, s in session_ports.items()}

    active = []
    free_count = 0
    next_free = None

    for port, listening in zip(ports, listening_flags):
        has_session = port in session_ports
        if has_session:
            mcp_alive = session_pids_alive.get(port, False)
            if mcp_alive and listening:
                status = "linked"
            elif mcp_alive:
                status = "mcp_idle"
            elif listening:
                status = "orphaned"
            else:
                status = "stale"
            active.append({"port": port, "status": status, "session_id": session_ports[port].get("session_id")})
        elif listening:
            active.append({"port": port, "status": "listening"})
        else:
            free_count += 1
            if next_free is None:
                next_free = port

    return {"range": [min_port, max_port], "active": active, "free_count": free_count, "next_free_port": next_free}


@mcp.tool()
def get_pool_status() -> dict:
    """Show idle/active Houdini instance counts."""
    min_port, max_port = config.get_port_range()
    sessions = registry.list_sessions()
    session_ports = {s["port"]: s for s in sessions if "port" in s}
    session_pids_alive = {p: is_pid_alive(s.get("pid")) if s.get("pid") else False for p, s in session_ports.items()}

    ports = list(range(min_port, max_port + 1))
    with ThreadPoolExecutor(max_workers=30) as executor:
        listening_flags = list(executor.map(is_port_in_use, ports))

    idle, active = [], []
    for port, listening in zip(ports, listening_flags):
        if not listening:
            continue
        if port in session_ports and session_pids_alive.get(port, False):
            active.append({"port": port, "session_id": session_ports[port].get("session_id")})
        else:
            idle.append({"port": port})

    return {"idle": idle, "idle_count": len(idle), "active": active, "active_count": len(active)}


@mcp.tool()
def acquire_from_pool(version: str | None = None) -> dict:
    """Grab an idle Houdini instance and connect."""
    min_port, max_port = config.get_port_range()
    sessions = registry.list_sessions()
    live_ports = {s["port"] for s in sessions if s.get("pid") and is_pid_alive(s["pid"])}

    ports = list(range(min_port, max_port + 1))
    with ThreadPoolExecutor(max_workers=30) as executor:
        listening_flags = list(executor.map(is_port_in_use, ports))

    idle_ports = [p for p, l in zip(ports, listening_flags) if l and p not in live_ports]

    if not idle_ports:
        return {"status": "pool_empty", "message": "No idle instances. Use warm_pool() or start_houdini()."}

    target = idle_ports[0]
    houdini.connect(port=target)
    import houdini_mcp.server as _srv
    _srv._session_id = houdini._session_id
    return {"status": "acquired", "port": target, "session_id": houdini._session_id}


@mcp.tool()
def adopt_idle(version: str | None = None) -> dict:
    """Kill stuck Houdini, adopt an idle replacement."""
    old_port = houdini._active_port
    killed = None
    if old_port:
        from houdini_mcp.tools.lifecycle import stop_houdini
        try:
            killed = stop_houdini(force=True, port=old_port)
        except Exception as e:
            killed = {"error": str(e)}

    acquired = acquire_from_pool(version=version)
    return {"killed": killed, "acquired": acquired}


@mcp.tool()
def get_mcp_config() -> dict:
    """Get MCP configuration."""
    return config.load()


@mcp.tool()
def update_mcp_config(
    human_auto_start: bool | None = None,
    agent_auto_start: bool | None = None,
    port_range_min: int | None = None,
    port_range_max: int | None = None,
) -> dict:
    """Update MCP configuration."""
    updates = {}
    if human_auto_start is not None:
        updates["human_launch"] = {"auto_start": human_auto_start}
    if agent_auto_start is not None:
        updates["agent_launch"] = {"auto_start": agent_auto_start}
    if port_range_min is not None or port_range_max is not None:
        current_range = config.get_port_range()
        updates["port_range"] = [
            port_range_min if port_range_min is not None else current_range[0],
            port_range_max if port_range_max is not None else current_range[1],
        ]
    if not updates:
        return config.load()
    return config.update(updates)


@mcp.tool()
def connect_to_houdini(port: int) -> dict:
    """Connect to a Houdini instance on a specific port."""
    houdini.connect(port=port)
    import houdini_mcp.server as _srv
    _srv._session_id = houdini._session_id
    return {"status": "connected", "port": port, "session_id": houdini._session_id, "connections": houdini.list_connections()}


@mcp.tool()
def switch_active_houdini(port: int) -> dict:
    """Switch which Houdini receives commands."""
    houdini.switch_active(port)
    import houdini_mcp.server as _srv
    _srv._session_id = houdini._session_id
    return {"status": "switched", "active_port": port, "connections": houdini.list_connections()}


@mcp.tool()
def list_houdini_connections() -> dict:
    """List all managed Houdini connections."""
    return {"connections": houdini.list_connections(), "active_port": houdini._active_port, "owned_ports": houdini.owned_ports()}
