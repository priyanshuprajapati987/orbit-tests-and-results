# ORBIT — Phase 3 status blueprint tests (minimal Flask app, no server boot)
#
# Run:  python -m pytest tests/test_status_bp.py -v
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    flask = pytest.importorskip("flask", reason="flask not installed")
    status_mod = pytest.importorskip(
        "orbit.orbit.core.status_bp", reason="status_bp not importable"
    )
    app = flask.Flask(__name__)
    app.register_blueprint(status_mod.status_bp, url_prefix="/api/status")
    app.config["TESTING"] = True
    return app.test_client()


def test_status_orbit_shape(client):
    resp = client.get("/api/status/orbit")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("version", "model", "policy", "runtime", "permissions",
                "recent_diagnostics", "ready_for_chat"):
        assert key in data, f"missing key: {key}"
    for mk in ("default", "ollama_reachable", "default_installed", "installed_count"):
        assert mk in data["model"], f"missing model.{mk}"
    assert "offline_mode" in data["policy"]
    assert "local_first" in data["policy"]


def test_status_ready_flag_is_boolean(client):
    data = client.get("/api/status/orbit").get_json()
    assert isinstance(data["ready_for_chat"], bool)
    # ready only when ollama reachable AND default model installed
    expected = data["model"]["ollama_reachable"] and data["model"]["default_installed"]
    assert data["ready_for_chat"] == expected


def test_status_permissions_pending_is_int(client):
    data = client.get("/api/status/orbit").get_json()
    assert isinstance(data["permissions"]["pending"], int)


def test_status_does_not_leak_api_key(client):
    body = client.get("/api/status/orbit").get_data(as_text=True)
    assert "ORBIT_API_KEY" not in body
    assert "sk-or-v1-" not in body
