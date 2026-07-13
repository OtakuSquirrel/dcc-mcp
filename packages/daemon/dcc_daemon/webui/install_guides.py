"""DCC plugin installation metadata and development-repo ZIP builder."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

KINDS = ("blender", "houdini", "ue", "maya")

_GUIDES = {
    "blender": {
        "title": "Blender",
        "bridge": "bpy.app.timers",
        "folder": "dcc_daemon_blender",
        "persistent": "Install the generated ZIP from Edit → Preferences → Add-ons, then enable DCC Daemon Bridge.",
        "temporary": "blender --python dcc_daemon_blender/__init__.py",
    },
    "houdini": {
        "title": "Houdini",
        "bridge": "hdefereval.executeInMainThreadWithResult",
        "folder": "dcc_daemon_houdini",
        "persistent": "Place the generated folder on $HOUDINI_PATH and call dcc_daemon_houdini.start() from 123.py or 456.py.",
        "temporary": "import dcc_daemon_houdini; dcc_daemon_houdini.start()",
    },
    "ue": {
        "title": "Unreal Engine",
        "bridge": "Slate post-tick callback",
        "folder": "dcc_daemon_ue",
        "persistent": "Extract into Content/Python and add __init__.py to Project Settings → Python → Startup Scripts.",
        "temporary": "exec(open(r'<path>\\dcc_daemon_ue\\__init__.py').read())",
    },
    "maya": {
        "title": "Maya",
        "bridge": "maya.utils.executeInMainThreadWithResult",
        "folder": "dcc_daemon_maya",
        "persistent": "Place the generated folder on Maya's PYTHONPATH and call dcc_daemon_maya.start() from userSetup.py.",
        "temporary": "import dcc_daemon_maya; dcc_daemon_maya.start()",
    },
}


def list_guides(register_address: str) -> list[dict]:
    return [
        {"kind": kind, "register_address": register_address, **_GUIDES[kind]}
        for kind in KINDS
    ]


def build_plugin_zip(kind: str) -> tuple[bytes, str]:
    """Build a two-file plugin ZIP from this development checkout."""
    if kind not in _GUIDES:
        raise KeyError(kind)

    repo_root = Path(__file__).resolve().parents[4]
    plugin_init = repo_root / "plugins" / f"{kind}_daemon" / "__init__.py"
    connector = repo_root / "plugins" / "common" / "dcc_socket_server.py"
    if not plugin_init.is_file() or not connector.is_file():
        raise FileNotFoundError(
            "plugin sources are unavailable; run the daemon from the dcc-mcp checkout"
        )

    folder = _GUIDES[kind]["folder"]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(plugin_init, f"{folder}/__init__.py")
        archive.write(connector, f"{folder}/dcc_socket_server.py")
    return output.getvalue(), f"{folder}.zip"
