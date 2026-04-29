"""Auto-run on UE startup — starts MCP socket server for AI agent communication.

This file is loaded as a UE Python startup script. It can be placed in:
  1. Project/Content/Python/init_unreal.py (per-project)
  2. Engine/Content/Python/init_unreal.py (engine-wide)
  3. Or executed via the install_plugin tool which copies to the project's Plugins/ dir

UE automatically executes init_unreal.py from Python paths on editor startup.
"""

import json
import os
import socket
from pathlib import Path

import unreal


def _is_port_listening(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("localhost", port)) == 0


def _get_config() -> dict:
    """Read MCP config file."""
    config_file = Path.home() / "ue_mcp" / "config.json"
    try:
        if config_file.exists():
            return json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _should_auto_start() -> bool:
    """Check config to decide whether to start the socket server automatically."""
    if os.environ.get("UE_MCP_ENABLED", "0") != "1":
        return False

    is_agent = os.environ.get("UE_MCP_AGENT_LAUNCH", "0") == "1"
    config_key = "agent_launch" if is_agent else "human_launch"

    # Default: agent=True, human=False
    default = is_agent

    cfg = _get_config()
    return cfg.get(config_key, {}).get("auto_start", default)


def _find_free_port() -> int | None:
    """Find a free port in the configured range.

    Agent-launched UE uses the explicit UE_MCP_PORT.
    Human-launched UE scans the port range for the first available port.
    """
    explicit = os.environ.get("UE_MCP_PORT")
    if explicit:
        try:
            port = int(explicit)
        except ValueError:
            return None
        if not _is_port_listening(port):
            return port
        # Agent set a specific port but it's taken — don't scan, fail
        if os.environ.get("UE_MCP_AGENT_LAUNCH", "0") == "1":
            return None

    # Scan port range for a free port
    cfg = _get_config()
    port_range = cfg.get("port_range", [20811, 20899])
    lo, hi = port_range[0], port_range[1]

    for port in range(lo, hi + 1):
        if not _is_port_listening(port):
            return port

    return None


def _start_mcp_server() -> None:
    """Start the MCP socket server if config allows it."""
    if not _should_auto_start():
        return

    port = _find_free_port()
    if port is None:
        unreal.log_warning("[DCC-MCP] No free port available in range, skipping socket server start")
        return

    try:
        # Import the server module — it should be on the Python path
        # either from the project Plugins/UEMCP/ or from the repo plugins/ue/
        import ue_mcp_server
        ue_mcp_server.start(port=port)
        unreal.log(f"[DCC-MCP] Socket server started on port {port}")
    except Exception as e:
        unreal.log_error(f"[DCC-MCP] Failed to start socket server: {e}")


try:
    _start_mcp_server()
except Exception as e:
    unreal.log_error(f"[DCC-MCP] init_unreal.py error: {e}")
