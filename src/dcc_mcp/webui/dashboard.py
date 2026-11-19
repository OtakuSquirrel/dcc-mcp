"""Local monitoring, installation, logs, and diagnostics WebUI."""

from __future__ import annotations

import json
import logging
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from dcc_mcp.installers import InstallerService
from dcc_mcp.installers.base import InstallerError
from dcc_mcp.mcp_server import core, mcp
from dcc_mcp.webui.diagnostics import snapshot as diagnostics_snapshot
from dcc_mcp.webui.integrations import integration_examples
from dcc_mcp.webui.log_buffer import clear_logs, get_logs

logger = logging.getLogger(__name__)
installer_service = InstallerService()

_KIND_COLOR = {
    "blender": "#ea7600",
    "houdini": "#ff4713",
    "ue": "#0e88c8",
    "maya": "#35a66f",
    "tuanjie": "#c2c2c2",
}

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dcc-mcp</title>
<style>
  :root { color-scheme:dark; --bg:#14161a; --panel:#1b1f26; --line:#2a2e35; --muted:#9299a4; --text:#e6e8ec; --accent:#67a7ff; --surface-code:#111318; --alpha-hover:rgba(255,255,255,.05); --alpha-selected:rgba(255,255,255,.10); --ease:cubic-bezier(.16,1,.3,1); --duration:180ms; --copy-width:88px; }
  * { box-sizing:border-box; }
  body { font:14px/1.5 system-ui,sans-serif; margin:0; background:var(--bg); color:var(--text); }
  header { padding:16px 24px; border-bottom:1px solid var(--line); display:flex; align-items:baseline; gap:14px; }
  h1 { font-size:18px; margin:0; } h2 { font-size:18px; margin:0 0 14px; } h3 { margin:0 0 8px; font-size:15px; }
  .sub,.muted { color:var(--muted); font-size:12px; }
  .shell { display:grid; grid-template-columns:180px minmax(0,1fr); min-height:calc(100vh - 58px); }
  nav { border-right:1px solid var(--line); padding:18px 12px; }
  nav button { display:block; width:100%; text-align:left; margin:0 0 5px; border:0; background:transparent; }
  nav button.active { background:#283142; color:#fff; }
  main { padding:24px; max-width:1100px; width:100%; min-width:0; }
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
  .service > * { min-width:0; }
  .installer-grid { grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr)); align-items:start; }
  .installer-card { min-width:0; }
  .target { border-top:1px solid var(--line); padding:14px 0 2px; margin-top:12px; }
  .target:first-of-type { margin-top:8px; }
  .target-head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .target-head h4 { margin:0; font-size:16px; }
  .target-path { display:block; margin:8px 0 12px; color:var(--muted); overflow-wrap:anywhere; word-break:break-word; }
  .target-actions { display:flex; flex-wrap:wrap; gap:8px; }
  .status { border-radius:999px; padding:2px 8px; font-size:11px; white-space:nowrap; background:#343a46; color:var(--muted); }
  .status.installed { background:#193b2a; color:#6ee7a2; }
  .status.modified,.status.error { background:#462727; color:#fca5a5; }
  .installer-note { margin:10px 0; padding:9px 10px; border-left:3px solid #f59e0b; background:#2a251b; color:#f6d38a; border-radius:4px; }
  button.primary { background:#2864c7; border-color:#3475df; color:#fff; }
  button.danger { color:#fca5a5; border-color:#704040; }
  button:disabled { cursor:not-allowed; opacity:.45; }
  #install-preview { min-width:0; overflow:hidden; }
  .preview-table { table-layout:fixed; }
  .preview-table th:first-child { width:80px; }
  .preview-table th:last-child { width:180px; }
  .preview-table code { white-space:normal; overflow-wrap:anywhere; word-break:break-word; }
  .project-picker { display:flex; gap:8px; align-items:center; margin:12px 0; }
  .project-picker input { flex:1; min-width:0; }
  .tool-card { min-width:0; }
  .tool-head { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:6px; }
  .tool-name { font-size:15px; font-weight:650; background:transparent; padding:0; }
  .tool-call { background:#0f1420; border:1px solid #24304a; color:#8fd0ff; }
  .tool-more { margin-top:8px; } .tool-more summary { cursor:pointer; color:var(--muted); }
  .tool-more table { margin-top:8px; }
  #integrations { min-width:0; }
  nav { background:var(--panel); padding:16px 8px; }
  nav button { min-width:0; min-height:32px; margin-bottom:2px; padding:6px 8px; border-radius:8px; font:inherit; overflow:hidden; text-overflow:ellipsis; transition:background-color var(--duration) var(--ease),color var(--duration) var(--ease); }
  nav button:hover { background:var(--alpha-hover); }
  nav button.active { background:var(--alpha-selected); color:var(--text); }
  .integration-endpoint { display:flex; flex-wrap:wrap; align-items:center; gap:8px 16px; margin-bottom:16px; }
  .integration-endpoint code { flex:1; min-width:0; }
  .integration-note { margin:0 0 24px; color:var(--muted); }
  .integration-grid { grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr)); align-items:start; gap:16px; }
  .integration-card { min-width:0; padding:16px; border-radius:12px; }
  .integration-head { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
  .integration-head h3 { font-size:16px; line-height:24px; margin:0; min-width:0; }
  .integration-path { display:block; margin-bottom:12px; }
  .integration-card pre { background:var(--surface-code); padding:12px; margin:0; font:12px/20px ui-monospace,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; border-radius:8px; }
  .integration-card pre code { background:transparent; padding:0; border-radius:0; }
  .integration-card p { margin:12px 0 0; color:var(--muted); font-size:12px; line-height:16px; }
  .integration-card a { display:inline-block; margin-top:12px; color:var(--accent); font-size:12px; }
  .integration-language { color:var(--muted); font-size:12px; line-height:16px; margin-bottom:4px; }
  .integration-api-heading { margin:24px 0 16px; font-size:16px; line-height:24px; }
  .copy-button { display:inline-grid; flex:0 0 var(--copy-width); width:var(--copy-width); min-height:32px; padding:6px 8px; border:0; border-radius:8px; font:14px/20px system-ui,sans-serif; white-space:nowrap; transition:background-color var(--duration) var(--ease),transform var(--duration) var(--ease); }
  .copy-button:active { transform:scale(.98); }
  .copy-button span { grid-area:1/1; opacity:0; transition:opacity var(--duration) var(--ease); }
  .copy-button[data-state="idle"] .copy-idle,.copy-button[data-state="success"] .copy-success,.copy-button[data-state="error"] .copy-error { opacity:1; }
  nav button:focus-visible,.copy-button:focus-visible,.integration-card a:focus-visible,.integration-card pre:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip-path:inset(50%); white-space:nowrap; border:0; }
  section#integrations.active { animation:integration-enter var(--duration) var(--ease); }
  @keyframes integration-enter { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
  @media (prefers-reduced-motion:reduce) { nav button,.copy-button,.copy-button span { transition:none; } section#integrations.active { animation:none; } .copy-button:active { transform:none; } }
  @media (max-width:720px) { .shell { grid-template-columns:1fr; } nav { border-right:0; border-bottom:1px solid var(--line); display:flex; overflow:auto; } nav button { width:auto; flex-shrink:0; white-space:nowrap; } main { padding:16px; } .integration-endpoint { display:grid; grid-template-columns:minmax(0,1fr) var(--copy-width); } .integration-endpoint > code { grid-row:2; grid-column:1/-1; } .integration-endpoint > .copy-button { grid-row:1; grid-column:2; } }
</style>
</head>
<body>
<header><h1>dcc-mcp</h1><span class="sub">local DCC control · <span id="header-status">ready</span></span></header>
<div class="shell">
<nav>
  <button class="active" data-tab="overview" aria-current="page">Overview</button>
  <button data-tab="tools">Tools</button>
  <button data-tab="logs">Logs</button>
  <button data-tab="install">Install</button>
  <button data-tab="integrations">API/MCP接入</button>
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

  <section id="tools">
    <h2>Tools</h2>
    <p class="muted">There are <strong>no per-DCC tools</strong>. Every instance — Blender, Houdini, Unreal, Maya — is driven by the same handful of meta-tools below; all creative work happens by sending Python through <code>execute_python</code>. Pick an instance to see the exact calls.</p>
    <div class="row">
      <select id="tool-instance"><option value="">— generic (no instance) —</option></select>
      <button onclick="loadTools()">Refresh</button>
      <span class="sub" id="tool-status"></span>
    </div>
    <div id="tool-cards" class="grid"></div>
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
    <p class="muted">The daemon detects local DCC versions and installs into their standard user configuration. Every change is previewed before it is written.</p>
    <div class="row"><button id="scan-installers" onclick="scanInstallers()">Rescan this computer</button><span class="sub" id="installer-platform">Scanning local installations…</span></div>
    <div id="installer-results" class="grid installer-grid"></div>
    <div id="install-preview" class="card" style="margin-top:12px" hidden></div>
  </section>

  <section id="integrations" aria-labelledby="integrations-heading">
    <h2 id="integrations-heading">API/MCP接入</h2>
    <div class="integration-endpoint"><span>MCP · Streamable HTTP</span><code id="integration-endpoint"></code><button class="copy-button" data-state="idle" data-copy-target="integration-endpoint" aria-label="复制 MCP 地址"><span class="copy-idle" aria-hidden="true">复制</span><span class="copy-success" aria-hidden="true">已复制</span><span class="copy-error" aria-hidden="true">复制失败</span></button></div>
    <p class="integration-note">先启动 dcc-mcp，再连接客户端。已有配置时合并 dcc 条目，保留其他服务；~ 表示用户目录，Windows 对应 %USERPROFILE%。保存后在客户端重新连接或重启。</p>
    <div id="integration-clients" class="grid integration-grid"></div>
    <h3 class="integration-api-heading">API 调用示例</h3>
    <div id="integration-api" class="grid integration-grid"></div>
    <span id="integration-feedback" class="sr-only" role="status" aria-live="polite"></span>
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
const INTEGRATIONS = __INTEGRATION_DATA__;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shortTime = value => value ? value.slice(11,23) : '—';

document.querySelectorAll('nav button').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.toggle('active', x === button));
  document.querySelectorAll('nav button').forEach(x => x.setAttribute('aria-current', x === button ? 'page' : 'false'));
  document.querySelectorAll('main section').forEach(x => x.classList.toggle('active', x.id === button.dataset.tab));
  if (button.dataset.tab === 'logs') loadLogs();
  if (button.dataset.tab === 'tools') loadTools();
  if (button.dataset.tab === 'install') scanInstallers();
  if (button.dataset.tab === 'diagnostics') loadDiagnostics();
}));

function renderIntegrations() {
  document.getElementById('integration-endpoint').textContent = INTEGRATIONS.endpoint;
  const cards = examples => examples.map(item => `<article class="card integration-card">
    <div class="integration-head"><h3>${esc(item.name)}</h3><button class="copy-button" data-state="idle" data-copy-target="config-${esc(item.id)}" aria-label="复制 ${esc(item.name)} 配置"><span class="copy-idle" aria-hidden="true">复制</span><span class="copy-success" aria-hidden="true">已复制</span><span class="copy-error" aria-hidden="true">复制失败</span></button></div>
    <code class="integration-path">${esc(item.path)}</code><div class="integration-language">${esc(item.language)}</div>
    <pre tabindex="0"><code id="config-${esc(item.id)}">${esc(item.code)}</code></pre><p>${esc(item.note)}</p>
    ${item.docs ? `<a href="${esc(item.docs)}" target="_blank" rel="noopener noreferrer">官方文档</a>` : ''}</article>`).join('');
  document.getElementById('integration-clients').innerHTML = cards(INTEGRATIONS.clients);
  document.getElementById('integration-api').innerHTML = cards(INTEGRATIONS.api);
}

const copyTimers = new Map();
const copyRequests = new WeakMap();
document.getElementById('integrations').addEventListener('click', async event => {
  const button = event.target.closest('button[data-copy-target]');
  if (!button) return;
  const target = document.getElementById(button.dataset.copyTarget);
  const request = {};
  copyRequests.set(button, request);
  clearTimeout(copyTimers.get(button));
  const feedback = document.getElementById('integration-feedback');
  feedback.textContent = '';
  let state = 'success';
  try {
    await navigator.clipboard.writeText(target.textContent);
  } catch (error) {
    state = 'error';
  }
  if (copyRequests.get(button) !== request) return;
  button.dataset.state = state;
  feedback.textContent = state === 'success' ? '已复制' : '复制失败，请选中代码后手动复制。';
  if (state === 'error') {
    const range = document.createRange();
    range.selectNodeContents(target);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  copyTimers.set(button, setTimeout(() => { button.dataset.state = 'idle'; copyTimers.delete(button); }, 2500));
});
window.addEventListener('pagehide', () => { copyTimers.forEach(clearTimeout); copyTimers.clear(); });
renderIntegrations();

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
      `<div class="card"><span class="muted">MCP endpoint</span><div class="value"><code>${esc(INTEGRATIONS.endpoint)}</code></div></div>`;
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

let pendingInstallPlan=null;
async function scanInstallers(){
  const scanButton=document.getElementById('scan-installers');
  scanButton.disabled=true; scanButton.textContent='Scanning…';
  let data;
  try {
    data=await jsonFetch('/api/installers/scan', {method:'POST'});
  } catch(error) {
    document.getElementById('installer-platform').textContent=`Scan failed: ${error.message}`;
    document.getElementById('installer-results').innerHTML='';
    return;
  } finally {
    scanButton.disabled=false; scanButton.textContent='Rescan this computer';
  }
  document.getElementById('installer-platform').textContent=`${data.platform.system} ${data.platform.release} / ${data.platform.machine}`;
  document.getElementById('install-preview').hidden=true;
  document.getElementById('installer-results').innerHTML=data.installers.map(item=>{
    const targets=item.targets||[];
    const targetRows=targets.length ? targets.map(target=>{
      const state=target.installation||{status:'not_installed',ok:false};
      const managed=state.status!=='not_installed';
      const installLabel=state.status==='modified'||state.status==='error'?'Repair':(managed?'Reinstall':'Install');
      const statusLabel=state.status==='not_installed'?'not managed':state.status.replace('_',' ');
      return `<div class="target">
        <div class="target-head"><h4>${esc(target.label)}</h4><span class="status ${esc(state.status)}">${esc(statusLabel)}</span></div>
        <code class="target-path" title="${esc(target.install_root)}">${esc(target.install_root)}</code>
        <div class="target-actions"><button class="primary" onclick="previewInstall('${esc(item.kind)}','${esc(target.id)}','install')">${installLabel}</button>`+
        (managed?`<button class="danger" onclick="previewInstall('${esc(item.kind)}','${esc(target.id)}','uninstall')">Uninstall</button>`:
          `<button class="danger" disabled title="No managed installation">Uninstall</button>`)+
        `<button onclick="verifyInstall('${esc(item.kind)}','${esc(target.id)}')">Verify</button></div></div>`;
    }).join('') : `<p class="empty">${item.available?'No installation detected.':'Automatic installer is not implemented yet.'}</p>`;
    const projectPicker=item.accepts_project_path?`<div class="project-picker">
      <input id="project-path-${esc(item.kind)}" placeholder="${item.kind==='tuanjie'?'C:/path/to/TuanjieProject':'C:/path/to/Project.uproject'}" aria-label="${esc(item.title||item.kind)} project path">
      <button onclick="addProject('${esc(item.kind)}')">Add project</button></div><p class="sub" id="project-status-${esc(item.kind)}">Project scope installs only into that project's folder.</p>`:'';
    return `<div class="card installer-card"><h3><span class="kind" style="background:${KIND_COLOR[item.kind]||'#556'}">${esc(item.title||item.kind)}</span></h3>
      <p class="muted">${esc(item.strategy)}</p>${item.note?`<p class="installer-note">${esc(item.note)}</p>`:''}${projectPicker}${targetRows}</div>`;
  }).join('');
}

async function addProject(kind){
  const input=document.getElementById('project-path-'+kind);
  const status=document.getElementById('project-status-'+kind);
  const path=input.value.trim();
  if(!path){status.textContent='Enter a project path.';return;}
  try {
    await jsonFetch(`/api/installers/${encodeURIComponent(kind)}/projects`, {
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})
    });
    await scanInstallers();
  } catch(error) {
    status.textContent=error.message;
  }
}

async function previewInstall(kind,targetId,action){
  const plan=await jsonFetch(`/api/installers/${encodeURIComponent(kind)}/plan`, {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target_id:targetId,action})
  });
  pendingInstallPlan=plan;
  const preview=document.getElementById('install-preview');
  preview.innerHTML=`<h3>${esc(action)} ${esc(plan.target.label)}</h3>`+
    `<p class="muted">Review these filesystem changes. This confirmation expires in five minutes.</p>`+
    `<table class="preview-table"><thead><tr><th>Action</th><th>Path</th><th>Description</th></tr></thead><tbody>`+
    plan.changes.map(change=>`<tr><td>${esc(change.action)}</td><td><code>${esc(change.path)}</code></td><td>${esc(change.description)}</td></tr>`).join('')+
    `</tbody></table><div class="row" style="margin-top:12px"><button onclick="applyInstallPlan()">Confirm ${esc(action)}</button>`+
    `<button onclick="document.getElementById('install-preview').hidden=true">Cancel</button></div>`;
  preview.hidden=false;
  preview.scrollIntoView({behavior:'smooth',block:'nearest'});
}

async function applyInstallPlan(){
  const plan=pendingInstallPlan; if(!plan) return;
  const result=await jsonFetch(`/api/installers/${encodeURIComponent(plan.kind)}/apply`, {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan_id:plan.id,token:plan.token})
  });
  pendingInstallPlan=null;
  await scanInstallers();
  const preview=document.getElementById('install-preview');
  const fileResults=(result.files||[]).filter(item=>item.action).map(item=>
    `<div class="service"><code>${esc(item.path)}</code><span>${esc(item.action)}</span></div>`).join('');
  preview.innerHTML=`<h3>${result.ok?'Completed':'Needs attention'}</h3><p>${esc(result.action)} finished for <code>${esc(result.target_id)}</code>.</p>`+
    (!result.ok&&result.manifest?`<p class="muted">Manifest retained: <code>${esc(result.manifest)}</code></p>`:'')+fileResults+
    ((result.next_steps||[]).length?`<ol>${result.next_steps.map(step=>`<li>${esc(step)}</li>`).join('')}</ol>`:
      `<p class="muted">Restart the DCC, then check Overview for its registration.</p>`);
  preview.hidden=false;
}

async function verifyInstall(kind,targetId){
  const result=await jsonFetch(`/api/installers/${encodeURIComponent(kind)}/verify`, {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target_id:targetId})
  });
  const preview=document.getElementById('install-preview');
  preview.innerHTML=`<h3>Verification: ${esc(result.status)}</h3>`+
    (result.checks.length?result.checks.map(item=>`<div class="service"><code>${esc(item.path)}</code><span class="${item.ok?'healthy':'ERROR'}">${item.ok?'OK':'changed or missing'}</span></div>`).join(''):'<p>No managed installation was found.</p>')+
    (result.status!=='not_installed'?`<div class="row" style="margin-top:12px"><button class="danger" onclick="previewInstall('${esc(kind)}','${esc(targetId)}','uninstall')">Uninstall</button></div>`:'');
  preview.hidden=false;
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

let toolCatalog=[];
async function loadTools(){
  const status=document.getElementById('tool-status');
  status.textContent='loading…';
  try {
    const [tools,instances]=await Promise.all([
      jsonFetch('/api/tools'),
      jsonFetch('/api/instances'),
    ]);
    toolCatalog=tools.tools||[];
    const select=document.getElementById('tool-instance');
    const previous=select.value;
    select.innerHTML='<option value="">— generic (no instance) —</option>'+
      instances.map(item=>`<option value="${esc(item.instance_id)}">${esc(item.instance_id)} · ${esc(item.kind||'?')}</option>`).join('');
    if([...select.options].some(o=>o.value===previous)) select.value=previous;
    select.onchange=renderTools;
    renderTools();
    status.textContent=instances.length?`${instances.length} instance(s) · same ${toolCatalog.length} tools drive all`:'no instances registered — showing generic calls';
  } catch(error){ status.textContent=error.message; }
}

function renderTools(){
  const select=document.getElementById('tool-instance');
  const chosen=instanceById(select.value);
  const idArg=chosen?`"${chosen.instance_id}"`:'"<instance_id>"';
  document.getElementById('tool-cards').innerHTML=toolCatalog.map(tool=>{
    const call=tool.name==='list_instances'
      ? `${tool.name}(${(tool.parameters[0]||{}).name?(tool.parameters[0].name+'=…'):''})`
      : tool.signature.replace(/\binstance_id\b/, idArg);
    const scope=tool.targets_instance
      ? (chosen?`<span class="kind" style="background:${KIND_COLOR[chosen.kind]||'#556'}">${esc(chosen.instance_id)}</span>`:'<span class="status">any instance</span>')
      : '<span class="status">daemon-wide</span>';
    const params=tool.parameters.length?`<details class="tool-more"><summary>${tool.parameters.length} parameter(s)</summary>`+
      `<table><thead><tr><th>Name</th><th>Type</th><th>Req</th><th>Description</th></tr></thead><tbody>`+
      tool.parameters.map(p=>`<tr><td><code>${esc(p.name)}</code></td><td>${esc(p.type)}</td><td>${p.required?'yes':'—'}</td><td>${esc(p.description)}</td></tr>`).join('')+
      `</tbody></table></details>`:'';
    const full=tool.description&&tool.description!==tool.summary
      ? `<details class="tool-more"><summary>Full description</summary><pre>${esc(tool.description)}</pre></details>`:'';
    return `<div class="card tool-card">
      <div class="tool-head"><code class="tool-name">${esc(tool.name)}</code>${scope}</div>
      <p class="muted">${esc(tool.summary)}</p>
      <pre class="tool-call">${esc(call)}</pre>${params}${full}</div>`;
  }).join('');
}

function instanceById(id){
  const select=document.getElementById('tool-instance');
  const option=[...select.options].find(o=>o.value===id&&id);
  if(!option) return null;
  const [instance_id,kind]=option.textContent.split(' · ');
  return {instance_id:instance_id.trim(), kind:(kind||'').trim()};
}

</script>
</body>
</html>""".replace("__KIND_COLOR__", json.dumps(_KIND_COLOR))


async def _index(_request: Request) -> HTMLResponse:
    origin = str(_request.base_url).rstrip("/")
    mcp_path = getattr(_request.app.state, "mcp_path", "/mcp")
    data = integration_examples(origin + mcp_path, origin)
    # The data lives in a script element; a custom path must not close it.
    encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return HTMLResponse(_PAGE.replace("__INTEGRATION_DATA__", encoded))


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


def _local_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
        origin_port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and origin_port == request.url.port
    )


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise InstallerError("request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise InstallerError("request body must be a JSON object")
    return body


def _installer_error(exc: InstallerError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


async def _api_installer_scan(_request: Request) -> JSONResponse:
    return JSONResponse(installer_service.scan())


async def _api_installer_plan(request: Request) -> JSONResponse:
    if not _local_origin(request):
        return JSONResponse({"error": "cross-origin installer requests are forbidden"}, status_code=403)
    try:
        body = await _json_body(request)
        return JSONResponse(installer_service.create_plan(
            str(request.path_params.get("kind", "")),
            str(body.get("target_id", "")),
            str(body.get("action", "install")),
        ))
    except InstallerError as exc:
        return _installer_error(exc)


async def _api_installer_apply(request: Request) -> JSONResponse:
    if not _local_origin(request):
        return JSONResponse({"error": "cross-origin installer requests are forbidden"}, status_code=403)
    try:
        body = await _json_body(request)
        return JSONResponse(installer_service.apply_plan(
            str(request.path_params.get("kind", "")),
            str(body.get("plan_id", "")),
            str(body.get("token", "")),
        ))
    except (InstallerError, OSError) as exc:
        logger.warning("installer apply failed: %s", exc)
        return _installer_error(InstallerError(str(exc)))


async def _api_installer_verify(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        return JSONResponse(installer_service.verify(
            str(request.path_params.get("kind", "")),
            str(body.get("target_id", "")),
        ))
    except (InstallerError, OSError) as exc:
        return _installer_error(InstallerError(str(exc)))


async def _api_project(request: Request) -> JSONResponse:
    if not _local_origin(request):
        return JSONResponse({"error": "cross-origin installer requests are forbidden"}, status_code=403)
    try:
        body = await _json_body(request)
        kind = str(request.path_params.get("kind", ""))
        return JSONResponse(installer_service.add_project(kind, str(body.get("path", ""))))
    except (InstallerError, OSError) as exc:
        return _installer_error(InstallerError(str(exc)))

# Tools that address a specific DCC instance (everything except list_instances).
_INSTANCE_TOOLS = {"execute_python", "health", "screenshot"}


def _serialize_tool(tool) -> dict:
    """Flatten a FastMCP tool into the shape the WebUI renders."""
    description = (tool.description or "").strip()
    summary = description.split("\n", 1)[0].strip()
    schema = getattr(tool, "parameters", None) or {}
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    required = set(schema.get("required", []) if isinstance(schema, dict) else [])
    parameters = [
        {
            "name": name,
            "type": spec.get("type", "any"),
            "description": (spec.get("description") or "").strip(),
            "required": name in required,
        }
        for name, spec in properties.items()
    ]
    return {
        "name": tool.name,
        "summary": summary,
        "description": description,
        "signature": f"{tool.name}({', '.join(p['name'] for p in parameters)})",
        "parameters": parameters,
        "targets_instance": tool.name in _INSTANCE_TOOLS,
    }


async def _api_tools(_request: Request) -> JSONResponse:
    tools = sorted(await mcp.list_tools(), key=lambda t: t.name != "list_instances")
    return JSONResponse({"tools": [_serialize_tool(tool) for tool in tools]})


async def _api_diagnostics(_request: Request) -> JSONResponse:
    return JSONResponse(diagnostics_snapshot(core.list_instances()))


def register_webui() -> None:
    """Attach local WebUI routes to the FastMCP HTTP app."""
    mcp.custom_route("/", methods=["GET"])(_index)
    mcp.custom_route("/api/instances", methods=["GET"])(_api_instances)
    mcp.custom_route("/api/tools", methods=["GET"])(_api_tools)
    mcp.custom_route("/api/health/{instance_id}", methods=["GET"])(_api_health)
    mcp.custom_route("/api/logs", methods=["GET"])(_api_logs)
    mcp.custom_route("/api/logs", methods=["DELETE"])(_api_logs_clear)
    mcp.custom_route("/api/installers/scan", methods=["POST"])(_api_installer_scan)
    mcp.custom_route("/api/installers/{kind}/plan", methods=["POST"])(_api_installer_plan)
    mcp.custom_route("/api/installers/{kind}/apply", methods=["POST"])(_api_installer_apply)
    mcp.custom_route("/api/installers/{kind}/verify", methods=["POST"])(_api_installer_verify)
    mcp.custom_route("/api/installers/{kind}/projects", methods=["POST"])(_api_project)
    mcp.custom_route("/api/diagnostics", methods=["GET"])(_api_diagnostics)
