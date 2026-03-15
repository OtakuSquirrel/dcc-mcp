"""Aggregates session/health/tool data from all DCC MCP servers.

The bridge reads file-based registries and OS-level health signals —
it never talks to the DCC processes directly. This means it works even
when a DCC is frozen or no MCP servers are running.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dcc_mcp_core.config import DCCConfig
from dcc_mcp_core.health import check_health, is_port_open
from dcc_mcp_core.registry import SessionRegistry

logger = logging.getLogger(__name__)

# DCC definitions: name -> (app_name, port_range, label, color)
_DCC_DEFS: dict[str, dict[str, Any]] = {
    "blender": {
        "app_name": "blender_mcp",
        "port_range": (19811, 19899),
        "label": "Blender",
        "color": "#E87D0D",
    },
    "houdini": {
        "app_name": "houdini_mcp",
        "port_range": (18811, 18899),
        "label": "Houdini",
        "color": "#FF3C00",
    },
    "ue": {
        "app_name": "ue_mcp",
        "port_range": (20811, 20899),
        "label": "Unreal Engine",
        "color": "#0D47A1",
    },
}

# Icon file mapping — filenames in the project root /icons/ directory
_ICON_FILES: dict[str, str] = {
    "blender": "blender_icon_512x512.png",
    "houdini": "Houdini@0.5x.png",
    "ue": "UE.png",
}

_executor = ThreadPoolExecutor(max_workers=6)


def _load_tool_defs(dcc_key: str) -> dict[str, dict] | None:
    """Try to import CATEGORY_DEFS for a DCC. Returns None if not installed."""
    module_map = {
        "blender": "blender_mcp.tool_defs",
        "houdini": "houdini_mcp.tool_defs",
        "ue": "ue_mcp.tool_defs",
    }
    mod_name = module_map.get(dcc_key)
    if not mod_name:
        return None
    try:
        import importlib
        mod = importlib.import_module(mod_name)
        return getattr(mod, "CATEGORY_DEFS", None)
    except ImportError:
        return None


class DCCBridge:
    """Unified data layer across all DCC MCP registries."""

    def __init__(self):
        self.dccs: dict[str, dict[str, Any]] = {}
        for key, defn in _DCC_DEFS.items():
            config = DCCConfig(
                app_name=defn["app_name"],
                default_port_range=defn["port_range"],
            )
            registry = SessionRegistry(config.sessions_dir, config.get_port_range)
            cat_defs = _load_tool_defs(key)
            self.dccs[key] = {
                "config": config,
                "registry": registry,
                "category_defs": cat_defs,
                "label": defn["label"],
                "color": defn["color"],
            }

    # ------------------------------------------------------------------
    # DCC metadata
    # ------------------------------------------------------------------

    def get_dcc_info(self, dcc_key: str) -> dict[str, Any] | None:
        """Return label, color, icon_file, installed status for one DCC."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return None
        icon_file = _ICON_FILES.get(dcc_key, "")
        return {
            "key": dcc_key,
            "label": dcc["label"],
            "color": dcc["color"],
            "icon_file": icon_file,
            "icon": f"/icons/{icon_file}" if icon_file else "",
            "installed": dcc["category_defs"] is not None,
        }

    def list_dccs(self) -> list[dict[str, Any]]:
        """Return metadata for all known DCCs (for nav rendering)."""
        result = []
        for key in self.dccs:
            info = self.get_dcc_info(key)
            if info:
                result.append(info)
        return result

    # ------------------------------------------------------------------
    # Overview / sessions
    # ------------------------------------------------------------------

    def get_overview(self) -> dict[str, Any]:
        """Return a snapshot of all DCCs — sessions, counts, basic status."""
        result = {}
        for key, dcc in self.dccs.items():
            registry: SessionRegistry = dcc["registry"]
            sessions = registry.list_sessions()
            # Quick port check for each session
            for s in sessions:
                s["port_open"] = is_port_open(s.get("port", 0))
            cat_defs = dcc["category_defs"]
            tool_count = 0
            cat_count = 0
            if cat_defs:
                cat_count = len(cat_defs)
                tool_count = sum(len(c["tools"]) for c in cat_defs.values())
            result[key] = {
                "label": dcc["label"],
                "color": dcc["color"],
                "icon_file": _ICON_FILES.get(key, ""),
                "sessions": sessions,
                "session_count": len(sessions),
                "tool_count": tool_count,
                "category_count": cat_count,
                "installed": cat_defs is not None,
            }
        return result

    async def get_overview_async(self) -> dict[str, Any]:
        """Async wrapper — runs get_overview in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self.get_overview)

    def get_sessions(self, dcc_key: str) -> dict[str, Any]:
        """List sessions for a specific DCC with port_open check."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        registry: SessionRegistry = dcc["registry"]
        sessions = registry.list_sessions()
        for s in sessions:
            s["port_open"] = is_port_open(s.get("port", 0))
        return {"sessions": sessions, "count": len(sessions)}

    def get_dashboard_data(self, dcc_key: str) -> dict[str, Any]:
        """Full dashboard data for one DCC: sessions + port status + metadata."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        sessions_data = self.get_sessions(dcc_key)
        cat_defs = dcc["category_defs"]
        tool_count = 0
        cat_count = 0
        if cat_defs:
            cat_count = len(cat_defs)
            tool_count = sum(len(c["tools"]) for c in cat_defs.values())
        return {
            "label": dcc["label"],
            "color": dcc["color"],
            "icon_file": _ICON_FILES.get(dcc_key, ""),
            "installed": cat_defs is not None,
            "sessions": sessions_data["sessions"],
            "session_count": sessions_data["count"],
            "tool_count": tool_count,
            "category_count": cat_count,
        }

    def delete_session(self, dcc_key: str, session_id: str) -> dict[str, Any]:
        """Remove a specific session by ID."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        registry: SessionRegistry = dcc["registry"]
        registry.remove_session(session_id)
        return {"removed": session_id}

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def get_health(self, dcc_key: str, port: int) -> dict[str, Any]:
        """Full health check for a specific port."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        sessions = dcc["registry"].list_sessions()
        return check_health(port, sessions=sessions)

    async def get_health_async(self, dcc_key: str, port: int) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self.get_health, dcc_key, port)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def get_tools(self, dcc_key: str) -> dict[str, Any]:
        """Return tool categories with enabled/disabled state (array format)."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        cat_defs = dcc["category_defs"]
        if cat_defs is None:
            return {"error": f"{dcc['label']} package not installed"}
        config: DCCConfig = dcc["config"]
        cfg = config.load()
        disabled = set(cfg.get("disabled_tools", []))
        categories = []
        for cat_name, cat_info in cat_defs.items():
            tools = []
            for tool_name, desc in cat_info["tools"].items():
                tools.append({
                    "name": tool_name,
                    "desc": desc,
                    "enabled": tool_name not in disabled,
                })
            enabled_count = sum(1 for t in tools if t["enabled"])
            categories.append({
                "category": cat_name,
                "desc": cat_info["desc"],
                "tools": tools,
                "enabled_count": enabled_count,
                "total_count": len(tools),
            })
        return {"categories": categories, "disabled_tools": list(disabled)}

    def toggle_tool(self, dcc_key: str, tool_name: str) -> dict[str, Any]:
        """Toggle a tool's enabled/disabled state."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        config: DCCConfig = dcc["config"]
        cfg = config.load()
        disabled = cfg.get("disabled_tools", [])
        if tool_name in disabled:
            disabled.remove(tool_name)
            enabled = True
        else:
            disabled.append(tool_name)
            enabled = False
        config.update({"disabled_tools": disabled})
        return {"tool": tool_name, "enabled": enabled}

    def bulk_set_tools(self, dcc_key: str, disabled_tools: list[str]) -> dict[str, Any]:
        """Set the entire disabled_tools list at once."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        config: DCCConfig = dcc["config"]
        config.update({"disabled_tools": disabled_tools})
        return {"disabled_tools": disabled_tools}

    def reset_tools(self, dcc_key: str) -> dict[str, Any]:
        """Clear disabled_tools (enable all tools)."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        config: DCCConfig = dcc["config"]
        config.update({"disabled_tools": []})
        return {"disabled_tools": []}

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def get_config(self, dcc_key: str) -> dict[str, Any]:
        """Return the full config dict for a DCC."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        config: DCCConfig = dcc["config"]
        return config.load()

    def update_config(self, dcc_key: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Partial update of config for a DCC."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        config: DCCConfig = dcc["config"]
        config.update(updates)
        return config.load()

    def reset_config(self, dcc_key: str) -> dict[str, Any]:
        """Reset config to defaults for a DCC."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        config: DCCConfig = dcc["config"]
        config.reset()
        return config.load()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_stale(self, dcc_key: str) -> dict[str, Any]:
        """Remove stale sessions for a DCC."""
        dcc = self.dccs.get(dcc_key)
        if not dcc:
            return {"error": f"Unknown DCC: {dcc_key}"}
        cleaned = dcc["registry"].cleanup_stale_sessions()
        return {"cleaned": cleaned, "count": len(cleaned)}
