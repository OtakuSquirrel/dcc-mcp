"""Session management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dcc_bridge import DCCBridge

router = APIRouter(prefix="/api/{dcc}/sessions", tags=["sessions"])


def _get_bridge() -> DCCBridge:
    from ..app import bridge
    return bridge


def _validate(dcc: str, br: DCCBridge = Depends(_get_bridge)) -> DCCBridge:
    if dcc not in br.dccs:
        raise HTTPException(status_code=404, detail=f"Unknown DCC: {dcc}")
    return br


@router.get("/")
async def list_sessions(dcc: str, br: DCCBridge = Depends(_validate)):
    """List sessions for a DCC with port_open status."""
    return br.get_sessions(dcc)


@router.get("/dashboard")
async def dashboard_data(dcc: str, br: DCCBridge = Depends(_validate)):
    """Full dashboard data — sessions + port status + metadata."""
    return br.get_dashboard_data(dcc)


@router.post("/cleanup")
async def cleanup_stale(dcc: str, br: DCCBridge = Depends(_validate)):
    """Remove stale sessions for a DCC."""
    return br.cleanup_stale(dcc)


@router.delete("/{session_id}")
async def delete_session(dcc: str, session_id: str, br: DCCBridge = Depends(_validate)):
    """Remove a single session by ID."""
    return br.delete_session(dcc, session_id)
