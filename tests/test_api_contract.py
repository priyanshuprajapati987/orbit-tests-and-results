# ORBIT — Phase 1 API Contract Smoke Tests (env-gated)
#
# Full create_app() boots the complete blueprint graph; that is heavy and may
# pull optional deps/services, so these tests only run when explicitly enabled:
#
#   ORBIT_SMOKE_SERVER=1 python -m pytest tests/test_api_contract.py -v
#
# Run these on the primary dev machine (jarves venv) before each release.
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_SERVER_ON = os.getenv("ORBIT_SMOKE_SERVER", "").lower() in ("1", "true", "yes", "on")


@pytest.fixture(scope="module")
def client():
    if not _SERVER_ON:
        pytest.skip("set ORBIT_SMOKE_SERVER=1 to run server contract tests")
    pytest.importorskip("flask", reason="flask not installed")
    server = pytest.importorskip("orbit.orbit.server", reason="server not importable")
    create = getattr(server, "create_app", None)
    if create is None:
        pytest.fail("create_app factory missing from orbit.orbit.server")
    try:
        app = create()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"create_app() failed: {exc}")
    app.config["TESTING"] = True
    return app.test_client()


def test_health_route_public(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"health broke: {resp.status_code} {resp.get_data(as_text=True)[:120]}"


def test_security_headers_present(client):
    resp = client.get("/api/health")
    assert "X-Response-Time-Ms" in resp.headers, "timing header missing (after_request lost?)"


def test_protected_route_requires_auth(client):
    resp = client.get("/api/memory/stats")
    assert resp.status_code in (401, 503), (
        f"protected route allowed unauthenticated access: {resp.status_code}"
    )


def test_wrong_api_key_rejected(client):
    resp = client.get("/api/memory/stats", headers={"X-API-Key": "definitely-wrong-key"})
    assert resp.status_code in (401, 503), f"wrong key accepted: {resp.status_code}"


def test_agents_status_contract(client):
    resp = client.get("/api/agents/status")
    # auth-gated deployments answer 401/503 without key; open dev answers 200
    if resp.status_code == 200:
        data = resp.get_json()
        assert data is not None, "agents/status not JSON"
    else:
        assert resp.status_code in (401, 503)


def test_options_preflight_allowed(client):
    resp = client.open("/api/chat", method="OPTIONS")
    assert resp.status_code < 500, "CORS preflight crashed"
