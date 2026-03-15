"""Session management tools for UE MCP."""

from __future__ import annotations

from ue_mcp.server import mcp, ue, registry, get_session_id


@mcp.tool()
def list_all_sessions() -> dict:
    """List all registered UE MCP sessions."""
    cleaned = registry.cleanup_stale_sessions()
    sessions = registry.list_sessions()
    return {"sessions": sessions, "total": len(sessions), "cleaned_stale": cleaned}


@mcp.tool()
def get_current_session() -> dict:
    """Get this MCP server's session info."""
    session_id = get_session_id()
    return {
        "session_id": session_id,
        "port": ue.port,
        "connected": ue.is_connected(),
        "registry_info": registry.get_session(session_id) if session_id else None,
    }


@mcp.tool()
def connect_to_ue(port: int) -> dict:
    """Connect to a UE instance on a specific port."""
    ue.connect(port=port)
    import ue_mcp.server as _srv
    _srv._session_id = ue._session_id
    return {"status": "connected", "port": port, "session_id": ue._session_id}


@mcp.tool()
def disconnect_ue() -> dict:
    """Disconnect from current UE instance."""
    was_connected = ue.is_connected()
    port = ue._active_port
    ue.release(port=port)
    return {"disconnected": was_connected, "port": port}
