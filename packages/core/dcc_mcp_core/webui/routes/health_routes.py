"""Health check API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dcc_bridge import DCCBridge

router = APIRouter(prefix="/api/{dcc}", tags=["health"])


def _get_bridge() -> DCCBridge:
    from ..app import bridge
    return bridge


def _validate(dcc: str, br: DCCBridge = Depends(_get_bridge)) -> DCCBridge:
    if dcc not in br.dccs:
        raise HTTPException(status_code=404, detail=f"Unknown DCC: {dcc}")
    return br


@router.get("/health/{port}")
async def health_check(dcc: str, port: int, br: DCCBridge = Depends(_validate)):
    """Detailed health check for a specific port."""
    return await br.get_health_async(dcc, port)
