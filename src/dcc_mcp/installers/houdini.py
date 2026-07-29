"""Houdini Packages installer."""

from __future__ import annotations

import json
import platform
import re
from pathlib import Path

from dcc_mcp.installers.base import BaseInstaller, Change, InstallerError, Target


class HoudiniInstaller(BaseInstaller):
    kind = "houdini"
    title = "Houdini"
    strategy = "Houdini Package"

    def _preference_roots(self) -> list[Path]:
        system = platform.system()
        if system == "Windows":
            bases = [self.home, self.home / "Documents"]
            patterns = ["houdini[0-9]*.[0-9]*"]
        elif system == "Darwin":
            bases = [self.home, self.home / "Library" / "Preferences" / "houdini"]
            patterns = ["houdini[0-9]*.[0-9]*", "[0-9]*.[0-9]*"]
        else:
            bases = [self.home]
            patterns = ["houdini[0-9]*.[0-9]*"]

        # One target per version. Later bases are the platform-standard location
        # and intentionally win over legacy/accidental duplicate directories.
        by_version: dict[str, Path] = {}
        for base, pattern in zip(bases, patterns, strict=False):
            for path in base.glob(pattern):
                match = re.search(r"([0-9]+\.[0-9]+)$", path.name)
                resolved = path.resolve()
                if path.is_dir() and match and resolved.is_relative_to(self.home):
                    by_version[match.group(1)] = resolved
        if system == "Windows":
            for path in (self.home / "Documents").glob("houdini[0-9]*.[0-9]*"):
                match = re.search(r"([0-9]+\.[0-9]+)$", path.name)
                resolved = path.resolve()
                if path.is_dir() and match and resolved.is_relative_to(self.home):
                    by_version[match.group(1)] = resolved
        return [by_version[version] for version in sorted(by_version)]

    def detect(self) -> list[Target]:
        targets = []
        for root in self._preference_roots():
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)$", root.name, re.IGNORECASE)
            if not match:
                continue
            version = match.group(1)
            targets.append(Target(
                id=f"houdini-{version}", kind=self.kind, version=version,
                label=f"Houdini {version}", install_root=str(root),
                detected_from="user_preferences",
            ))
        return targets

    def _paths(self, target: Target) -> tuple[Path, Path, Path]:
        preference_root = Path(target.install_root).resolve()
        if preference_root not in self._preference_roots():
            raise InstallerError("Houdini target is no longer available")
        payload_root = self.state_root / "plugins" / "houdini" / target.version
        module_root = payload_root / "python" / "dcc_daemon_houdini"
        package_file = preference_root / "packages" / "dcc_daemon.json"
        return payload_root, module_root, package_file

    def changes(self, target: Target) -> list[Change]:
        payload_root, module_root, package_file = self._paths(target)
        return [
            Change("write", str(module_root / "__init__.py"), "Install Houdini adapter"),
            Change("write", str(module_root / "dcc_socket_server.py"), "Install shared connector"),
            Change("write", str(payload_root / "scripts" / "123.py"), "Start connector for new sessions"),
            Change("write", str(payload_root / "scripts" / "456.py"), "Start connector when a scene loads"),
            Change("write", str(package_file), "Register the dcc-daemon Houdini Package"),
        ]

    def install(self, target: Target) -> dict:
        payload_root, module_root, package_file = self._paths(target)
        files = self.copy_payload(module_root)
        startup = (
            "# Managed by dcc-daemon.\n"
            "import sys\n"
            f"sys.path.insert(0, {str(payload_root / 'python')!r})\n"
            "try:\n"
            "    import dcc_daemon_houdini\n"
            "    dcc_daemon_houdini.start()\n"
            "except Exception as exc:\n"
            "    print('[dcc-daemon] startup failed:', exc)\n"
        ).encode("utf-8")
        files[payload_root / "scripts" / "123.py"] = startup
        files[payload_root / "scripts" / "456.py"] = startup
        package = {
            "recommends": f"houdini_version >= '{target.version}'",
            "env": [{"DCC_DAEMON_ENABLED": "1"}],
            "path": str(payload_root).replace("\\", "/"),
        }
        files[package_file] = json.dumps(package, indent=2).encode("utf-8") + b"\n"
        result = self._write_files(files, target)
        result["next_steps"] = ["Restart Houdini and check Overview for registration."]
        return result
