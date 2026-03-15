# dcc-mcp

Agent-oriented MCP servers for DCC applications — **Blender**, **Houdini**, and **Unreal Engine**.

```
  Agent (Claude, etc.)
    │
    ├── stdio/MCP ──▶  blender-mcp  ──TCP/JSON──▶  Blender
    ├── stdio/MCP ──▶  houdini-mcp  ──RPyC─────▶  Houdini
    └── stdio/MCP ──▶  ue-mcp       ──TCP/JSON──▶  Unreal Engine
```

An AI agent connects to one or more DCC MCP servers via the standard [Model Context Protocol](https://modelcontextprotocol.io). Each server translates MCP tool calls into DCC-native API calls, giving the agent full programmatic control over the application.

## Features

| DCC | Tools | Categories | Protocol | Status |
|-----|-------|------------|----------|--------|
| Blender | 55 | 13 | TCP + JSON (bpy.app.timers) | Production |
| Houdini | 49 | 11 | RPyC (remote Python) | Production |
| Unreal Engine | — | 12 | TCP + JSON (Python Remote Exec) | Skeleton |

- **Shared core library** (`dcc-mcp-core`) — config, session registry, connection management, middleware, health checks, tool registry
- **Multi-instance support** — connect to multiple DCC instances simultaneously, switch between them
- **Session management** — file-based registry at `~/{{app_name}}/sessions/`, automatic port allocation
- **Health monitoring** — OS-level checks (window responding, CPU usage, port status) that never hang
- **Web dashboard** — real-time monitoring UI with SSE live updates
- **Tool guard middleware** — per-tool enable/disable via config

## Quick Start

### Install

```bash
# Clone the repo
git clone https://github.com/OtakuSquirrel/dcc-mcp.git
cd dcc-mcp

# Create virtualenv
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install packages (editable)
pip install -e packages/core[webui]
pip install -e packages/blender
pip install -e packages/houdini
```

### Configure Claude Desktop / Cursor

Add to your MCP config (`claude_desktop_config.json` or Cursor settings):

```json
{
  "mcpServers": {
    "blender": {
      "command": "blender-mcp",
      "args": []
    },
    "houdini": {
      "command": "houdini-mcp",
      "args": []
    }
  }
}
```

### Launch

```bash
# Start a DCC MCP server (stdio mode, used by MCP clients)
blender-mcp
houdini-mcp

# Start the web dashboard
dcc-mcp-webui              # http://127.0.0.1:8420
dcc-mcp-webui --port 9000  # custom port
```

### DCC Plugin Setup

**Blender**: Copy `plugins/blender/` to Blender's addons directory as `blender_mcp`, then enable in Preferences > Add-ons. Or launch with:

```bash
blender --python plugins/blender/start_mcp.py
```

**Houdini**: Copy `plugins/houdini/houdini_mcp_startup.py` to your Houdini scripts directory (`$HOUDINI_USER_PREF_DIR/scripts/`), or set `HOUDINI_MCP_ENABLED=1` before launching.

## Project Structure

```
dcc-mcp/
├── packages/
│   ├── core/                  # Shared library (dcc-mcp-core)
│   │   └── dcc_mcp_core/
│   │       ├── config.py          # Thread-safe JSON config
│   │       ├── registry.py        # File-based session registry
│   │       ├── connection.py      # ConnectionBase + ConnectionManagerBase
│   │       ├── middleware.py      # ClientName + ToolGuard middleware
│   │       ├── health.py          # OS-level health checks (Win32)
│   │       ├── tool_registry.py   # Category/tool metadata framework
│   │       └── webui/             # Web dashboard (FastAPI + Jinja2)
│   │           ├── app.py             # Routes + Jinja2 template rendering
│   │           ├── dcc_bridge.py      # Aggregates all DCC registries
│   │           ├── routes/            # API route modules
│   │           │   ├── session_routes.py
│   │           │   ├── tool_routes.py
│   │           │   ├── config_routes.py
│   │           │   └── health_routes.py
│   │           └── templates/         # Jinja2 templates
│   │               ├── base.html          # Shared layout + per-DCC theming
│   │               ├── index.html         # Overview (all DCCs)
│   │               ├── dashboard.html     # Per-DCC sessions + health
│   │               ├── tools.html         # Tool management + toggles
│   │               ├── config.html        # Port range, launch, paths
│   │               └── agent_config.html  # Agent integration
│   │
│   ├── blender/               # Blender MCP server
│   │   └── blender_mcp/
│   │       ├── connection.py      # TCP+JSON connection
│   │       ├── server.py          # FastMCP server
│   │       ├── tool_defs.py       # 55 tools in 13 categories
│   │       └── tools/             # Tool implementations
│   │
│   ├── houdini/               # Houdini MCP server
│   │   └── houdini_mcp/
│   │       ├── connection.py      # RPyC connection
│   │       ├── server.py          # FastMCP server
│   │       ├── tool_defs.py       # 49 tools in 11 categories
│   │       ├── utils.py           # obtain/obtain_list helpers
│   │       └── tools/             # Tool implementations
│   │
│   └── ue/                    # Unreal Engine MCP server (skeleton)
│       └── ue_mcp/
│
├── plugins/
│   ├── blender/               # Blender addon (socket server)
│   │   ├── __init__.py            # bl_info, N-panel UI
│   │   └── socket_server.py       # Non-blocking TCP on bpy.app.timers
│   │
│   └── houdini/               # Houdini startup script
│       └── houdini_mcp_startup.py
│
├── icons/                    # DCC brand icons (PNG/SVG)
├── start_webui.bat           # One-click dashboard launcher
└── README.md
```

## Tool Categories

### Blender (55 tools)

| Category | Tools | Description |
|----------|-------|-------------|
| Scene | 4 | Create, open, save scenes |
| Objects | 7 | Create, delete, transform, inspect objects |
| Materials | 5 | Create materials, shader nodes |
| Modifiers | 4 | Add, remove, apply modifiers |
| Animation | 4 | Keyframes, timeline control |
| Camera | 3 | Create and configure cameras |
| Lighting | 3 | Lights and HDRI environment |
| Rendering | 4 | Render engine, resolution, output |
| Viewport | 3 | Screenshots, shading, camera view |
| Import/Export | 2 | FBX, OBJ, USD, glTF |
| Execution | 1 | Execute Python in Blender |
| Lifecycle | 6 | Start/stop, health, addon management |
| Sessions | 9 | Multi-instance, port scanning, pool |

### Houdini (49 tools)

| Category | Tools | Description |
|----------|-------|-------------|
| Scene | 4 | Create, open, save HIP files |
| Nodes | 5 | Create, delete, inspect, traverse nodes |
| Parameters | 3 | Read/write node parameters |
| Connections | 3 | Wire/unwire node connections |
| Execution | 3 | Python execution, cook, errors |
| Geometry | 3 | Points, prims, attributes |
| Viewport | 2 | Screenshots, display settings |
| Render | 2 | ROP render, OpenGL preview |
| Verification | 3 | Screenshot compare, scene diff |
| Lifecycle | 8 | Start/stop, health, startup scripts |
| Sessions | 12 | Multi-instance, pool, config |

## Configuration

Each DCC stores config at `~/<app_name>/config.json`:

```json
{
  "port_range": [19811, 19899],
  "disabled_tools": [],
  "human_launch": { "auto_start": false },
  "agent_launch": { "auto_start": true }
}
```

| Setting | Description |
|---------|-------------|
| `port_range` | Port range for auto-allocation |
| `disabled_tools` | List of tool names to disable |
| `dcc_search_paths` | Directories to scan for DCC installs |

Port ranges:
- Houdini: 18811–18899
- Blender: 19811–19899
- Unreal Engine: 20811–20899

## Web Dashboard

Launch with `dcc-mcp-webui` or double-click `start_webui.bat` (requires `pip install dcc-mcp-core[webui]`).

The dashboard is a multi-page Jinja2 app with per-DCC theming:

| Page | URL | Description |
|------|-----|-------------|
| Overview | `/` | All DCCs at a glance — icons, session counts, tool counts |
| Dashboard | `/{dcc}/` | Sessions, health checks, quick stats |
| Config | `/{dcc}/config` | Port range, launch settings, search paths |
| Tools | `/{dcc}/tools` | Browse categories, enable/disable individual tools |
| Agent | `/{dcc}/agent-config` | Agent integration (coming soon) |

Each DCC has its own accent color (Blender orange, Houdini red, UE blue) and icon that automatically applies when navigating between DCCs.

Features:
- **Per-DCC theming** — accent colors and icons switch automatically
- **DCC switcher** — quick navigation between Blender, Houdini, UE
- **Tool toggles** — enable/disable tools with immediate effect, bulk actions
- **Health monitoring** — OS-level verdicts (healthy/busy/hung/dead)
- **Live updates** via Server-Sent Events
- **Responsive** — works on desktop and mobile

## Architecture

### Shared Core (`dcc-mcp-core`)

All DCC packages depend on `dcc-mcp-core` which provides:

- **`DCCConfig`** — parameterized config manager with thread-safe JSON persistence
- **`SessionRegistry`** — file-based session tracking with port allocation
- **`ConnectionBase` / `ConnectionManagerBase`** — abstract base classes for DCC connections with multi-instance proxy support
- **`ClientNameMiddleware`** — extracts MCP client name from initialization
- **`ToolGuardMiddleware`** — blocks disabled tools at the MCP level
- **`check_health()`** — comprehensive OS-level health check (PID, window responding, CPU, port, protocol)
- **`ToolRegistry`** — static metadata framework with category/tool indexing

### Connection Architecture

Each DCC uses a different protocol:

- **Blender**: TCP socket server running on `bpy.app.timers` (main-thread safe). The addon accepts newline-delimited JSON commands and executes them synchronously on Blender's main thread.
- **Houdini**: RPyC (Remote Python Call) gives direct access to `hou` module. Uses `obtain()`/`obtain_list()` to convert netref proxies to native Python types.
- **Unreal Engine**: TCP socket with length-prefix framing, connected to UE's Python Remote Execution plugin.

### Health Check System

Health checks are pure OS-level queries that **never hang**, even if the DCC is completely frozen:

1. **`find_pid_for_port()`** — find which process owns a port
2. **`check_window_responding()`** — Win32 `IsHungAppWindow` API
3. **`sample_cpu_percent()`** — Win32 `GetProcessTimes` kernel API
4. **`tcp_ping_with_timeout()`** — daemon-thread ping with hard timeout

Verdicts: `healthy` | `busy` | `hung` | `dead` | `no_protocol`

## Development

```bash
# Install all packages in dev mode
pip install -e packages/core[dev,webui]
pip install -e packages/blender
pip install -e packages/houdini

# Run tests
pytest packages/core/tests/
pytest packages/blender/tests/
pytest packages/houdini/tests/

# Lint
ruff check packages/
```

## License

MIT
