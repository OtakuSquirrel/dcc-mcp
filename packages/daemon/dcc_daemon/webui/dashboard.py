"""Local monitoring, installation, logs, and diagnostics WebUI."""

from __future__ import annotations

import json
import logging

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from dcc_daemon import config
from dcc_daemon.mcp_server import core, mcp
from dcc_daemon.webui.diagnostics import snapshot as diagnostics_snapshot
from dcc_daemon.webui.install_guides import build_plugin_zip, list_guides
from dcc_daemon.webui.log_buffer import clear_logs, get_logs

logger = logging.getLogger(__name__)

_KIND_COLOR = {
    "blender": "#ea7600",
    "houdini": "#ff4713",
    "ue": "#0e88c8",
    "maya": "#35a66f",
}

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dcc-daemon</title>
<style>
  :root { color-scheme:dark; --bg:#14161a; --panel:#1b1f26; --line:#2a2e35; --muted:#9299a4; --text:#e6e8ec; --accent:#67a7ff; }
  * { box-sizing:border-box; }
  body { font:14px/1.5 system-ui,sans-serif; margin:0; background:var(--bg); color:var(--text); }
  header { padding:16px 24px; border-bottom:1px solid var(--line); display:flex; align-items:baseline; gap:14px; }
  h1 { font-size:18px; margin:0; } h2 { font-size:18px; margin:0 0 14px; } h3 { margin:0 0 8px; font-size:15px; }
  .sub,.muted { color:var(--muted); font-size:12px; }
  .shell { display:grid; grid-template-columns:180px minmax(0,1fr); min-height:calc(100vh - 58px); }
  nav { border-right:1px solid var(--line); padding:18px 12px; }
  nav button { display:block; width:100%; text-align:left; margin:0 0 5px; border:0; background:transparent; }
  nav button.active { background:#283142; color:#fff; }
  main { padding:24px; max-width:1100px; width:100%; }
  section { display:none; } section.active { display:block; }
  .row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:14px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:9px; padding:15px; }
  .card .value { font-size:18px; font-weight:650; margin-top:4px; }
  button,select,input { background:#232833; color:var(--text); border:1px solid #363c47; border-radius:6px; padding:7px 11px; }
  button { cursor:pointer; } button:hover { background:#303746; }
  input { min-width:190px; }
  table { width:100%; border-collapse:collapse; }
  th,td { text-align:left; padding:9px 10px; border-bottom:1px solid #292d34; vertical-align:top; }
  th { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
  code { background:#232833; padding:2px 6px; border-radius:4px; overflow-wrap:anywhere; }
  pre { background:#111318; padding:10px; border-radius:6px; white-space:pre-wrap; margin:8px 0; }
  .kind { display:inline-block; padding:2px 9px; border-radius:20px; font-size:12px; font-weight:650; color:#fff; }
  .healthy,.INFO { color:#4ade80; } .busy,.WARNING { color:#fbbf24; } .hung,.dead,.ERROR,.CRITICAL { color:#f87171; } .DEBUG { color:#a5b4fc; }
  .empty { color:var(--muted); padding:20px 0; }
  .guide { margin-bottom:12px; } .guide p { margin:6px 0; }
  .log-message { max-width:560px; white-space:pre-wrap; overflow-wrap:anywhere; }
  .service { display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-bottom:1px solid var(--line); }
  @media (max-width:720px) { .shell { grid-template-columns:1fr; } nav { border-right:0; border-bottom:1px solid var(--line); display:flex; overflow:auto; } nav button { width:auto; white-space:nowrap; } main { padding:16px; } }
</style>
</head>
<body>
<header><h1>dcc-daemon</h1><span class="sub">local DCC control · <span id="header-status">ready</span></span></header>
<div class="shell">
<nav>
  <button class="active" data-tab="overview">Overview</button>
  <button data-tab="logs">Logs</button>
  <button data-tab="install">Install</button>
  <button data-tab="diagnostics">Diagnostics</button>
</nav>
<main>
  <section id="overview" class="active">
    <h2>Overview</h2>
    <div class="grid" id="overview-cards"></div>
    <div class="row" style="margin-top:18px"><button onclick="loadInstances(true)">Refresh</button><span class="sub" id="instance-status"></span></div>
    <table><thead><tr><th>Kind</th><th>Instance</th><th>Version</th><th>PID</th><th>File</th><th>Health</th></tr></thead><tbody id="instance-rows"></tbody></table>
    <p class="empty" id="instance-empty" hidden>No DCC instances registered. Open Install for setup instructions.</p>
  </section>

  <section id="logs">
    <h2>Logs</h2>
    <div class="row">
      <select id="log-level"><option value="">All levels</option><option>DEBUG</option><option>INFO</option><option>WARNING</option><option>ERROR</option></select>
      <input id="log-search" placeholder="Search logger or message">
      <button onclick="loadLogs()">Refresh</button><button onclick="clearLogView()">Clear buffer</button>
      <span class="sub">Manual refresh · latest 300 records</span>
    </div>
    <table><thead><tr><th>Time (UTC)</th><th>Level</th><th>Logger</th><th>Message</th></tr></thead><tbody id="log-rows"></tbody></table>
    <p class="empty" id="log-empty" hidden>No matching log records.</p>
  </section>

  <section id="install">
    <h2>Install DCC plugins</h2>
    <p class="muted">Each ZIP contains the DCC adapter and shared connector. Extract or install it using the instructions below.</p>
    <div id="install-guides"></div>
  </section>

  <section id="diagnostics">
    <h2>Diagnostics</h2>
    <div class="row"><button onclick="loadDiagnostics()">Run diagnostics</button><span class="sub">Read-only local checks</span></div>
    <div class="grid" id="diagnostic-cards"></div>
    <div class="card" style="margin-top:12px"><h3>Services</h3><div id="service-list"></div></div>
    <div class="card" style="margin-top:12px"><h3>MCP tools</h3><div id="tool-list"></div></div>
  </section>
</main>
</div>
<script>
const KIND_COLOR = __KIND_COLOR__;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shortTime = value => value ? value.slice(11,23) : '—';

document.querySelectorAll('nav button').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.toggle('active', x === button));
  document.querySelectorAll('main section').forEach(x => x.classList.toggle('active', x.id === button.dataset.tab));
  if (button.dataset.tab === 'logs') loadLogs();
  if (button.dataset.tab === 'install') loadGuides();
  if (button.dataset.tab === 'diagnostics') loadDiagnostics();
}));

async function jsonFetch(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`);
  return response.json();
}

async function loadInstances(showStatus=false) {
  const status = document.getElementById('instance-status');
  if (showStatus) status.textContent = 'refreshing…';
  try {
    const data = await jsonFetch('/api/instances');
    const rows = document.getElementById('instance-rows');
    rows.innerHTML = '';
    document.getElementById('instance-empty').hidden = data.length > 0;
    document.getElementById('overview-cards').innerHTML =
      `<div class="card"><span class="muted">Registered instances</span><div class="value">${data.length}</div></div>`+
      `<div class="card"><span class="muted">MCP endpoint</span><div class="value"><code>${esc(location.origin+'/mcp')}</code></div></div>`;
    for (const item of data) {
      const tr = document.createElement('tr');
      const hid = 'health-' + String(item.instance_id).replace(/[^a-zA-Z0-9_-]/g,'_');
      tr.innerHTML = `<td><span class="kind" style="background:${KIND_COLOR[item.kind]||'#556'}">${esc(item.kind||'?')}</span></td>`+
        `<td>${esc(item.instance_id)}</td><td>${esc(item.version||'—')}</td><td>${esc(item.pid??'—')}</td>`+
        `<td title="${esc(item.file||'')}">${esc((item.file||'—').split(/[\\/]/).pop())}</td><td id="${hid}">…</td>`;
      rows.appendChild(tr);
      jsonFetch('/api/health/'+encodeURIComponent(item.instance_id)).then(health => {
        const cell=document.getElementById(hid); if(cell){cell.textContent=health.verdict;cell.className=health.verdict;}
      }).catch(()=>{});
    }
    status.textContent = showStatus ? 'updated' : '';
  } catch (error) { status.textContent = error.message; }
}

async function loadLogs() {
  const level = document.getElementById('log-level').value;
  const search = document.getElementById('log-search').value;
  const data = await jsonFetch(`/api/logs?limit=300&level=${encodeURIComponent(level)}&search=${encodeURIComponent(search)}`);
  const rows = document.getElementById('log-rows'); rows.innerHTML='';
  document.getElementById('log-empty').hidden = data.length > 0;
  for(const item of data){
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${esc(shortTime(item.timestamp))}</td><td class="${esc(item.level)}">${esc(item.level)}</td>`+
      `<td>${esc(item.logger)}</td><td class="log-message">${esc(item.message)}${item.exception?'<pre>'+esc(item.exception)+'</pre>':''}</td>`;
    rows.appendChild(tr);
  }
}

async function clearLogView(){ await jsonFetch('/api/logs', {method:'DELETE'}); await loadLogs(); }

let guidesLoaded=false;
async function loadGuides(){
  if(guidesLoaded) return;
  const guides=await jsonFetch('/api/install');
  document.getElementById('install-guides').innerHTML=guides.map(g=>`<div class="card guide">
    <h3><span class="kind" style="background:${KIND_COLOR[g.kind]||'#556'}">${esc(g.title)}</span></h3>
    <p><span class="muted">Main-thread bridge</span> · <code>${esc(g.bridge)}</code></p>
    <p><span class="muted">Registration</span> · <code>${esc(g.register_address)}</code></p>
    <p>${esc(g.persistent)}</p><pre>${esc(g.temporary)}</pre>
    <button onclick="location.href='/api/install/${encodeURIComponent(g.kind)}/package'">Download plugin ZIP</button>
  </div>`).join('');
  guidesLoaded=true;
}

async function loadDiagnostics(){
  const data=await jsonFetch('/api/diagnostics');
  const d=data.daemon, s=data.summary;
  document.getElementById('diagnostic-cards').innerHTML=
    `<div class="card"><span class="muted">Daemon</span><div class="value">v${esc(d.version)}</div><div>PID ${esc(d.pid)} · ${esc(d.uptime_seconds)}s</div></div>`+
    `<div class="card"><span class="muted">Instances</span><div class="value">${esc(s.connected_instances)} / ${esc(s.registered_instances)}</div><div>connected / registered</div></div>`+
    `<div class="card"><span class="muted">Config</span><div><code>${esc(d.config_path)}</code></div></div>`;
  document.getElementById('service-list').innerHTML=Object.entries(data.services).map(([name,item])=>
    `<div class="service"><span>${esc(name)}</span><span><code>${esc(item.address)}</code> · <span class="healthy">${esc(item.status)}</span></span></div>`).join('');
  document.getElementById('tool-list').innerHTML=data.mcp_tools.map(x=>`<code>${esc(x)}</code>`).join(' ');
}

loadInstances(false);
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


async def _api_logs(request: Request) -> JSONResponse:
    try:
        limit = int(request.query_params.get("limit", "200"))
    except ValueError:
        return JSONResponse({"error": "limit must be an integer"}, status_code=400)
    return JSONResponse(get_logs(
        level=request.query_params.get("level"),
        logger=request.query_params.get("logger"),
        search=request.query_params.get("search"),
        limit=limit,
    ))


async def _api_logs_clear(_request: Request) -> JSONResponse:
    clear_logs()
    return JSONResponse({"ok": True})


async def _api_install(_request: Request) -> JSONResponse:
    host, port = config.register_bind()
    return JSONResponse(list_guides(f"{host}:{port}"))


async def _api_install_package(request: Request) -> Response:
    kind = str(request.path_params.get("kind", ""))
    try:
        data, filename = build_plugin_zip(kind)
    except KeyError:
        return JSONResponse({"error": f"unknown DCC kind: {kind}"}, status_code=404)
    except FileNotFoundError as exc:
        logger.warning("plugin package unavailable: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=503)
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _api_diagnostics(_request: Request) -> JSONResponse:
    return JSONResponse(diagnostics_snapshot(core.list_instances()))


def register_webui() -> None:
    """Attach local WebUI routes to the FastMCP HTTP app."""
    mcp.custom_route("/", methods=["GET"])(_index)
    mcp.custom_route("/api/instances", methods=["GET"])(_api_instances)
    mcp.custom_route("/api/health/{instance_id}", methods=["GET"])(_api_health)
    mcp.custom_route("/api/logs", methods=["GET"])(_api_logs)
    mcp.custom_route("/api/logs", methods=["DELETE"])(_api_logs_clear)
    mcp.custom_route("/api/install", methods=["GET"])(_api_install)
    mcp.custom_route("/api/install/{kind}/package", methods=["GET"])(_api_install_package)
    mcp.custom_route("/api/diagnostics", methods=["GET"])(_api_diagnostics)
