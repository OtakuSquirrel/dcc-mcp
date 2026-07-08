"""Monitoring WebUI — a small dashboard served by the daemon itself.

Since the user runs the daemon locally anyway, it is a convenient place
to see what DCC instances are live, their health, and how to connect an
agent. This is *monitoring*, not control — it reuses the same
``DaemonCore`` the MCP tools use, so it never opens a second path to the
DCCs.

The routes are attached directly to the FastMCP server via
``@mcp.custom_route`` (see ``register_webui``), so they share the MCP
app's single lifespan and port — no sub-mounting. Endpoints:

    GET /              -> HTML dashboard (auto-refreshing via fetch)
    GET /api/instances -> JSON: discovered instances
    GET /api/health/{port} -> JSON: health verdict for one port
"""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from dcc_daemon.mcp_server import core, mcp

_KIND_COLOR = {"blender": "#ea7600", "houdini": "#ff4713", "ue": "#0e88c8"}

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dcc-daemon</title>
<style>
  :root { color-scheme: dark; }
  body { font: 14px/1.5 system-ui, sans-serif; margin: 0; background:#14161a; color:#e6e8ec; }
  header { padding: 18px 24px; border-bottom: 1px solid #2a2e35; display:flex; align-items:baseline; gap:14px; }
  header h1 { font-size: 18px; margin:0; font-weight:650; }
  header .sub { color:#8b929c; font-size:12px; }
  main { padding: 24px; max-width: 900px; }
  .row { display:flex; gap:10px; align-items:center; margin-bottom:14px; }
  button { background:#232833; color:#e6e8ec; border:1px solid #363c47; border-radius:6px; padding:6px 12px; cursor:pointer; }
  button:hover { background:#2c323e; }
  table { width:100%; border-collapse: collapse; }
  th, td { text-align:left; padding:10px 12px; border-bottom:1px solid #23262d; }
  th { color:#8b929c; font-weight:550; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  .kind { display:inline-block; padding:2px 9px; border-radius:20px; font-size:12px; font-weight:600; color:#fff; }
  .verdict { font-weight:600; }
  .healthy { color:#4ade80; } .busy { color:#fbbf24; } .hung,.dead { color:#f87171; }
  .no_protocol,.unknown { color:#9ca3af; }
  .empty { color:#8b929c; padding:24px 0; }
  code { background:#232833; padding:2px 6px; border-radius:4px; }
  .foot { margin-top:28px; color:#8b929c; font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>dcc-daemon</h1>
  <span class="sub">local DCC control &middot; <span id="count">…</span></span>
</header>
<main>
  <div class="row">
    <button onclick="refresh(true)">Refresh</button>
    <span class="sub" id="status"></span>
  </div>
  <table>
    <thead><tr><th>Kind</th><th>Instance</th><th>Version</th><th>PID</th><th>File</th><th>Health</th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <p class="empty" id="empty" hidden>No DCC instances registered. Start a DCC with its dcc-daemon plugin.</p>
  <div class="foot">
    Agents connect with <code>{"type":"http","url":"http://HOST:PORT/mcp"}</code>.
    Page auto-refreshes every 5&nbsp;s.
  </div>
</main>
<script>
const KIND_COLOR = __KIND_COLOR__;
function idAttr(s){ return String(s).replace(/[^a-zA-Z0-9_-]/g,'_'); }
async function refresh(force) {
  const s = document.getElementById('status');
  s.textContent = force ? 'refreshing…' : '';
  const r = await fetch('api/instances');
  const data = await r.json();
  const rows = document.getElementById('rows');
  document.getElementById('count').textContent = data.length + ' instance' + (data.length===1?'':'s');
  document.getElementById('empty').hidden = data.length > 0;
  rows.innerHTML = '';
  for (const i of data) {
    const tr = document.createElement('tr');
    const color = KIND_COLOR[i.kind] || '#556';
    const hid = 'h' + idAttr(i.instance_id);
    tr.innerHTML =
      `<td><span class="kind" style="background:${color}">${i.kind||'?'}</span></td>`+
      `<td>${i.instance_id}</td><td>${i.version||'—'}</td><td>${i.pid??'—'}</td>`+
      `<td title="${i.file||''}">${(i.file||'—').split(/[\\\\/]/).pop()}</td>`+
      `<td class="verdict" id="${hid}">…</td>`;
    rows.appendChild(tr);
    fetch('api/health/'+encodeURIComponent(i.instance_id)).then(x=>x.json()).then(h=>{
      const cell = document.getElementById(hid);
      if (cell) { cell.textContent = h.verdict; cell.className = 'verdict '+h.verdict; }
    }).catch(()=>{});
  }
  s.textContent = '';
}
refresh(false);
setInterval(()=>refresh(false), 5000);
</script>
</body>
</html>""".replace("__KIND_COLOR__", json.dumps(_KIND_COLOR))


async def _index(_request: Request) -> HTMLResponse:
    return HTMLResponse(_PAGE)


async def _api_instances(request: Request) -> JSONResponse:
    refresh = request.query_params.get("refresh") in ("1", "true", "yes")
    return JSONResponse(core.list_instances(refresh=refresh))


async def _api_health(request: Request) -> JSONResponse:
    instance_id = request.path_params.get("instance_id")
    if not instance_id:
        return JSONResponse({"error": "bad instance_id"}, status_code=400)
    return JSONResponse(core.health(instance_id))


def register_webui() -> None:
    """Attach the dashboard routes to the MCP server's HTTP app.

    Uses ``@mcp.custom_route`` so the WebUI shares the MCP app's single
    lifespan and port. Idempotent-ish: call once at startup.
    """
    mcp.custom_route("/", methods=["GET"])(_index)
    mcp.custom_route("/api/instances", methods=["GET"])(_api_instances)
    mcp.custom_route("/api/health/{instance_id}", methods=["GET"])(_api_health)
