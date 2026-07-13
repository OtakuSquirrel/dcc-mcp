"""Installer orchestration used by the local WebUI API."""

from __future__ import annotations

import platform
import secrets
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from dcc_daemon.installers.base import (
    BaseInstaller,
    Change,
    InstallPlan,
    InstallerError,
    Target,
)
from dcc_daemon.installers.blender import BlenderInstaller
from dcc_daemon.installers.houdini import HoudiniInstaller
from dcc_daemon.installers.maya import MayaInstaller


class InstallerService:
    """Discover DCCs and guard every filesystem mutation with a short-lived plan."""

    plan_ttl_seconds = 300

    def __init__(self, *, home: Path | None = None, repo_root: Path | None = None) -> None:
        home = (home or Path.home()).resolve()
        repo_root = (repo_root or Path(__file__).resolve().parents[4]).resolve()
        self.installers: dict[str, BaseInstaller] = {
            "blender": BlenderInstaller(home, repo_root),
            "houdini": HoudiniInstaller(home, repo_root),
            "maya": MayaInstaller(home, repo_root),
        }
        self._plans: dict[str, InstallPlan] = {}
        self._lock = threading.Lock()

    def scan(self) -> dict:
        supported = []
        for kind in ("blender", "houdini", "maya", "ue"):
            installer = self.installers.get(kind)
            if installer is None:
                supported.append({
                    "kind": kind,
                    "available": False,
                    "strategy": "installer coming next",
                    "targets": [],
                })
                continue
            targets = installer.detect()
            supported.append({
                "kind": kind,
                "title": installer.title,
                "available": True,
                "strategy": installer.strategy,
                "targets": [asdict(target) for target in targets],
            })
        return {
            "platform": {
                "system": platform.system().lower(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
            "installers": supported,
        }

    def _target(self, kind: str, target_id: str) -> tuple[BaseInstaller, Target]:
        installer = self.installers.get(kind)
        if installer is None:
            raise InstallerError(f"automatic installation is not available for {kind}")
        target = next((item for item in installer.detect() if item.id == target_id), None)
        if target is None:
            raise InstallerError("the selected DCC installation is no longer detected")
        return installer, target

    def create_plan(self, kind: str, target_id: str, action: str = "install") -> dict:
        if action not in {"install", "uninstall"}:
            raise InstallerError(f"unsupported installer action: {action}")
        installer, target = self._target(kind, target_id)
        if action == "install":
            changes = installer.changes(target)
        else:
            manifest = installer.manifest_path(target)
            if not manifest.is_file():
                raise InstallerError("installation manifest was not found")
            changes = [Change("restore_or_remove", str(manifest), "Uninstall files recorded in the manifest")]
        now = time.time()
        plan = InstallPlan(
            id=str(uuid.uuid4()),
            token=secrets.token_urlsafe(24),
            kind=kind,
            target=target,
            changes=changes,
            created_at=now,
            expires_at=now + self.plan_ttl_seconds,
            metadata={"action": action},
        )
        with self._lock:
            self._discard_expired(now)
            self._plans[plan.id] = plan
        result = plan.public_dict()
        result["action"] = action
        return result

    def apply_plan(self, kind: str, plan_id: str, token: str) -> dict:
        with self._lock:
            plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise InstallerError("installation plan was not found or was already used")
        if plan.expires_at < time.time():
            raise InstallerError("installation plan has expired; preview it again")
        if not secrets.compare_digest(plan.token, token):
            raise InstallerError("installation confirmation token is invalid")
        if plan.kind != kind:
            raise InstallerError("installation plan does not match this DCC")
        installer, current_target = self._target(plan.kind, plan.target.id)
        if current_target != plan.target:
            raise InstallerError("the detected DCC installation changed; preview it again")
        action = plan.metadata["action"]
        result = (
            installer.install(current_target)
            if action == "install"
            else installer.uninstall(current_target)
        )
        result.update({"action": action, "kind": plan.kind, "target_id": plan.target.id})
        return result

    def verify(self, kind: str, target_id: str) -> dict:
        installer, target = self._target(kind, target_id)
        result = installer.verify(target)
        result.update({"kind": kind, "target_id": target_id})
        return result

    def _discard_expired(self, now: float) -> None:
        expired = [plan_id for plan_id, plan in self._plans.items() if plan.expires_at < now]
        for plan_id in expired:
            self._plans.pop(plan_id, None)
