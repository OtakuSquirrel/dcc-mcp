"""Safe local installer tests using isolated fake DCC preferences."""

from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from dcc_daemon.installers.base import InstallerError
from dcc_daemon.installers.service import InstallerService


def _fake_repo(root: Path) -> Path:
    for kind in ("blender", "houdini", "maya"):
        adapter = root / "plugins" / f"{kind}_daemon" / "__init__.py"
        adapter.parent.mkdir(parents=True, exist_ok=True)
        adapter.write_text(f"KIND = {kind!r}\n", encoding="utf-8")
    connector = root / "plugins" / "common" / "dcc_socket_server.py"
    connector.parent.mkdir(parents=True, exist_ok=True)
    connector.write_text("CONNECTOR = True\n", encoding="utf-8")
    return root


def test_scan_detects_houdini_and_maya_user_preferences(tmp_path: Path):
    home = tmp_path / "home"
    (home / "Documents" / "houdini20.5").mkdir(parents=True)
    (home / "Documents" / "maya" / "2026").mkdir(parents=True)
    service = InstallerService(home=home, repo_root=_fake_repo(tmp_path / "repo"))

    scan = service.scan()
    installers = {item["kind"]: item for item in scan["installers"]}
    assert installers["houdini"]["targets"][0]["id"] == "houdini-20.5"
    assert installers["maya"]["targets"][0]["id"] == "maya-2026"
    assert installers["blender"]["available"] is True
    assert installers["ue"]["available"] is False


def test_blender_user_addon_install(tmp_path: Path):
    home = tmp_path / "home"
    system = platform.system()
    if system == "Windows":
        root = home / "AppData" / "Roaming" / "Blender Foundation" / "Blender" / "5.1"
    elif system == "Darwin":
        root = home / "Library" / "Application Support" / "Blender" / "5.1"
    else:
        root = home / ".config" / "blender" / "5.1"
    root.mkdir(parents=True)
    service = InstallerService(home=home, repo_root=_fake_repo(tmp_path / "repo"))

    plan = service.create_plan("blender", "blender-5.1")
    result = service.apply_plan("blender", plan["id"], plan["token"])
    addon = root / "scripts" / "addons" / "dcc_daemon_blender"
    assert result["ok"]
    assert (addon / "__init__.py").is_file()
    assert result["next_steps"][1].endswith("DCC Daemon Bridge.")

    (addon / "__init__.py").write_text("user changed this\n", encoding="utf-8")
    uninstall = service.create_plan("blender", "blender-5.1", "uninstall")
    result = service.apply_plan("blender", uninstall["id"], uninstall["token"])
    assert result["ok"] is False
    assert result["status"] == "needs_attention"
    assert (addon / "__init__.py").read_text(encoding="utf-8") == "user changed this\n"
    assert Path(result["manifest"]).is_file()


def test_houdini_install_verify_and_uninstall(tmp_path: Path):
    home = tmp_path / "home"
    preference_root = home / "Documents" / "houdini20.5"
    preference_root.mkdir(parents=True)
    service = InstallerService(home=home, repo_root=_fake_repo(tmp_path / "repo"))

    plan = service.create_plan("houdini", "houdini-20.5")
    result = service.apply_plan("houdini", plan["id"], plan["token"])
    assert result["ok"]

    package_file = preference_root / "packages" / "dcc_daemon.json"
    package = json.loads(package_file.read_text(encoding="utf-8"))
    assert package["path"].endswith("/.dcc-mcp/plugins/houdini/20.5")
    assert service.verify("houdini", "houdini-20.5")["status"] == "installed"

    with pytest.raises(InstallerError, match="already used"):
        service.apply_plan("houdini", plan["id"], plan["token"])

    # Reinstall/repair keeps the original pre-install snapshot for uninstall.
    repair = service.create_plan("houdini", "houdini-20.5")
    service.apply_plan("houdini", repair["id"], repair["token"])

    uninstall = service.create_plan("houdini", "houdini-20.5", "uninstall")
    result = service.apply_plan("houdini", uninstall["id"], uninstall["token"])
    assert result["ok"]
    assert not package_file.exists()
    assert service.verify("houdini", "houdini-20.5")["status"] == "not_installed"


def test_maya_install_restores_existing_module_on_uninstall(tmp_path: Path):
    home = tmp_path / "home"
    preference_root = home / "Documents" / "maya" / "2026"
    module_file = preference_root / "modules" / "dcc_daemon.mod"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("previous module\n", encoding="utf-8")
    service = InstallerService(home=home, repo_root=_fake_repo(tmp_path / "repo"))

    plan = service.create_plan("maya", "maya-2026")
    service.apply_plan("maya", plan["id"], plan["token"])
    assert "+ dcc_daemon 0.1.0" in module_file.read_text(encoding="utf-8")
    assert service.verify("maya", "maya-2026")["ok"]

    uninstall = service.create_plan("maya", "maya-2026", "uninstall")
    service.apply_plan("maya", uninstall["id"], uninstall["token"])
    assert module_file.read_text(encoding="utf-8") == "previous module\n"
