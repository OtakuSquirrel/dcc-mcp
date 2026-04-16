"""Heartbeat task registry + HeartbeatMiddleware + wait_task tool.

Every DCC tool call is wrapped by this middleware. If the call finishes
within `heartbeat` seconds, the result is returned normally. Otherwise
the call keeps running in a daemon asyncio task, the middleware registers
it, and returns a 'running' status to the agent — who can then call
`wait_task(task_id)` to continue waiting, or use os-mcp to diagnose / kill.

Pattern rationale: the old TimeoutGuardMiddleware raised an error after
timeout, stealing agency from the agent. This middleware YIELDS instead —
the work keeps running, the agent decides what to do next.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import mcp.types as mt
from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import ToolResult

logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT = 15.0


class _RunningTask:
    def __init__(self, task: asyncio.Task, name: str, started: float):
        self.task_id = uuid.uuid4().hex[:8]
        self.task = task
        self.name = name
        self.started = started


# Module-level registry. Lives only in-process; MCP server exit clears it.
_tasks: dict[str, _RunningTask] = {}


def _register_task(task: asyncio.Task, name: str, started: float) -> str:
    rt = _RunningTask(task, name, started)
    _tasks[rt.task_id] = rt
    return rt.task_id


def _pop_task(task_id: str) -> _RunningTask | None:
    return _tasks.pop(task_id, None)


def _get_task(task_id: str) -> _RunningTask | None:
    return _tasks.get(task_id)


def list_running_tasks() -> list[dict]:
    now = time.time()
    return [
        {
            "task_id": rt.task_id,
            "task_name": rt.name,
            "elapsed_seconds": round(now - rt.started, 2),
        }
        for rt in _tasks.values()
    ]


class HeartbeatMiddleware(Middleware):
    """Wrap every tool call so long-running calls yield to the agent."""

    # Tools that should NOT be heartbeat-wrapped — they're infrastructure
    # that exists to interact with the registry itself.
    _EXEMPT_TOOLS = {"wait_task", "list_tasks"}

    def __init__(self, default_heartbeat: float = _DEFAULT_HEARTBEAT):
        super().__init__()
        self._default = default_heartbeat

    async def on_call_tool(self, context, call_next):
        tool_name = context.message.name
        if tool_name in self._EXEMPT_TOOLS:
            return await call_next(context)

        started = time.time()
        # Wrap call_next in an asyncio.Task so we can time-bound the wait
        # without cancelling the underlying work on timeout (shield).
        inner = asyncio.create_task(call_next(context))

        try:
            result = await asyncio.wait_for(
                asyncio.shield(inner), self._default
            )
            return result
        except asyncio.TimeoutError:
            task_id = _register_task(inner, tool_name, started)
            elapsed = time.time() - started
            payload = {
                "status": "running",
                "task_id": task_id,
                "task_name": tool_name,
                "elapsed_seconds": round(elapsed, 2),
                "hint": (
                    f"Task '{tool_name}' has run for {elapsed:.1f}s and is not "
                    f"done. Call wait_task(task_id='{task_id}') to keep waiting, "
                    f"or os-mcp.check_dcc_health(port=...) to diagnose."
                ),
            }
            return ToolResult(
                content=[mt.TextContent(type="text", text=json.dumps(payload))]
            )


def _extract_tool_result(result: Any) -> Any:
    """Pull the original dict out of a ToolResult wrapper.

    Used by wait_task when a previously-yielded task finishes — we need
    to surface the original tool output to the agent. If the structure
    isn't what we expect, fall back to a string representation rather
    than crashing.
    """
    try:
        content = getattr(result, "content", None) or []
        if content:
            text = getattr(content[0], "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return None
    except Exception:
        return str(result)


def register_task_tools(mcp) -> None:
    """Register wait_task and list_tasks tools on the given FastMCP instance.

    Called from server.py after the FastMCP instance is built.
    """

    @mcp.tool()
    async def wait_task(task_id: str, heartbeat: float = _DEFAULT_HEARTBEAT) -> dict:
        """Continue waiting for a task that previously returned status='running'.

        When a DCC tool call doesn't finish within 15s, the MCP server
        returns status='running' with a task_id so the agent can decide
        whether to keep waiting. Call this tool with that task_id to wait
        longer.

        Args:
            task_id: The task_id from a prior tool call's 'running' response.
            heartbeat: Max seconds to wait before yielding again.

        Returns:
            status='completed' with the original result, or status='running'
            again if it's still not done, or status='unknown_task' if the
            task_id isn't in the registry (expired / wrong id / server
            restarted).
        """
        rt = _get_task(task_id)
        if rt is None:
            return {"status": "unknown_task", "task_id": task_id}

        try:
            result = await asyncio.wait_for(
                asyncio.shield(rt.task), heartbeat
            )
            _pop_task(task_id)
            elapsed = time.time() - rt.started
            original = _extract_tool_result(result)
            return {
                "status": "completed",
                "task_name": rt.name,
                "elapsed_seconds": round(elapsed, 2),
                "result": original,
            }
        except asyncio.TimeoutError:
            elapsed = time.time() - rt.started
            return {
                "status": "running",
                "task_id": task_id,
                "task_name": rt.name,
                "elapsed_seconds": round(elapsed, 2),
            }

    @mcp.tool()
    def list_tasks() -> dict:
        """List all in-flight tasks on this MCP server process."""
        return {"tasks": list_running_tasks()}
