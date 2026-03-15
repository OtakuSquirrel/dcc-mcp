"""Tool management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dcc_bridge import DCCBridge

router = APIRouter(prefix="/api/{dcc}/tools", tags=["tools"])


class ToggleBody(BaseModel):
    tool: str


class BulkBody(BaseModel):
    disabled_tools: list[str]


def _get_bridge() -> DCCBridge:
    from ..app import bridge
    return bridge


def _validate(dcc: str, br: DCCBridge = Depends(_get_bridge)) -> DCCBridge:
    if dcc not in br.dccs:
        raise HTTPException(status_code=404, detail=f"Unknown DCC: {dcc}")
    return br


@router.get("/")
async def list_tools(dcc: str, br: DCCBridge = Depends(_validate)):
    """List all tools by category with enabled state."""
    return br.get_tools(dcc)


@router.put("/toggle")
async def toggle_tool(dcc: str, body: ToggleBody, br: DCCBridge = Depends(_validate)):
    """Toggle one tool's enabled/disabled state."""
    return br.toggle_tool(dcc, body.tool)


@router.put("/bulk")
async def bulk_set_tools(dcc: str, body: BulkBody, br: DCCBridge = Depends(_validate)):
    """Set the entire disabled_tools list."""
    return br.bulk_set_tools(dcc, body.disabled_tools)


@router.post("/reset")
async def reset_tools(dcc: str, br: DCCBridge = Depends(_validate)):
    """Reset tools to defaults (enable all)."""
    return br.reset_tools(dcc)
