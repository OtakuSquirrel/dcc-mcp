"""DCC plugin installation/uninstallation routes.

Handles detecting DCC versions on the system and installing/uninstalling
MCP plugins into them:
- Blender: symlink (or copy) addon to addons directory
- Houdini: write packages JSON (clean, no 456.py modification)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/install", tags=["install"])

# Project root: dcc-mcp/
_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_PLUGINS_DIR = _PROJECT_ROOT / "plugins"


# ---------------------------------------------------------------------------
# Blender detection & install
# ---------------------------------------------------------------------------

def _blender_base() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Blender Foundation" / "Blender"


def detect_blender_versions() -> list[dict[str, Any]]:
    base = _blender_base()
    if not base.exists():
        return []
    versions = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or not d.name[0].isdigit():
            continue
        addons_dir = d / "scripts" / "addons"
        target = addons_dir / "blender_mcp"
        installed = target.exists()
        is_symlink = target.is_symlink() if installed else False
        versions.append({
            "version": d.name,
            "pref_dir": str(d),
            "addons_dir": str(addons_dir),
            "installed": installed,
            "install_method": "symlink" if is_symlink else ("copy" if installed else None),
        })
    return versions


def install_blender_plugin(version: str) -> dict[str, Any]:
    base = _blender_base() / version / "scripts" / "addons"
    if not base.parent.exists():
        base.parent.mkdir(parents=True, exist_ok=True)
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)

    target = base / "blender_mcp"
    source = _PLUGINS_DIR / "blender"

    if not source.exists():
        raise HTTPException(400, f"Plugin source not found: {source}")

    # Remove existing install
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        shutil.rmtree(str(target))

    # Try symlink first, fall back to copy
    method = "symlink"
    try:
        os.symlink(str(source), str(target), target_is_directory=True)
    except OSError:
        method = "copy"
        shutil.copytree(str(source), str(target))

    logger.info("Installed Blender plugin (%s) to %s", method, target)
    return {"installed": True, "method": method, "path": str(target)}


def uninstall_blender_plugin(version: str) -> dict[str, Any]:
    target = _blender_base() / version / "scripts" / "addons" / "blender_mcp"
    if not target.exists() and not target.is_symlink():
        return {"uninstalled": False, "reason": "not installed"}

    if target.is_symlink():
        target.unlink()
    else:
        shutil.rmtree(str(target))

    logger.info("Uninstalled Blender plugin from %s", target)
    return {"uninstalled": True}


# ---------------------------------------------------------------------------
# Houdini detection & install (packages system)
# ---------------------------------------------------------------------------

def _houdini_pref_dirs() -> list[Path]:
    """Find all Houdini user preference directories."""
    candidates = []
    for parent in [Path.home(), Path.home() / "Documents"]:
        if not parent.exists():
            continue
        try:
            for d in parent.iterdir():
                if d.is_dir() and d.name.startswith("houdini") and len(d.name) > 7 and d.name[7].isdigit():
                    candidates.append(d)
        except PermissionError:
            continue
    return sorted(set(candidates), key=lambda p: p.name)


def _find_all_dirs_for_version(version: str) -> list[Path]:
    """Find ALL pref dirs for a given Houdini version (may be in ~ and ~/Documents)."""
    return [d for d in _houdini_pref_dirs() if d.name.replace("houdini", "") == version]


def detect_houdini_versions() -> list[dict[str, Any]]:
    versions = []
    seen = set()
    for d in _houdini_pref_dirs():
        version = d.name.replace("houdini", "")
        if version in seen:
            continue
        seen.add(version)
        # Check ALL dirs for this version (~/houdiniXX and ~/Documents/houdiniXX)
        all_dirs = _find_all_dirs_for_version(version)
        installed = any((dd / "packages" / "dcc_mcp.json").exists() for dd in all_dirs)
        has_legacy = False
        for dd in all_dirs:
            legacy_456 = dd / "scripts" / "456.py"
            if legacy_456.exists():
                try:
                    content = legacy_456.read_text(encoding="utf-8")
                    if "[HoudiniMCP]" in content or "houdini_mcp_startup" in content:
                        has_legacy = True
                        break
                except OSError:
                    pass
        pref_dir = all_dirs[0]
        versions.append({
            "version": version,
            "pref_dir": str(pref_dir),
            "packages_dir": str(pref_dir / "packages"),
            "installed": installed,
            "has_legacy_456": has_legacy,
        })
    return versions


def _build_houdini_package_json() -> dict:
    """Build the Houdini packages JSON content."""
    plugin_dir = str(_PLUGINS_DIR / "houdini").replace("\\", "/")
    return {
        "recommends": "houdini_version >= '20.0'",
        "env": [
            {"HOUDINI_MCP_ENABLED": "1"},
        ],
        "path": plugin_dir,
    }


def install_houdini_plugin(version: str) -> dict[str, Any]:
    all_dirs = _find_all_dirs_for_version(version)
    if not all_dirs:
        raise HTTPException(404, f"Houdini {version} pref dir not found")

    content = _build_houdini_package_json()
    installed_paths = []
    for pref_dir in all_dirs:
        pkg_dir = pref_dir / "packages"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        pkg_file = pkg_dir / "dcc_mcp.json"
        pkg_file.write_text(json.dumps(content, indent=2), encoding="utf-8")
        installed_paths.append(str(pkg_file))
        logger.info("Installed Houdini package to %s", pkg_file)

    return {"installed": True, "paths": installed_paths, "content": content}


def uninstall_houdini_plugin(version: str) -> dict[str, Any]:
    all_dirs = _find_all_dirs_for_version(version)
    if not all_dirs:
        raise HTTPException(404, f"Houdini {version} pref dir not found")

    removed = []
    for pref_dir in all_dirs:
        pkg_file = pref_dir / "packages" / "dcc_mcp.json"
        if pkg_file.exists():
            pkg_file.unlink()
            removed.append(str(pkg_file))
            logger.info("Uninstalled Houdini package from %s", pkg_file)

    return {"uninstalled": len(removed) > 0, "removed": removed}


def cleanup_houdini_legacy(version: str) -> dict[str, Any]:
    """Remove legacy 456.py injection and copied startup script from ALL pref dirs."""
    all_dirs = _find_all_dirs_for_version(version)
    if not all_dirs:
        raise HTTPException(404, f"Houdini {version} pref dir not found")

    cleaned = []
    for pref_dir in all_dirs:
        # Remove [HoudiniMCP] line from 456.py
        legacy_456 = pref_dir / "scripts" / "456.py"
        if legacy_456.exists():
            try:
                lines = legacy_456.read_text(encoding="utf-8").splitlines()
                new_lines = [l for l in lines if "[HoudiniMCP]" not in l and "houdini_mcp_startup" not in l]
                if len(new_lines) != len(lines):
                    content = "\n".join(new_lines).strip()
                    if content:
                        legacy_456.write_text(content + "\n", encoding="utf-8")
                    else:
                        legacy_456.unlink()
                    cleaned.append(f"456.py ({pref_dir.name})")
            except OSError as e:
                logger.warning("Failed to clean 456.py in %s: %s", pref_dir, e)

        # Remove copied startup script
        startup = pref_dir / "scripts" / "houdini_mcp_startup.py"
        if startup.exists():
            startup.unlink()
            cleaned.append(f"houdini_mcp_startup.py ({pref_dir.name})")

        # Remove copied pythonrc.py if it's ours
        pythonrc = pref_dir / "scripts" / "pythonrc.py"
        if pythonrc.exists():
            try:
                content = pythonrc.read_text(encoding="utf-8")
                if "HoudiniMCP" in content or "houdini_mcp_startup" in content:
                    pythonrc.unlink()
                    cleaned.append(f"pythonrc.py ({pref_dir.name})")
            except OSError:
                pass

    return {"cleaned": cleaned}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/detect/{dcc}")
async def detect_versions(dcc: str):
    """Detect installed versions of a DCC application."""
    if dcc == "blender":
        return {"dcc": dcc, "versions": detect_blender_versions()}
    elif dcc == "houdini":
        return {"dcc": dcc, "versions": detect_houdini_versions()}
    else:
        return {"dcc": dcc, "versions": [], "note": "Detection not implemented for this DCC"}


@router.post("/{dcc}/{version}")
async def install_plugin(dcc: str, version: str):
    """Install the MCP plugin for a specific DCC version."""
    if dcc == "blender":
        return install_blender_plugin(version)
    elif dcc == "houdini":
        return install_houdini_plugin(version)
    else:
        raise HTTPException(400, f"Install not implemented for {dcc}")


@router.delete("/{dcc}/{version}")
async def uninstall_plugin(dcc: str, version: str):
    """Uninstall the MCP plugin from a specific DCC version."""
    if dcc == "blender":
        return uninstall_blender_plugin(version)
    elif dcc == "houdini":
        return uninstall_houdini_plugin(version)
    else:
        raise HTTPException(400, f"Uninstall not implemented for {dcc}")


@router.post("/houdini/{version}/cleanup-legacy")
async def cleanup_legacy(version: str):
    """Remove legacy 456.py injection from a Houdini version."""
    return cleanup_houdini_legacy(version)
