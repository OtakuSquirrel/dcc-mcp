# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata


repo_root = Path(SPECPATH).parents[1]
daemon_root = repo_root / "packages" / "daemon"

datas = []
for distribution in ("fastmcp", "mcp", "pydantic", "starlette", "uvicorn"):
    datas += copy_metadata(distribution)

payloads = {
    repo_root / "plugins" / "common" / "dcc_socket_server.py": (
        "dcc_daemon/installers/payloads/common"
    ),
    repo_root / "plugins" / "blender_daemon" / "__init__.py": (
        "dcc_daemon/installers/payloads/blender_daemon"
    ),
    repo_root / "plugins" / "houdini_daemon" / "__init__.py": (
        "dcc_daemon/installers/payloads/houdini_daemon"
    ),
    repo_root / "plugins" / "maya_daemon" / "__init__.py": (
        "dcc_daemon/installers/payloads/maya_daemon"
    ),
    repo_root / "plugins" / "ue_daemon" / "__init__.py": (
        "dcc_daemon/installers/payloads/ue_daemon"
    ),
}
datas += [(str(source), destination) for source, destination in payloads.items()]

hiddenimports = (
    collect_submodules("uvicorn.lifespan")
    + collect_submodules("uvicorn.loops")
    + collect_submodules("uvicorn.protocols")
)

a = Analysis(
    [str(repo_root / "packaging" / "windows" / "daemon_entry.py")],
    pathex=[str(daemon_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dcc-daemon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DCC-MCP-Portable-x64",
)
