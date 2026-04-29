#!/usr/bin/env python3
"""Export every MCP package's CATEGORY_DEFS into a single JSON bundle.

The Tauri manager's Tools tab renders tool catalogs from this bundle —
Python remains the single source of truth, the frontend stays dumb.

Usage: `python scripts/sync_tool_defs.py`

Re-run whenever any `packages/*/tool_defs.py` changes, then commit the
generated file. Intentionally zero dependencies so it runs against the
repo's uv venv or any bare Python.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "tauri-manager" / "src" / "tool-defs.generated.json"

# (mcp_server_name, module_file). The MCP server name matches the key
# written into `.claude/settings.json` — see known_mcps() in project.rs.
SOURCES = [
    ("blender", REPO_ROOT / "packages/blender/blender_mcp/tool_defs.py"),
    ("houdini", REPO_ROOT / "packages/houdini/houdini_mcp/tool_defs.py"),
    ("ue",      REPO_ROOT / "packages/ue/ue_mcp/tool_defs.py"),
    ("maya",    REPO_ROOT / "packages/maya/maya_mcp/tool_defs.py"),
    ("os",      REPO_ROOT / "packages/os/os_mcp/tool_defs.py"),
]


def load_defs(path: Path) -> dict:
    if not path.exists():
        return {}
    spec = importlib.util.spec_from_file_location(f"_td_{path.stem}", path)
    if spec is None or spec.loader is None:
        return {}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {
        "categories": getattr(mod, "CATEGORY_DEFS", {}),
        "default_disabled": list(getattr(mod, "DEFAULT_DISABLED_TOOLS", [])),
    }


def main() -> int:
    bundle: dict = {}
    missing: list[str] = []
    for name, path in SOURCES:
        defs = load_defs(path)
        if not defs:
            missing.append(f"{name} ({path.relative_to(REPO_ROOT)})")
            continue
        bundle[name] = defs

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    print(f"  included: {', '.join(bundle.keys())}")
    if missing:
        print(f"  skipped (no tool_defs.py): {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
