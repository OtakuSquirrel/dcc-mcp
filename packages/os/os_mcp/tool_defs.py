"""Tool category definitions for os-mcp.

Static metadata — used by the Tauri manager to render the tool management
UI. Format mirrors the DCC MCP packages' tool_defs.py.
"""

from __future__ import annotations

CATEGORY_DEFS: dict[str, dict] = {
    "Processes": {
        "desc": "Inspect and manage OS processes",
        "tools": {
            "list_dcc_instances": "Scan port range for running DCC processes",
            "get_process_info": "Get exe path, memory, cpu, start time for a PID",
            "kill_process": "Terminate a process by PID (force-kill optional)",
        },
    },
    "Windows": {
        "desc": "Inspect and manipulate GUI windows",
        "tools": {
            "is_window_responding": "Check if a process's main window is responding",
            "find_modal_dialogs": "Detect modal/popup dialogs blocking a process",
            "bring_window_to_front": "Bring a process's main window to the foreground",
        },
    },
    "Health": {
        "desc": "Composite OS-level diagnostics for stuck DCC instances",
        "tools": {
            "check_dcc_health": "Run full health check on a DCC port (window + cpu + dialogs)",
        },
    },
    "Screenshot": {
        "desc": "Capture desktop or window screenshots",
        "tools": {
            "take_screenshot": "Capture the full desktop as PNG",
            "take_window_screenshot": "Capture a specific process's main window",
        },
    },
    "Clipboard": {
        "desc": "Read and write the system clipboard",
        "tools": {
            "read_clipboard": "Read clipboard content as text",
            "write_clipboard": "Write text to clipboard",
        },
    },
}

DEFAULT_DISABLED_TOOLS: list[str] = []
