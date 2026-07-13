"""Maya Modules installer."""

from __future__ import annotations

import re
import platform
from pathlib import Path

from dcc_daemon.installers.base import BaseInstaller, Change, InstallerError, Target


class MayaInstaller(BaseInstaller):
    kind = "maya"
    title = "Maya"
    strategy = "Maya Module (.mod)"

    def _preference_roots(self) -> list[Path]:
        system = platform.system()
        if system == "Windows":
            bases = [self.home / "maya", self.home / "Documents" / "maya"]
        elif system == "Darwin":
            bases = [
                self.home / "maya",
                self.home / "Library" / "Preferences" / "Autodesk" / "maya",
            ]
        else:
            bases = [self.home / "maya"]
        roots: list[Path] = []
        for base in bases:
            if base.is_dir():
                roots.extend(
                    path for path in base.iterdir()
                    if path.is_dir() and path.resolve().is_relative_to(self.home)
                )
        return sorted({path.resolve() for path in roots})

    def detect(self) -> list[Target]:
        targets = []
        for root in self._preference_roots():
            if not re.fullmatch(r"20[0-9]{2}", root.name):
                continue
            targets.append(Target(
                id=f"maya-{root.name}", kind=self.kind, version=root.name,
                label=f"Maya {root.name}", install_root=str(root),
                detected_from="user_preferences",
            ))
        return targets

    def _paths(self, target: Target) -> tuple[Path, Path, Path]:
        preference_root = Path(target.install_root).resolve()
        if preference_root not in self._preference_roots():
            raise InstallerError("Maya target is no longer available")
        payload_root = self.state_root / "plugins" / "maya" / target.version
        module_root = payload_root / "scripts" / "dcc_daemon_maya"
        module_file = preference_root / "modules" / "dcc_daemon.mod"
        return payload_root, module_root, module_file

    def changes(self, target: Target) -> list[Change]:
        payload_root, module_root, module_file = self._paths(target)
        return [
            Change("write", str(module_root / "__init__.py"), "Install Maya adapter"),
            Change("write", str(module_root / "dcc_socket_server.py"), "Install shared connector"),
            Change("write", str(payload_root / "scripts" / "userSetup.py"), "Start the connector after Maya initializes"),
            Change("write", str(module_file), "Register the dcc-daemon Maya Module"),
        ]

    def install(self, target: Target) -> dict:
        payload_root, module_root, module_file = self._paths(target)
        files = self.copy_payload(module_root)
        files[payload_root / "scripts" / "userSetup.py"] = (
            "# Managed by dcc-daemon.\n"
            "import maya.utils\n\n"
            "maya.utils.executeDeferred(\n"
            "    \"import dcc_daemon_maya; dcc_daemon_maya.start()\"\n"
            ")\n"
        ).encode("utf-8")
        module_path = str(payload_root).replace("\\", "/")
        files[module_file] = (
            f"+ dcc_daemon 0.1.0 {module_path}\n"
            "DCC_DAEMON_ENABLED = 1\n"
        ).encode("utf-8")
        result = self._write_files(files, target)
        result["next_steps"] = ["Restart Maya and check Overview for registration."]
        return result
