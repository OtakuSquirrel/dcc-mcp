"""FastAPI application — serves the dashboard UI and REST API."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .dcc_bridge import DCCBridge

logger = logging.getLogger(__name__)

app = FastAPI(title="DCC MCP MANAGER", version="0.1.0")

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
_webui_dir = Path(__file__).parent
_static_dir = _webui_dir / "static"
_templates_dir = _webui_dir / "templates"
# Icons live at the project root: dcc-mcp/icons/
_icons_dir = _webui_dir.parents[3] / "icons"

app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
if _icons_dir.is_dir():
    app.mount("/icons", StaticFiles(directory=str(_icons_dir)), name="icons")

templates = Jinja2Templates(directory=str(_templates_dir))

# ---------------------------------------------------------------------------
# Shared bridge instance
# ---------------------------------------------------------------------------
bridge = DCCBridge()


def get_bridge() -> DCCBridge:
    """Dependency that returns the shared bridge."""
    return bridge


def validate_dcc(dcc: str, br: DCCBridge = Depends(get_bridge)) -> str:
    """Dependency that validates a DCC key exists."""
    if dcc not in br.dccs:
        raise HTTPException(status_code=404, detail=f"Unknown DCC: {dcc}")
    return dcc


# ---------------------------------------------------------------------------
# Import and include API routers
# ---------------------------------------------------------------------------
from .routes.session_routes import router as session_router  # noqa: E402
from .routes.tool_routes import router as tool_router  # noqa: E402
from .routes.config_routes import router as config_router  # noqa: E402
from .routes.health_routes import router as health_router  # noqa: E402
from .routes.agent_routes import router as agent_router  # noqa: E402
from .routes.install_routes import router as install_router  # noqa: E402

app.include_router(session_router)
app.include_router(tool_router)
app.include_router(config_router)
app.include_router(health_router)
app.include_router(agent_router)
app.include_router(install_router)


# ---------------------------------------------------------------------------
# Helper: build common template context
# ---------------------------------------------------------------------------
def _page_context(request: Request, dcc: str, active_page: str = "dashboard") -> dict:
    """Build the template context dict shared by all DCC sub-pages."""
    info = bridge.get_dcc_info(dcc)
    if not info:
        raise HTTPException(status_code=404, detail=f"Unknown DCC: {dcc}")
    return {
        "request": request,
        "dcc": dcc,
        "dcc_label": info["label"],
        "dcc_color": info["color"],
        "dcc_icon": info["icon"],
        "dcc_installed": info["installed"],
        "active_page": active_page,
        "all_dccs": bridge.list_dccs(),
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Overview page showing all DCCs."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "all_dccs": bridge.list_dccs(),
    })


@app.get("/{dcc}/", response_class=HTMLResponse)
async def dcc_dashboard(request: Request, dcc: str):
    """Per-DCC dashboard page."""
    ctx = _page_context(request, dcc)
    return templates.TemplateResponse("dashboard.html", ctx)


@app.get("/{dcc}/config", response_class=HTMLResponse)
async def dcc_config_page(request: Request, dcc: str):
    """Per-DCC configuration page."""
    ctx = _page_context(request, dcc, active_page="config")
    return templates.TemplateResponse("config.html", ctx)


@app.get("/{dcc}/tools", response_class=HTMLResponse)
async def dcc_tools_page(request: Request, dcc: str):
    """Per-DCC tool management page."""
    ctx = _page_context(request, dcc, active_page="tools")
    return templates.TemplateResponse("tools.html", ctx)



# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------

@app.get("/api/events")
async def api_events():
    """Server-Sent Events stream for live dashboard updates."""

    async def event_stream():
        while True:
            try:
                data = await bridge.get_overview_async()
                yield f"data: {json.dumps(data, default=str)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Legacy overview endpoint (kept for backward compat)
# ---------------------------------------------------------------------------

@app.get("/api/overview")
async def api_overview():
    """All DCCs — sessions, counts, basic port status."""
    return await bridge.get_overview_async()
