"""Auto-run on scene load — ensures RPyC server is running for MCP communication.

This file is discovered by Houdini via the packages system (dcc_mcp.json),
which adds the parent directory to HOUDINI_PATH.

If RPyC was already started by 123.py, this is a no-op.
"""

import json
import os
import socket
from pathlib import Path


def _is_port_listening(port):
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("localhost", port)) == 0


def _get_config():
    """Read MCP config file."""
    config_file = Path.home() / "houdini_mcp" / "config.json"
    try:
        if config_file.exists():
            return json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _should_auto_start():
    """Check config to decide whether to start RPyC automatically."""
    if os.environ.get("HOUDINI_MCP_ENABLED", "0") != "1":
        return False

    is_agent = os.environ.get("HOUDINI_MCP_AGENT_LAUNCH", "0") == "1"
    config_key = "agent_launch" if is_agent else "human_launch"

    # Default: agent=True, human=False
    default = is_agent

    cfg = _get_config()
    return cfg.get(config_key, {}).get("auto_start", default)


def _find_free_port():
    """Find a free port in the configured range.

    Agent-launched Houdini uses the explicit HOUDINI_MCP_PORT.
    Human-launched Houdini scans the port range for the first available port.
    """
    explicit = os.environ.get("HOUDINI_MCP_PORT")
    if explicit:
        port = int(explicit)
        if not _is_port_listening(port):
            return port
        # Agent set a specific port but it's taken — don't scan, fail
        if os.environ.get("HOUDINI_MCP_AGENT_LAUNCH", "0") == "1":
            return None

    # Scan port range for a free port
    cfg = _get_config()
    port_range = cfg.get("port_range", [18811, 18899])
    lo, hi = port_range[0], port_range[1]

    for port in range(lo, hi + 1):
        if not _is_port_listening(port):
            return port

    return None


def _ensure_mcp_rpyc():
    """Start the RPyC server if not already running and config allows it."""
    if not _should_auto_start():
        return

    port = _find_free_port()
    if port is None:
        print("[DCC-MCP] No free port available in range, skipping RPyC start")
        return

    if _is_port_listening(port):
        print(f"[DCC-MCP] RPyC already running on port {port}, skipping")
        return

    try:
        import hrpyc
        hrpyc.start_server(port=port)
        print(f"[DCC-MCP] RPyC server started on port {port}")
    except Exception as e:
        print(f"[DCC-MCP] Failed to start RPyC server: {e}")


try:
    _ensure_mcp_rpyc()
except Exception as e:
    print(f"[DCC-MCP] 456.py error: {e}")
