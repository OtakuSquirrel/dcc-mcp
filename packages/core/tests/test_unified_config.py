"""Tests for the read-only Python view of ``~/.dcc-mcp/config.toml``."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from dcc_mcp_core import unified_config


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` so each test gets an empty config dir."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    importlib.reload(unified_config)
    return tmp_path


def _write(home: Path, body: str) -> Path:
    p = home / ".dcc-mcp" / "config.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_defaults_when_file_missing(fake_home: Path) -> None:
    assert not unified_config.exists()
    p = unified_config.port_range()
    assert p.min == unified_config.DEFAULT_PORT_MIN
    assert p.max == unified_config.DEFAULT_PORT_MAX
    assert unified_config.disabled_tools("blender") == []
    assert unified_config.has_disabled_tools_section("blender") is False


def test_reads_explicit_ports(fake_home: Path) -> None:
    _write(fake_home, "[ports]\nmin = 20000\nmax = 20100\n")
    p = unified_config.port_range()
    assert p == (20000, 20100)


def test_reads_disabled_tools_per_mcp(fake_home: Path) -> None:
    _write(
        fake_home,
        '[tools.blender]\ndisabled = ["execute_blender_code", "render_frame"]\n'
        "[tools.os]\ndisabled = []\n",
    )
    assert unified_config.disabled_tools("blender") == [
        "execute_blender_code",
        "render_frame",
    ]
    # Empty list still counts as "section present" — authoritative.
    assert unified_config.has_disabled_tools_section("os") is True
    assert unified_config.disabled_tools("os") == []
    # Server with no section returns nothing AND reports absent.
    assert unified_config.has_disabled_tools_section("houdini") is False
    assert unified_config.disabled_tools("houdini") == []


def test_malformed_toml_falls_back_silently(fake_home: Path, caplog) -> None:
    _write(fake_home, "this is not = valid [toml")
    p = unified_config.port_range()
    # Defaults — and we should have logged a warning.
    assert p == (unified_config.DEFAULT_PORT_MIN, unified_config.DEFAULT_PORT_MAX)
    assert any("Failed to read" in r.message for r in caplog.records)


def test_garbage_disabled_value_returns_empty(fake_home: Path) -> None:
    _write(fake_home, '[tools.blender]\ndisabled = "not a list"\n')
    assert unified_config.disabled_tools("blender") == []
    # Section is still present — caller can choose to treat that as
    # "user explicitly cleared the list".
    assert unified_config.has_disabled_tools_section("blender") is True


def test_garbage_port_values_return_defaults(fake_home: Path) -> None:
    _write(fake_home, '[ports]\nmin = "abc"\nmax = "xyz"\n')
    p = unified_config.port_range()
    assert p.min == unified_config.DEFAULT_PORT_MIN
    assert p.max == unified_config.DEFAULT_PORT_MAX


def test_empty_file_yields_defaults(fake_home: Path) -> None:
    _write(fake_home, "")
    p = unified_config.port_range()
    assert p.min == unified_config.DEFAULT_PORT_MIN
