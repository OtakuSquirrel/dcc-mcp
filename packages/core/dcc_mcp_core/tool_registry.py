"""Tool registry — static metadata framework for DCC MCP tools.

Each DCC package defines its own CATEGORY_DEFS and passes them to
ToolRegistry. Provides tool-to-category mapping, descriptions,
and default enabled/disabled state.
"""

from __future__ import annotations

from typing import Any

from dcc_mcp_core.config import DCCConfig


class ToolRegistry:
    """Manages tool metadata, categories, and enable/disable state.

    Usage:
        tool_reg = ToolRegistry(config, category_defs, default_disabled)
    """

    def __init__(
        self,
        config: DCCConfig,
        category_defs: dict[str, dict[str, Any]],
        default_disabled_tools: list[str] | None = None,
    ):
        self._config = config
        self.category_defs = category_defs
        self.default_disabled_tools = default_disabled_tools or []

        # Build indexes
        self.tool_categories: dict[str, list[str]] = {
            cat: list(info["tools"].keys())
            for cat, info in category_defs.items()
        }
        self.tool_to_category: dict[str, str] = {}
        self.all_tool_names: set[str] = set()
        self.tool_descriptions: dict[str, str] = {}

        for cat, info in category_defs.items():
            for tool, desc in info["tools"].items():
                self.tool_to_category[tool] = cat
                self.all_tool_names.add(tool)
                self.tool_descriptions[tool] = desc

    def get_disabled_tools(self) -> list[str]:
        """Get the current list of disabled tools from config."""
        config = self._config.load()
        return config.get("disabled_tools", list(self.default_disabled_tools))

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a specific tool is enabled."""
        return tool_name not in self.get_disabled_tools()
