"""Configuration API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..dcc_bridge import DCCBridge

router = APIRouter(prefix="/api/{dcc}/config", tags=["config"])


def _get_bridge() -> DCCBridge:
    from ..app import bridge
    return bridge


def _validate(dcc: str, br: DCCBridge = Depends(_get_bridge)) -> DCCBridge:
    if dcc not in br.dccs:
        raise HTTPException(status_code=404, detail=f"Unknown DCC: {dcc}")
    return br


@router.get("/")
async def get_config(dcc: str, br: DCCBridge = Depends(_validate)):
    """Get full config for a DCC."""
    return br.get_config(dcc)


@router.put("/")
async def update_config(
    dcc: str,
    updates: dict[str, Any] = Body(...),
    br: DCCBridge = Depends(_validate),
):
    """Partial update of config."""
    return br.update_config(dcc, updates)


@router.post("/reset")
async def reset_config(dcc: str, br: DCCBridge = Depends(_validate)):
    """Reset config to defaults."""
    return br.reset_config(dcc)
