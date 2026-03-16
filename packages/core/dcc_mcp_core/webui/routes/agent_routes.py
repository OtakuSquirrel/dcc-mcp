"""Agent MCP installation API routes.

Handles detecting AI agents on the system and installing/uninstalling
MCP server entries into their configuration files.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..dcc_bridge import DCCBridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _get_bridge() -> DCCBridge:
    from ..app import bridge
    return bridge


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

def _appdata() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))


def _home() -> Path:
    return Path.home()


# Each agent: config file path, how to read/write mcpServers
_AGENT_DEFS: dict[str, dict[str, Any]] = {
    "claude_desktop": {
        "label": "Claude Desktop",
        "config_path": lambda: _appdata() / "Claude" / "claude_desktop_config.json",
        "mcp_key": "mcpServers",
    },
    "claude_code": {
        "label": "Claude Code (CLI)",
        "config_path": lambda: _home() / ".claude.json",
        "mcp_key": "mcpServers",
    },
    "vscode_claude": {
        "label": "VS Code (Claude)",
        "config_path": lambda: _appdata() / "Code" / "User" / "Claude" / "claude_desktop_config.json",
        "mcp_key": "mcpServers",
    },
    "cursor": {
        "label": "Cursor",
        "config_path": lambda: _home() / ".cursor" / "mcp.json",
        "mcp_key": "mcpServers",
    },
    "windsurf": {
        "label": "Windsurf",
        "config_path": lambda: _home() / ".codeium" / "windsurf" / "mcp_config.json",
        "mcp_key": "mcpServers",
    },
}

# DCC -> MCP server name mapping
_DCC_SERVER_NAMES: dict[str, str] = {
    "blender": "blender",
    "houdini": "houdini",
    "ue": "ue",
}


def _get_mcp_command(dcc_key: str) -> dict[str, Any]:
    """Build the MCP server entry for a DCC."""
    # Use the full path to the venv python for reliability
    venv_python = Path(sys.executable)
    server_name = _DCC_SERVER_NAMES.get(dcc_key, f"{dcc_key}-mcp")
    module_map = {
        "blender": "blender_mcp",
        "houdini": "houdini_mcp",
        "ue": "ue_mcp",
    }
    module = module_map.get(dcc_key, f"{dcc_key}_mcp")
    return {
        "command": str(venv_python),
        "args": ["-m", module],
    }


def _read_agent_config(agent_key: str) -> tuple[Path, dict]:
    """Read an agent's config file. Returns (path, data)."""
    defn = _AGENT_DEFS.get(agent_key)
    if not defn:
        raise HTTPException(404, f"Unknown agent: {agent_key}")
    path = defn["config_path"]()
    if not path.exists():
        return path, {}
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", path, e)
        return path, {}


def _write_agent_config(path: Path, data: dict) -> None:
    """Write config back to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/agents")
async def list_agents():
    """List all known AI agents with their install status."""
    results = []
    for key, defn in _AGENT_DEFS.items():
        path = defn["config_path"]()
        config_exists = path.exists()
        installed_dccs = []

        if config_exists:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                servers = data.get(defn["mcp_key"], {})
                for dcc_key, server_name in _DCC_SERVER_NAMES.items():
                    if server_name in servers:
                        installed_dccs.append(dcc_key)
            except (json.JSONDecodeError, OSError):
                pass

        results.append({
            "key": key,
            "label": defn["label"],
            "label_short": defn["label"].split("(")[0].strip(),
            "config_path": str(path),
            "config_exists": config_exists,
            "installed_dccs": installed_dccs,
        })
    return {"agents": results}


@router.get("/agents/{agent_key}")
async def get_agent_detail(agent_key: str):
    """Get detailed info about one agent's MCP config."""
    defn = _AGENT_DEFS.get(agent_key)
    if not defn:
        raise HTTPException(404, f"Unknown agent: {agent_key}")

    path, data = _read_agent_config(agent_key)
    servers = data.get(defn["mcp_key"], {})

    dcc_status = {}
    for dcc_key, server_name in _DCC_SERVER_NAMES.items():
        dcc_status[dcc_key] = {
            "installed": server_name in servers,
            "server_name": server_name,
            "config": servers.get(server_name),
        }

    return {
        "key": agent_key,
        "label": defn["label"],
        "config_path": str(path),
        "config_exists": path.exists(),
        "dcc_status": dcc_status,
        "all_servers": servers,
    }


@router.post("/agents/{agent_key}/install/{dcc_key}")
async def install_mcp(agent_key: str, dcc_key: str):
    """Install a DCC's MCP server entry into an agent's config."""
    defn = _AGENT_DEFS.get(agent_key)
    if not defn:
        raise HTTPException(404, f"Unknown agent: {agent_key}")
    if dcc_key not in _DCC_SERVER_NAMES:
        raise HTTPException(404, f"Unknown DCC: {dcc_key}")

    path, data = _read_agent_config(agent_key)
    mcp_key = defn["mcp_key"]
    if mcp_key not in data:
        data[mcp_key] = {}

    server_name = _DCC_SERVER_NAMES[dcc_key]
    entry = _get_mcp_command(dcc_key)
    data[mcp_key][server_name] = entry

    _write_agent_config(path, data)
    logger.info("Installed %s into %s at %s", server_name, agent_key, path)

    return {
        "status": "installed",
        "agent": agent_key,
        "dcc": dcc_key,
        "server_name": server_name,
        "entry": entry,
        "config_path": str(path),
    }


@router.post("/agents/{agent_key}/uninstall/{dcc_key}")
async def uninstall_mcp(agent_key: str, dcc_key: str):
    """Remove a DCC's MCP server entry from an agent's config."""
    defn = _AGENT_DEFS.get(agent_key)
    if not defn:
        raise HTTPException(404, f"Unknown agent: {agent_key}")
    if dcc_key not in _DCC_SERVER_NAMES:
        raise HTTPException(404, f"Unknown DCC: {dcc_key}")

    path, data = _read_agent_config(agent_key)
    mcp_key = defn["mcp_key"]
    servers = data.get(mcp_key, {})
    server_name = _DCC_SERVER_NAMES[dcc_key]

    removed = server_name in servers
    if removed:
        del servers[server_name]
        data[mcp_key] = servers
        _write_agent_config(path, data)
        logger.info("Uninstalled %s from %s", server_name, agent_key)

    return {
        "status": "uninstalled" if removed else "not_found",
        "agent": agent_key,
        "dcc": dcc_key,
        "server_name": server_name,
    }


@router.post("/agents/{agent_key}/install-all")
async def install_all_mcps(agent_key: str, br: DCCBridge = Depends(_get_bridge)):
    """Install all available DCC MCP servers into an agent."""
    defn = _AGENT_DEFS.get(agent_key)
    if not defn:
        raise HTTPException(404, f"Unknown agent: {agent_key}")

    path, data = _read_agent_config(agent_key)
    mcp_key = defn["mcp_key"]
    if mcp_key not in data:
        data[mcp_key] = {}

    installed = []
    for dcc_key, server_name in _DCC_SERVER_NAMES.items():
        # Only install DCCs that have packages installed
        dcc = br.dccs.get(dcc_key)
        if dcc and dcc.get("category_defs") is not None:
            entry = _get_mcp_command(dcc_key)
            data[mcp_key][server_name] = entry
            installed.append(dcc_key)

    _write_agent_config(path, data)
    return {"status": "installed", "agent": agent_key, "installed": installed}
