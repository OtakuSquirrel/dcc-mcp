"""Session management tools — discover, list, and manage Blender sessions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from dcc_mcp_core.registry import is_pid_alive, is_port_in_use

from blender_mcp.server import mcp, blender, registry, config, get_session_id


@mcp.tool()
def list_all_sessions() -> dict:
    """List all registered Blender MCP sessions on this machine.

    Returns:
        Dict with list of sessions and summary info.
    """
    cleaned = registry.cleanup_stale_sessions()
    sessions = registry.list_sessions()

    return {
        "sessions": sessions,
        "total": len(sessions),
        "cleaned_stale": cleaned,
        "current_session_id": get_session_id(),
    }


@mcp.tool()
def disconnect_blender() -> dict:
    """Disconnect from the current Blender instance.

    The MCP server stays running. Blender's socket server stays active.

    Returns:
        Dict with disconnection status.
    """
    session_id = get_session_id()
    was_connected = blender.is_connected()
    port = blender._active_port

    blender.release(port=port)

    import blender_mcp.server as _srv
    _srv._session_id = blender._session_id

    return {
        "disconnected": was_connected,
        "session_id": session_id,
        "port": port,
        "remaining_connections": blender.list_connections(),
    }


@mcp.tool()
def get_current_session() -> dict:
    """Get information about this MCP server's Blender session.

    Returns:
        Dict with session ID, port, connection status.
    """
    session_id = get_session_id()
    session_info = None
    if session_id:
        session_info = registry.get_session(session_id)

    return {
        "session_id": session_id,
        "port": blender.port,
        "connected": blender.is_connected(),
        "registry_info": session_info,
        "connections": blender.list_connections(),
    }


@mcp.tool()
def cleanup_stale_sessions() -> dict:
    """Remove sessions whose processes are no longer running.

    Returns:
        Dict with cleaned session IDs.
    """
    cleaned = registry.cleanup_stale_sessions()
    remaining = registry.list_sessions()

    return {
        "cleaned": cleaned,
        "cleaned_count": len(cleaned),
        "remaining_sessions": len(remaining),
    }


@mcp.tool()
def scan_ports() -> dict:
    """Scan the configured port range and report Blender + MCP server status.

    Returns:
        Dict with port range, active ports with dual status, free count.
    """
    min_port, max_port = config.get_port_range()
    sessions = registry.list_sessions()
    session_ports = {s["port"]: s for s in sessions if "port" in s}

    ports = list(range(min_port, max_port + 1))

    with ThreadPoolExecutor(max_workers=30) as executor:
        listening_flags = list(executor.map(is_port_in_use, ports))

    session_pids_alive = {}
    for port_num, s in session_ports.items():
        mcp_pid = s.get("pid")
        session_pids_alive[port_num] = is_pid_alive(mcp_pid) if mcp_pid else False

    active = []
    free_count = 0
    next_free_port = None

    for port, is_listening in zip(ports, listening_flags):
        has_session = port in session_ports

        if has_session:
            s = session_ports[port]
            mcp_alive = session_pids_alive.get(port, False)
            if mcp_alive and is_listening:
                status = "linked"
            elif mcp_alive and not is_listening:
                status = "mcp_idle"
            elif not mcp_alive and is_listening:
                status = "orphaned"
            else:
                status = "stale"
            active.append({
                "port": port, "status": status,
                "blender_socket": is_listening, "mcp_server": mcp_alive,
                "session_id": s.get("session_id"), "mcp_pid": s.get("pid"),
            })
        elif is_listening:
            active.append({
                "port": port, "status": "listening",
                "blender_socket": True, "mcp_server": False,
            })
        else:
            free_count += 1
            if next_free_port is None:
                next_free_port = port

    return {
        "range": [min_port, max_port],
        "active": active,
        "free_count": free_count,
        "next_free_port": next_free_port,
    }


@mcp.tool()
def get_pool_status() -> dict:
    """Get a summary of the Blender instance pool.

    Returns:
        Dict with idle/active counts and port details.
    """
    min_port, max_port = config.get_port_range()
    sessions = registry.list_sessions()
    session_ports = {s["port"]: s for s in sessions if "port" in s}

    session_pids_alive = {}
    for port_num, s in session_ports.items():
        mcp_pid = s.get("pid")
        session_pids_alive[port_num] = is_pid_alive(mcp_pid) if mcp_pid else False

    ports = list(range(min_port, max_port + 1))
    with ThreadPoolExecutor(max_workers=30) as executor:
        listening_flags = list(executor.map(is_port_in_use, ports))

    idle = []
    active = []

    for port, is_listening in zip(ports, listening_flags):
        if not is_listening:
            continue
        has_live_session = port in session_ports and session_pids_alive.get(port, False)
        entry = {"port": port}
        if has_live_session:
            entry["session_id"] = session_ports[port].get("session_id")
            active.append(entry)
        else:
            idle.append(entry)

    return {
        "idle": idle, "idle_count": len(idle),
        "active": active, "active_count": len(active),
    }


@mcp.tool()
def acquire_from_pool() -> dict:
    """Acquire an idle Blender instance from the pool and connect.

    Returns:
        Dict with connection info, or error if pool is empty.
    """
    min_port, max_port = config.get_port_range()
    sessions = registry.list_sessions()

    live_session_ports = set()
    for s in sessions:
        mcp_pid = s.get("pid")
        if s.get("port") and mcp_pid and is_pid_alive(mcp_pid):
            live_session_ports.add(s["port"])

    ports = list(range(min_port, max_port + 1))
    with ThreadPoolExecutor(max_workers=30) as executor:
        listening_flags = list(executor.map(is_port_in_use, ports))

    idle_ports = [
        p for p, listening in zip(ports, listening_flags)
        if listening and p not in live_session_ports
    ]

    if not idle_ports:
        return {
            "status": "pool_empty",
            "message": "No idle Blender instances. Use warm_pool() or start_blender().",
        }

    target_port = idle_ports[0]
    blender.connect(port=target_port)

    import blender_mcp.server as _srv
    _srv._session_id = blender._session_id

    return {
        "status": "acquired",
        "port": target_port,
        "session_id": blender._session_id,
    }


@mcp.tool()
def connect_to_blender(port: int) -> dict:
    """Connect to a Blender instance on a specific port.

    Args:
        port: The socket port of the Blender addon.

    Returns:
        Dict with connection status.
    """
    blender.connect(port=port)

    import blender_mcp.server as _srv
    _srv._session_id = blender._session_id

    return {
        "status": "connected",
        "port": port,
        "session_id": blender._session_id,
        "connections": blender.list_connections(),
    }


@mcp.tool()
def switch_active_blender(port: int) -> dict:
    """Switch which Blender instance receives commands.

    Args:
        port: The port of the Blender instance to switch to.

    Returns:
        Dict with switch status.
    """
    blender.switch_active(port)

    import blender_mcp.server as _srv
    _srv._session_id = blender._session_id

    return {
        "status": "switched",
        "active_port": port,
        "connections": blender.list_connections(),
    }
