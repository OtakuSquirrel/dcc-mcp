"""Unreal Editor user-wide and project plugin installers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
from pathlib import Path

from dcc_mcp.installers.base import BaseInstaller, Change, InstallerError, Target

_START = "# >>> dcc-daemon managed startup >>>"
_END = "# <<< dcc-daemon managed startup <<<"


class UnrealInstaller(BaseInstaller):
    kind = "ue"
    title = "Unreal Engine"
    strategy = "Current-user startup or project plugin"
    note = (
        "Unreal Python runs in the Editor only. The Python Editor Script Plugin "
        "must be enabled for each project before a user-wide startup can run."
    )
    accepts_project_path = True

    def __init__(self, home: Path, repo_root: Path) -> None:
        super().__init__(home, repo_root)
        self._projects: dict[str, Target] = {}
        self._project_files: dict[str, Path] = {}
        self._load_managed_projects()

    def _engine_versions(self) -> list[str]:
        versions: set[str] = set()
        system = platform.system()
        roots: list[Path] = []
        if system == "Windows":
            program_data = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
            manifests = program_data / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
            if manifests.is_dir():
                for item in manifests.glob("*.item"):
                    try:
                        data = json.loads(item.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    app_name = str(data.get("AppName", ""))
                    location = Path(str(data.get("InstallLocation", "")))
                    if app_name.startswith("UE_") and location.is_dir():
                        roots.append(location)
            program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            roots.extend((program_files / "Epic Games").glob("UE_*"))
        elif system == "Darwin":
            roots.extend(Path("/Users/Shared/Epic Games").glob("UE_*"))
        else:
            roots.extend(Path("/opt").glob("UnrealEngine*"))
            roots.extend(self.home.glob("UnrealEngine*"))

        for root in roots:
            match = re.search(r"(?:UE_|UnrealEngine[-_]?)([0-9]+\.[0-9]+)", root.name)
            if root.is_dir() and match:
                versions.add(match.group(1))
        return sorted(versions)

    def detect(self) -> list[Target]:
        targets: list[Target] = []
        versions = self._engine_versions()
        if versions:
            display_versions = ", ".join(versions)
            targets.append(Target(
                id="ue-user",
                kind=self.kind,
                version=display_versions,
                label=f"UE {display_versions} · Current user",
                install_root=str(self.home / "Documents" / "UnrealEngine" / "Python"),
                detected_from="engine_installation",
                scope="user",
            ))
        projects = (
            target for target_id, target in self._projects.items()
            if self._project_files[target_id].is_file()
        )
        targets.extend(sorted(projects, key=lambda item: item.label.lower()))
        return targets

    def _load_managed_projects(self) -> None:
        manifests = self.state_root / "installations"
        if not manifests.is_dir():
            return
        for manifest_path in manifests.glob("ue-ue-project-*.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                target = Target(**manifest["target"])
                project_files = list(Path(target.install_root).glob("*.uproject"))
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if target.kind != self.kind or target.scope != "project" or len(project_files) != 1:
                continue
            self._projects[target.id] = target
            self._project_files[target.id] = project_files[0].resolve()

    def add_project(self, value: str) -> Target:
        raw = value.strip().strip('"')
        if not raw:
            raise InstallerError("enter a .uproject file or project directory")
        path = Path(raw).expanduser()
        if path.is_dir():
            projects = list(path.glob("*.uproject"))
            if len(projects) != 1:
                raise InstallerError("project directory must contain exactly one .uproject file")
            path = projects[0]
        path = path.resolve()
        if path.suffix.lower() != ".uproject" or not path.is_file():
            raise InstallerError("the selected .uproject file does not exist")
        try:
            descriptor = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise InstallerError(f"unable to read the .uproject file: {exc}") from exc
        association = str(descriptor.get("EngineAssociation", "")) or "unknown"
        digest = hashlib.sha256(str(path).casefold().encode("utf-8")).hexdigest()[:12]
        target = Target(
            id=f"ue-project-{digest}",
            kind=self.kind,
            version=association,
            label=f"Project · {path.stem}",
            install_root=str(path.parent),
            detected_from="user_selected",
            scope="project",
        )
        self._projects[target.id] = target
        self._project_files[target.id] = path
        return target

    def _paths(self, target: Target) -> tuple[Path, Path, Path | None]:
        known = next((item for item in self.detect() if item.id == target.id), None)
        if known != target:
            raise InstallerError("Unreal target is no longer available")
        if target.scope == "user":
            python_root = Path(target.install_root).resolve()
            expected = (self.home / "Documents" / "UnrealEngine" / "Python").resolve()
            if python_root != expected:
                raise InstallerError("invalid Unreal user Python directory")
            return python_root, python_root / "dcc_daemon_ue", None
        if target.scope == "project":
            project_root = Path(target.install_root).resolve()
            descriptor = self._project_files.get(target.id)
            if (
                descriptor is None
                or not descriptor.is_file()
                or descriptor.parent != project_root
            ):
                raise InstallerError("the Unreal project is no longer available")
            plugin_root = project_root / "Plugins" / "DCCDaemon"
            python_root = plugin_root / "Content" / "Python"
            return python_root, python_root / "dcc_daemon_ue", plugin_root / "DCCDaemon.uplugin"
        raise InstallerError(f"unsupported Unreal installation scope: {target.scope}")

    def changes(self, target: Target) -> list[Change]:
        python_root, module_root, plugin_descriptor = self._paths(target)
        changes = [
            Change("write", str(module_root / "__init__.py"), "Install Unreal adapter"),
            Change("write", str(module_root / "dcc_socket_server.py"), "Install shared connector"),
            Change("update", str(python_root / "init_unreal.py"), "Start connector when the Unreal Editor Python environment loads"),
        ]
        if plugin_descriptor is not None:
            changes.insert(0, Change(
                "write", str(plugin_descriptor),
                "Register the project plugin and its PythonScriptPlugin dependency",
            ))
        return changes

    def install(self, target: Target) -> dict:
        python_root, module_root, plugin_descriptor = self._paths(target)
        files = self.copy_payload(module_root)
        startup = self._startup_block()
        init_file = python_root / "init_unreal.py"
        before_overrides = {}
        if target.scope == "user" and init_file.is_file():
            try:
                existing = init_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise InstallerError(f"existing init_unreal.py is unreadable: {exc}") from exc
            clean_startup = self._strip_startup(existing)
            startup = self._merge_startup(clean_startup)
            prior = self._manifest_before_text(target, init_file)
            if prior is not None and clean_startup.rstrip() != prior.rstrip():
                clean_startup = clean_startup.rstrip()
                clean_data = (clean_startup + "\n").encode("utf-8")
                before_overrides[init_file] = {
                    "existed": True,
                    "content_base64": base64.b64encode(clean_data).decode("ascii"),
                    "sha256": hashlib.sha256(clean_data).hexdigest(),
                }
            elif prior is not None and not clean_startup and prior:
                before_overrides[init_file] = {"existed": False}
        files[init_file] = startup.encode("utf-8")
        if plugin_descriptor is not None:
            descriptor = {
                "FileVersion": 3,
                "Version": 1,
                "VersionName": "0.1.0",
                "FriendlyName": "DCC Daemon Bridge",
                "Description": "Connects Unreal Editor Python to the local dcc-daemon.",
                "Category": "Scripting",
                "CreatedBy": "dcc-mcp",
                "EnabledByDefault": True,
                "CanContainContent": True,
                "IsBetaVersion": True,
                "Installed": False,
                "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True}],
            }
            files[plugin_descriptor] = (
                json.dumps(descriptor, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
            )
        result = self._write_files(files, target, before_overrides=before_overrides)
        if target.scope == "user":
            result["next_steps"] = [
                "For each project, enable Edit > Plugins > Scripting > Python Editor Script Plugin.",
                "Restart Unreal Editor and check Overview for registration.",
            ]
        else:
            result["next_steps"] = [
                "Restart this Unreal project; accept enabling Python Editor Script Plugin if prompted.",
                "Check Overview for registration.",
            ]
        return result

    def uninstall(self, target: Target) -> dict:
        python_root, module_root, plugin_descriptor = self._paths(target)
        result = super().uninstall(target)
        if result["ok"]:
            roots = [module_root]
            if plugin_descriptor is not None:
                roots.extend([python_root, python_root.parent, python_root.parent.parent])
            for root in roots:
                try:
                    root.rmdir()
                except OSError:
                    pass
        return result

    @staticmethod
    def _startup_block() -> str:
        return (
            f"{_START}\n"
            "try:\n"
            "    import dcc_daemon_ue\n"
            "    dcc_daemon_ue.start()\n"
            "except Exception as exc:\n"
            "    print('[dcc-daemon] Unreal startup failed:', exc)\n"
            f"{_END}\n"
        )

    @staticmethod
    def _strip_startup(existing: str) -> str:
        before, marker, remainder = existing.partition(_START)
        if marker:
            _managed, end, after = remainder.partition(_END)
            if not end:
                raise InstallerError("existing init_unreal.py has an incomplete dcc-daemon block")
            return before + after.lstrip("\r\n")
        return existing

    def _merge_startup(self, existing: str) -> str:
        prefix = existing.rstrip()
        return (prefix + "\n\n" if prefix else "") + self._startup_block()

    def _manifest_before_text(self, target: Target, init_file: Path) -> str | None:
        manifest_path = self.manifest_path(target)
        if not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            record = next(
                item for item in manifest.get("files", [])
                if item.get("path") == str(init_file)
            )
            before = record["before"]
            if not before.get("existed"):
                return ""
            return base64.b64decode(before["content_base64"]).decode("utf-8")
        except (OSError, ValueError, KeyError, StopIteration, UnicodeDecodeError) as exc:
            raise InstallerError(f"installation manifest is unreadable: {exc}") from exc
