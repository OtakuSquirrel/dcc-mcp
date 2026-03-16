"""MCP middleware — reusable middleware components for DCC MCP servers.

ClientNameMiddleware: Auto-detect agent name from MCP initialize handshake.
ToolGuardMiddleware: Block disabled tools at runtime based on config.
TimeoutGuardMiddleware: Hard timeout + auto health check on stuck tools.
"""

from __future__ import annotations

import asyncio
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


class TimeoutGuardMiddleware(Middleware):
    """Hard timeout on tool calls with automatic health check on timeout.

    If a tool call exceeds the timeout, runs a health check to determine
    if the DCC is hung/blocked/busy, and returns a descriptive error
    instead of hanging forever.

    Args:
        timeout: Max seconds per tool call (default 10).
        get_port: Callable returning the current DCC port.
        health_check_fn: Callable(port) -> dict returning health verdict.
        skip_tools: Tool names to skip timeout (e.g. long renders).
    """

    def __init__(
        self,
        timeout: float = 10.0,
        get_port: Any = None,
        health_check_fn: Any = None,
        skip_tools: set[str] | None = None,
    ):
        super().__init__()
        self._timeout = timeout
        self._get_port = get_port
        self._health_check_fn = health_check_fn
        self._skip_tools = skip_tools or set()

    async def on_call_tool(self, context, call_next):
        tool_name = context.message.name

        # Skip timeout for explicitly excluded tools (renders, etc.)
        if tool_name in self._skip_tools:
            return await call_next(context)

        try:
            return await asyncio.wait_for(
                call_next(context),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool '%s' timed out after %.1fs", tool_name, self._timeout)

            # Run health check to diagnose why it hung
            health_info = ""
            if self._get_port and self._health_check_fn:
                try:
                    port = self._get_port()
                    if port:
                        health = self._health_check_fn(port)
                        verdict = health.get("verdict", "unknown")
                        details = health.get("details", "")
                        dialogs = health.get("modal_dialogs", [])
                        health_info = f" DCC status: {verdict}. {details}"
                        if dialogs:
                            dialog_descs = []
                            for d in dialogs:
                                title = d.get("title", "?")
                                child = d.get("child_text", "")
                                if child:
                                    dialog_descs.append(f"[{title}] {child}")
                                else:
                                    dialog_descs.append(title)
                            health_info += f" Blocking dialog(s): {'; '.join(dialog_descs)}"
                except Exception as e:
                    health_info = f" Health check failed: {e}"

            raise RuntimeError(
                f"TIMEOUT: Tool '{tool_name}' did not respond within "
                f"{self._timeout}s. Houdini is likely blocked.\n\n"
                f"Health check:{health_info}\n\n"
                f"Recovery options:\n"
                f"- If 'blocked': modal dialog detected — use stop_houdini(force=True) "
                f"then adopt_idle() or start_houdini()\n"
                f"- If 'hung': use adopt_idle() to kill and replace\n"
                f"- If 'busy': Houdini is computing — wait or increase timeout"
            )
