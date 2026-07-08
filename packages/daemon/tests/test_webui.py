"""WebUI smoke tests — routes register and respond via Starlette TestClient.

Uses the MCP app built by ``build_app`` (WebUI attached via custom_route)
and Starlette's TestClient, so no real network port is bound. Verifies
the dashboard HTML and the two JSON endpoints without needing a live DCC.
"""

from __future__ import annotations

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


def test_api_health_bad_port():
    with _client() as client:
        r = client.get("/api/health/not-a-port")
        # Starlette int-less path param falls through to 404, or our 400.
        assert r.status_code in (400, 404)


def test_api_health_dead_port():
    with _client() as client:
        r = client.get("/api/health/65000")  # nothing listening
        assert r.status_code == 200
        assert r.json()["verdict"] in {"dead", "unknown"}
