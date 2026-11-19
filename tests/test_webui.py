"""WebUI smoke tests — routes register and respond via Starlette TestClient.

Uses the MCP app built by ``build_app`` (WebUI attached via custom_route)
and Starlette's TestClient, so no real network port is bound. Verifies
the dashboard HTML and the two JSON endpoints without needing a live DCC.
"""

from __future__ import annotations

import json
import logging
import tomllib

from starlette.testclient import TestClient

from dcc_mcp.app import build_app


def _client() -> TestClient:
    # TestClient drives the app's lifespan via context-manager use.
    return TestClient(build_app(webui=True))


def test_dashboard_html():
    with _client() as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "<title>dcc-mcp</title>" in r.text
        assert "setInterval" not in r.text
        assert 'data-tab="logs"' in r.text
        assert 'data-tab="tools"' in r.text
        assert 'data-tab="install"' in r.text
        assert 'data-tab="integrations">API/MCP接入</button>' in r.text
        assert 'data-tab="diagnostics"' in r.text
        assert "Rescan this computer" in r.text
        assert "Uninstall" in r.text
        assert "target-path" in r.text
        assert "installer-note" in r.text
        assert "Add project" in r.text
        assert "/api/installers/${encodeURIComponent(kind)}/projects" in r.text
        assert "function addProject(kind)" in r.text


def test_integration_examples_follow_live_endpoint():
    # A non-default port and MCP path must propagate into every copied example.
    app = build_app(mcp_path="/agent/mcp", webui=True)
    with TestClient(app, base_url="http://127.0.0.1:19876") as client:
        html = client.get("/").text
        data = json.loads(html.split("const INTEGRATIONS = ", 1)[1].split(";\n", 1)[0])
        endpoint = "http://127.0.0.1:19876/agent/mcp"
        assert data["endpoint"] == endpoint
        assert {item["id"] for item in data["clients"]} == {
            "claude-code", "codex", "cursor", "vscode", "codebuddy"
        }
        for item in data["clients"]:
            if item["language"] == "TOML":
                config = tomllib.loads(item["code"])
                server = config["mcp_servers"]["dcc"]
            else:
                config = json.loads(item["code"])
                root = "servers" if item["id"] == "vscode" else "mcpServers"
                server = config[root]["dcc"]
            assert server["url"] == endpoint
        assert endpoint in data["api"][0]["code"]
        assert "http://127.0.0.1:19876/api/instances" in data["api"][1]["code"]
        assert "__INTEGRATION_DATA__" not in html


def test_api_instances_is_list():
    with _client() as client:
        r = client.get("/api/instances")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_api_tools_catalog():
    with _client() as client:
        r = client.get("/api/tools")
        assert r.status_code == 200
        tools = r.json()["tools"]
        by_name = {t["name"]: t for t in tools}
        assert set(by_name) == {"list_instances", "execute_python", "health", "screenshot"}
        # list_instances is daemon-wide; the rest address a specific instance.
        assert by_name["list_instances"]["targets_instance"] is False
        assert by_name["execute_python"]["targets_instance"] is True
        exec_tool = by_name["execute_python"]
        assert exec_tool["summary"]
        assert {p["name"] for p in exec_tool["parameters"]} == {"instance_id", "code"}
        assert "instance_id" in exec_tool["signature"]


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
  "blender", "houdini", "ue", "maya", "tuanjie"
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
