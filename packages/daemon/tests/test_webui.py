"""WebUI smoke tests — routes register and respond via Starlette TestClient.

Uses the MCP app built by ``build_app`` (WebUI attached via custom_route)
and Starlette's TestClient, so no real network port is bound. Verifies
the dashboard HTML and the two JSON endpoints without needing a live DCC.
"""

from __future__ import annotations

import logging

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
        assert "Rescan this computer" in r.text
        assert "Uninstall" in r.text
        assert "target-path" in r.text
        assert "installer-note" in r.text
        assert "Add project" in r.text
        assert "/api/installers/ue/projects" in r.text


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


def test_api_installer_scan():
    with _client() as client:
        r = client.post("/api/installers/scan")
        assert r.status_code == 200
        data = r.json()
        assert data["platform"]["system"]
        assert {item["kind"] for item in data["installers"]} == {
            "blender", "houdini", "ue", "maya"
        }
        assert next(item for item in data["installers"] if item["kind"] == "maya")["available"]


def test_api_installer_plan_rejects_cross_origin():
    with _client() as client:
        r = client.post(
            "/api/installers/maya/plan",
            headers={"Origin": "https://example.com"},
            json={"target_id": "maya-2026"},
        )
        assert r.status_code == 403


def test_api_unreal_project_rejects_missing_path():
    with _client() as client:
        r = client.post("/api/installers/ue/projects", json={"path": "Z:/missing/project.uproject"})
        assert r.status_code == 400
        assert ".uproject file does not exist" in r.json()["error"]


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
