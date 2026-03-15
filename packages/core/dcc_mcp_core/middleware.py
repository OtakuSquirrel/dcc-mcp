"""MCP middleware — reusable middleware components for DCC MCP servers.

ClientNameMiddleware: Auto-detect agent name from MCP initialize handshake.
ToolGuardMiddleware: Block disabled tools at runtime based on config.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import mcp.types as mt
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import Tool, ToolResult

from dcc_mcp_core.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class ClientNameMiddleware(Middleware):
    """Capture client name from the MCP initialize handshake.

    Every MCP client sends clientInfo.name during initialization.
    We use this to auto-detect the agent/client identity (e.g. "Claude Code",
    "Cursor") so the WebUI dashboard shows the real name.
    """

    def __init__(self, on_client_name: Any = None):
        """
        Args:
            on_client_name: Callback(name: str) invoked when client name is detected.
                           Typically sets connection_manager._client_name.
        """
        super().__init__()
        self._on_client_name = on_client_name

    async def on_initialize(self, context, call_next):
        result = await call_next(context)
        try:
            name = context.message.params.clientInfo.name
            if name and self._on_client_name:
                self._on_client_name(name)
                logger.info("Client name auto-detected: '%s'", name)
        except Exception:
            pass
        return result


class ToolGuardMiddleware(Middleware):
    """Block disabled tools at runtime based on config.

    Checks the tool registry on each tool call. If the tool
    is disabled, returns an error without executing it. Also filters
    disabled tools from the tools/list response.
    """

    def __init__(self, tool_registry: ToolRegistry):
        super().__init__()
        self._tool_registry = tool_registry

    async def on_call_tool(self, context, call_next):
        tool_name = context.message.name
        if not self._tool_registry.is_tool_enabled(tool_name):
            return ToolResult(
                content=[mt.TextContent(
                    type="text",
                    text=f"Tool '{tool_name}' is currently disabled. "
                         f"Enable it in config or WebUI.",
                )]
            )
        return await call_next(context)

    async def on_list_tools(self, context, call_next):
        tools: Sequence[Tool] = await call_next(context)
        disabled = set(self._tool_registry.get_disabled_tools())
        return [t for t in tools if t.name not in disabled]
