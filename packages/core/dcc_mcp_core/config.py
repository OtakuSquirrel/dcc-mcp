"""Parameterized configuration management for DCC MCP servers.

Each DCC instantiates DCCConfig with its own app_name and defaults.
Config is stored at ~/{{app_name}}/config.json with thread-safe access.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()


class DCCConfig:
    """Parameterized config manager for a specific DCC MCP server.

    Usage:
        config = DCCConfig(
            app_name="blender_mcp",
            default_port_range=(19811, 19899),
            default_config={...},
        )
        cfg = config.load()
        config.update({"port_range": [19811, 19850]})
    """

    def __init__(
        self,
        app_name: str,
        default_port_range: tuple[int, int] = (18811, 18899),
        default_config: dict[str, Any] | None = None,
        dcc_search_paths: list[str] | None = None,
    ):
        self.app_name = app_name
        self.home = Path.home() / app_name
        self.config_file = self.home / "config.json"
        self.sessions_dir = self.home / "sessions"

        self._default_config: dict[str, Any] = {
            "human_launch": {
                "auto_start": False,
            },
            "agent_launch": {
                "auto_start": True,
            },
            "port_range": list(default_port_range),
        }
        if dcc_search_paths:
            self._default_config["dcc_search_paths"] = dcc_search_paths
        if default_config:
            self._default_config = _deep_merge(self._default_config, default_config)

    def _ensure_dirs(self) -> None:
        """Create config and sessions directories if needed."""
        self.home.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        """Load config from disk, creating defaults if missing."""
        self._ensure_dirs()
        with _lock:
            if not self.config_file.exists():
                self._write_locked(self._default_config)
                return dict(self._default_config)
            try:
                text = self.config_file.read_text(encoding="utf-8")
                config = json.loads(text)
                return _deep_merge(self._default_config, config)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read config, using defaults: %s", e)
                return dict(self._default_config)

    def save(self, config: dict[str, Any]) -> None:
        """Write config to disk."""
        self._ensure_dirs()
        with _lock:
            self._write_locked(config)

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge updates into existing config and save."""
        config = self.load()
        merged = _deep_merge(config, updates)
        self.save(merged)
        return merged

    def get_port_range(self) -> tuple[int, int]:
        """Return (min_port, max_port) from config."""
        config = self.load()
        port_range = config.get("port_range", self._default_config["port_range"])
        return (int(port_range[0]), int(port_range[1]))

    def get_dcc_search_paths(self) -> list[str]:
        """Return list of directories to scan for DCC installations."""
        config = self.load()
        return config.get("dcc_search_paths", self._default_config.get("dcc_search_paths", []))

    def _write_locked(self, config: dict[str, Any]) -> None:
        """Write config file (caller must hold _lock)."""
        self.config_file.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
