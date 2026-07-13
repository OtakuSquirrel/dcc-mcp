"""WebUI smoke tests — routes register and respond via Starlette TestClient.

Uses the MCP app built by ``build_app`` (WebUI attached via custom_route)
and Starlette's TestClient, so no real network port is bound. Verifies
the dashboard HTML and the two JSON endpoints without needing a live DCC.
"""

from __future__ import annotations

import io
import logging
import zipfile

from starlette.testclient import TestClient

from dcc_daemon.app import build_app


def _client() -> TestClient:
    # TestClient drives the app's lifespan via context-manager use.
    return TestClient(build_app(webui=True))


def test_dashboard_html():
    with _client() as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "<title>dcc-daemon</title>" in r.text
        assert "setInterval" not in r.text
        assert 'data-tab="logs"' in r.text
        assert 'data-tab="install"' in r.text
        assert 'data-tab="diagnostics"' in r.text


def test_api_instances_is_list():
    with _client() as client:
        r = client.get("/api/instances")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_api_instances_refresh_param():
    with _client() as client:
        r = client.get("/api/instances?refresh=1")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_api_health_unknown_instance():
    with _client() as client:
        r = client.get("/api/health/nope-9")
        # Unknown instance is a valid query → 200 with verdict "dead".
        assert r.status_code == 200
        assert r.json()["verdict"] == "dead"


def test_api_health_dead_instance():
    with _client() as client:
        r = client.get("/api/health/blender-999")  # nothing registered
        assert r.status_code == 200
        assert r.json()["verdict"] == "dead"


def test_api_logs_capture_filter_and_clear():
    with _client() as client:
        logging.getLogger("dcc_daemon.test").warning("webui-log-marker")
        r = client.get("/api/logs?level=WARNING&search=log-marker")
        assert r.status_code == 200
        assert any(item["message"] == "webui-log-marker" for item in r.json())

        r = client.delete("/api/logs")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert client.get("/api/logs?search=log-marker").json() == []


def test_api_install_guides():
    with _client() as client:
        r = client.get("/api/install")
        assert r.status_code == 200
        guides = r.json()
        assert {guide["kind"] for guide in guides} == {"blender", "houdini", "ue", "maya"}
        assert all(guide["register_address"].endswith(":18813") for guide in guides)


def test_api_plugin_package():
    with _client() as client:
        r = client.get("/api/install/blender/package")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
            assert set(archive.namelist()) == {
                "dcc_daemon_blender/__init__.py",
                "dcc_daemon_blender/dcc_socket_server.py",
            }


def test_api_plugin_package_unknown_kind():
    with _client() as client:
        r = client.get("/api/install/nope/package")
        assert r.status_code == 404


def test_api_diagnostics():
    with _client() as client:
        r = client.get("/api/diagnostics")
        assert r.status_code == 200
        data = r.json()
        assert data["services"]["mcp"]["address"].endswith(":18812/mcp")
        assert data["services"]["registration"]["address"].endswith(":18813")
        assert data["mcp_tools"] == [
            "list_instances", "execute_python", "health", "screenshot"
        ]
