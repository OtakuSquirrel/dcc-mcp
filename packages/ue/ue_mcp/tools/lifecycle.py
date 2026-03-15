"""UE lifecycle tools — health checks and connection management."""

from __future__ import annotations

from dcc_mcp_core.health import check_health, is_port_open

from ue_mcp.server import mcp, ue, registry, get_session_id


@mcp.tool()
def ensure_ue_ready() -> dict:
    """Ensure UE is running and connected.

    Tries to connect to UE. Unlike Blender/Houdini, UE is typically
    started manually with the Remote Execution plugin enabled.
    """
    if ue.is_connected():
        return {"status": "ready", "port": ue._explicit_port, "session_id": get_session_id()}

    try:
        ue.connect()
        return {"status": "ready", "port": ue._explicit_port, "session_id": get_session_id()}
    except Exception as e:
        return {
            "status": "not_connected",
            "error": str(e),
            "message": (
                "Could not connect to UE. Ensure Unreal Engine is running "
                "with the Python Remote Execution plugin enabled."
            ),
        }


@mcp.tool()
def is_ue_healthy(port: int | None = None) -> dict:
    """Check if UE is responsive."""
    target_port = port or ue._active_port or ue._explicit_port
    if not target_port:
        return {"verdict": "dead", "details": "No port configured."}

    def _ping_fn(host, p):
        import socket
        import struct
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            sock.connect((host, p))
            code = b"print('pong')"
            sock.sendall(struct.pack("!I", len(code)) + code)
            return True
        except Exception:
            return False
        finally:
            sock.close()

    return check_health(target_port, ping_fn=_ping_fn, sessions=registry.list_sessions())
