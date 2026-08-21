"""Tuanjie (团结引擎) Editor connector installer (project-scoped package).

Tuanjie is Unity's Chinese fork, and like Unity it scripts in C#, not an
embedded CPython — so it cannot vendor the shared ``dcc_socket_server.py``
like Blender/Houdini/Maya/UE. Instead it installs a small **embedded UPM
package** holding the C# connector from ``plugins/tuanjie_daemon/`` into a
specific project's ``Packages/`` folder. The connector's
``[InitializeOnLoad]`` starts it whenever the Editor loads, so there is
nothing to enable by hand (unlike Blender's add-on toggle).

Like Unreal projects, Tuanjie targets are **project-scoped**: the user points
the installer at a Tuanjie project directory; each is remembered via its
manifest. Detection requires ``m_TuanjieEditorVersion`` in
``ProjectSettings/ProjectVersion.txt`` — the marker a stock Unity project does
NOT have, so the two engines can coexist without misidentifying each other.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dcc_mcp.installers.base import BaseInstaller, Change, InstallerError, Target

_PACKAGE_DIR = "com.dcc-mcp.tuanjie"
_PLUGIN_DIR = "tuanjie_daemon"


class TuanjieInstaller(BaseInstaller):
    kind = "tuanjie"
    title = "Tuanjie 团结引擎"
    strategy = "Embedded Editor package (per project)"
    note = (
        "Tuanjie scripts in C#, not Python: code sent through execute_python is "
        "compiled and run as C# by the connector. Point this at a Tuanjie "
        "project folder; the package auto-starts when that project's Editor loads."
    )
    accepts_project_path = True

    def __init__(self, home: Path, repo_root: Path) -> None:
        super().__init__(home, repo_root)
        self._projects: dict[str, Target] = {}
        self._project_roots: dict[str, Path] = {}
        self._load_managed_projects()

    @staticmethod
    def _project_version(project_root: Path) -> str:
        version_file = project_root / "ProjectSettings" / "ProjectVersion.txt"
        try:
            for line in version_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("m_EditorVersion:"):
                    return line.split(":", 1)[1].strip() or "unknown"
        except (OSError, ValueError):
            pass
        return "unknown"

    @staticmethod
    def _is_tuanjie_project(path: Path) -> bool:
        """A Tuanjie project, not merely a Unity one.

        ``m_TuanjieEditorVersion`` is written only by Tuanjie, so requiring it
        keeps a stock Unity project from being adopted by this installer (its
        C# connector targets the Tuanjie Editor's assemblies).
        """
        version_file = path / "ProjectSettings" / "ProjectVersion.txt"
        if not version_file.is_file() or not (path / "Assets").is_dir():
            return False
        try:
            content = version_file.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return False
        return "m_TuanjieEditorVersion" in content

    def _load_managed_projects(self) -> None:
        manifests = self.state_root / "installations"
        if not manifests.is_dir():
            return
        for manifest_path in manifests.glob("tuanjie-tuanjie-project-*.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                target = Target(**manifest["target"])
                project_root = Path(target.install_root)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if target.kind != self.kind or not self._is_tuanjie_project(project_root):
                continue
            self._projects[target.id] = target
            self._project_roots[target.id] = project_root.resolve()

    def add_project(self, value: str) -> Target:
        raw = value.strip().strip('"')
        if not raw:
            raise InstallerError("enter a Tuanjie project directory")
        path = Path(raw).expanduser()
        if path.is_file():
            path = path.parent
        path = path.resolve()
        if not self._is_tuanjie_project(path):
            raise InstallerError(
                "not a Tuanjie project: expected Assets/ and a "
                "ProjectSettings/ProjectVersion.txt containing m_TuanjieEditorVersion"
            )
        digest = hashlib.sha256(str(path).casefold().encode("utf-8")).hexdigest()[:12]
        target = Target(
            id=f"tuanjie-project-{digest}",
            kind=self.kind,
            version=self._project_version(path),
            label=f"Project {path.name}",
            install_root=str(path),
            detected_from="user_selected",
            scope="project",
        )
        self._projects[target.id] = target
        self._project_roots[target.id] = path
        return target

    def detect(self) -> list[Target]:
        projects = (
            target
            for target_id, target in self._projects.items()
            if self._is_tuanjie_project(self._project_roots[target_id])
        )
        return sorted(projects, key=lambda item: item.label.lower())

    def _package_root(self, target: Target) -> Path:
        known = next((item for item in self.detect() if item.id == target.id), None)
        if known != target:
            raise InstallerError("Tuanjie project is no longer available")
        project_root = Path(target.install_root).resolve()
        return project_root / "Packages" / _PACKAGE_DIR

    def changes(self, target: Target) -> list[Change]:
        package_root = self._package_root(target)
        files = self.copy_payload_tree(_PLUGIN_DIR, package_root)
        return [
            Change("write", str(path), "Install Tuanjie Editor connector")
            for path in sorted(files)
        ]

    def install(self, target: Target) -> dict:
        package_root = self._package_root(target)
        files = self.copy_payload_tree(_PLUGIN_DIR, package_root)
        result = self._write_files(files, target)
        result["next_steps"] = [
            "Open (or refocus) this Tuanjie project so the Editor imports the package.",
            "The connector auto-starts on load; check Overview for registration.",
        ]
        return result

    def uninstall(self, target: Target) -> dict:
        package_root = self._package_root(target)
        result = super().uninstall(target)
        if result["ok"]:
            for root in (package_root, package_root.parent):
                try:
                    root.rmdir()
                except OSError:
                    pass
        return result
