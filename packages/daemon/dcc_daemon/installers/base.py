"""Shared types and safe filesystem primitives for DCC installers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "default"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class Target:
    id: str
    kind: str
    version: str
    label: str
    install_root: str
    detected_from: str
    scope: str = "version"


@dataclass(frozen=True)
class Change:
    action: str
    path: str
    description: str


@dataclass
class InstallPlan:
    id: str
    token: str
    kind: str
    target: Target
    changes: list[Change]
    created_at: float
    expires_at: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("metadata", None)
        return result


class InstallerError(RuntimeError):
    """A safe, user-facing installer failure."""


class BaseInstaller:
    kind = ""
    title = ""
    strategy = ""
    note = ""
    accepts_project_path = False

    def __init__(self, home: Path, repo_root: Path) -> None:
        self.home = home.resolve()
        self.repo_root = repo_root.resolve()
        self.state_root = self.home / ".dcc-mcp"

    def detect(self) -> list[Target]:
        raise NotImplementedError

    def changes(self, target: Target) -> list[Change]:
        raise NotImplementedError

    def install(self, target: Target) -> dict[str, Any]:
        raise NotImplementedError

    def manifest_path(self, target: Target) -> Path:
        return self.state_root / "installations" / f"{self.kind}-{safe_id(target.id)}.json"

    def plugin_source(self) -> tuple[Path, Path]:
        payloads = Path(__file__).resolve().parent / "payloads"
        adapter = payloads / f"{self.kind}_daemon" / "__init__.py"
        connector = payloads / "common" / "dcc_socket_server.py"
        if adapter.is_file() and connector.is_file():
            return adapter, connector

        adapter = self.repo_root / "plugins" / f"{self.kind}_daemon" / "__init__.py"
        connector = self.repo_root / "plugins" / "common" / "dcc_socket_server.py"
        if not adapter.is_file() or not connector.is_file():
            raise InstallerError("plugin payload is unavailable in this daemon installation")
        return adapter, connector

    def _snapshot(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {"existed": False}
        data = path.read_bytes()
        return {
            "existed": True,
            "content_base64": base64.b64encode(data).decode("ascii"),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def _write_files(
        self,
        files: dict[Path, bytes],
        target: Target,
        *,
        before_overrides: dict[Path, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        records = []
        before_overrides = before_overrides or {}
        manifest_path = self.manifest_path(target)
        previous: dict[str, dict[str, Any]] = {}
        if manifest_path.is_file():
            try:
                old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                previous = {item["path"]: item for item in old_manifest.get("files", [])}
            except (OSError, ValueError, KeyError) as exc:
                raise InstallerError(f"installation manifest is unreadable: {exc}") from exc
        try:
            for path, data in files.items():
                old_record = previous.get(str(path))
                before = before_overrides.get(path)
                if before is None:
                    before = old_record["before"] if old_record else self._snapshot(path)
                atomic_write(path, data)
                records.append({
                    "path": str(path),
                    "installed_sha256": hashlib.sha256(data).hexdigest(),
                    "before": before,
                })
            manifest = {
                "schema": 1,
                "kind": self.kind,
                "target": asdict(target),
                "files": records,
            }
            atomic_write(
                manifest_path,
                json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
            )
        except Exception:
            for record in reversed(records):
                self._restore_record(record, preserve_modified=True)
            raise
        return {"ok": True, "manifest": str(manifest_path), "files": records}

    def verify(self, target: Target) -> dict[str, Any]:
        manifest_path = self.manifest_path(target)
        if not manifest_path.is_file():
            return {"ok": False, "status": "not_installed", "checks": []}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checks = []
        for record in manifest.get("files", []):
            path = Path(record["path"])
            matches = path.is_file() and file_sha256(path) == record["installed_sha256"]
            checks.append({"path": str(path), "ok": matches})
        return {
            "ok": bool(checks) and all(item["ok"] for item in checks),
            "status": "installed" if checks and all(item["ok"] for item in checks) else "modified",
            "checks": checks,
        }

    def uninstall(self, target: Target) -> dict[str, Any]:
        manifest_path = self.manifest_path(target)
        if not manifest_path.is_file():
            raise InstallerError("installation manifest was not found")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        results = []
        for record in reversed(manifest.get("files", [])):
            results.append(self._restore_record(record, preserve_modified=True))
        preserved = any(item["action"] == "preserved_modified" for item in results)
        if not preserved:
            manifest_path.unlink()
        self._remove_empty_plugin_dirs(results)
        return {
            "ok": not preserved,
            "status": "needs_attention" if preserved else "uninstalled",
            "manifest": str(manifest_path) if preserved else None,
            "files": results,
        }

    def _restore_record(
        self, record: dict[str, Any], *, preserve_modified: bool
    ) -> dict[str, str]:
        path = Path(record["path"])
        if not path.is_file():
            return {"path": str(path), "action": "already_missing"}
        if preserve_modified and file_sha256(path) != record["installed_sha256"]:
            return {"path": str(path), "action": "preserved_modified"}
        before = record.get("before", {})
        if before.get("existed"):
            atomic_write(path, base64.b64decode(before["content_base64"]))
            action = "restored"
        else:
            path.unlink()
            action = "removed"
        return {"path": str(path), "action": action}

    def _remove_empty_plugin_dirs(self, results: list[dict[str, Any]]) -> None:
        roots = {Path(item["path"]).parent for item in results if item["action"] == "removed"}
        for root in sorted(roots, key=lambda item: len(item.parts), reverse=True):
            current = root
            while current != current.parent and self.state_root in current.parents:
                try:
                    current.rmdir()
                except OSError:
                    break
                current = current.parent

    def copy_payload(self, destination: Path) -> dict[Path, bytes]:
        adapter, connector = self.plugin_source()
        return {
            destination / "__init__.py": adapter.read_bytes(),
            destination / "dcc_socket_server.py": connector.read_bytes(),
        }
