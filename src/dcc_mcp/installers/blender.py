"""Blender user add-on installer."""

from __future__ import annotations

import platform
import re
from pathlib import Path

from dcc_mcp.installers.base import BaseInstaller, Change, InstallerError, Target


class BlenderInstaller(BaseInstaller):
    kind = "blender"
    title = "Blender"
    strategy = "Blender user add-on"
    note = (
        "After installation, open Edit > Preferences > Add-ons, enable "
        "DCC Daemon Bridge, and save preferences."
    )

    def _version_roots(self) -> list[Path]:
        system = platform.system()
        if system == "Windows":
            appdata = self.home / "AppData" / "Roaming"
            base = appdata / "Blender Foundation" / "Blender"
        elif system == "Darwin":
            base = self.home / "Library" / "Application Support" / "Blender"
        else:
            base = self.home / ".config" / "blender"
        if not base.is_dir():
            return []
        return sorted(
            path.resolve()
            for path in base.iterdir()
            if (
                path.is_dir()
                and re.fullmatch(r"[0-9]+\.[0-9]+", path.name)
                and path.resolve().is_relative_to(self.home)
            )
        )

    def detect(self) -> list[Target]:
        return [
            Target(
                id=f"blender-{root.name}", kind=self.kind, version=root.name,
                label=f"Blender {root.name}", install_root=str(root),
                detected_from="user_preferences",
            )
            for root in self._version_roots()
        ]

    def _module_root(self, target: Target) -> Path:
        version_root = Path(target.install_root).resolve()
        if version_root not in self._version_roots():
            raise InstallerError("Blender target is no longer available")
        return version_root / "scripts" / "addons" / "dcc_daemon_blender"

    def changes(self, target: Target) -> list[Change]:
        module_root = self._module_root(target)
        return [
            Change("write", str(module_root / "__init__.py"), "Install Blender add-on"),
            Change("write", str(module_root / "dcc_socket_server.py"), "Install shared connector"),
        ]

    def install(self, target: Target) -> dict:
        result = self._write_files(self.copy_payload(self._module_root(target)), target)
        result["next_steps"] = [
            "Restart Blender.",
            "Open Edit > Preferences > Add-ons and enable DCC Daemon Bridge.",
            "Save preferences so the add-on remains enabled after restart.",
        ]
        return result
