"""Tests for the ToolGate Flask blueprint (PolicyEngine approval UX)."""

import pytest


@pytest.fixture()
def client():
    from orbit.orbit.server import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_status_shape(client):
    res = client.get("/api/toolgate/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "workspace" in data
    assert "strict" in data
    assert "approved_paths" in data
    assert "approved_actions" in data
    assert "extra_workspaces" in data


def test_audit_empty_or_list(client):
    res = client.get("/api/toolgate/audit?limit=5")
    assert res.status_code == 200
    data = res.get_json()
    assert "audit" in data
    assert isinstance(data["audit"], list)


def test_audit_limit_clamped(client):
    res = client.get("/api/toolgate/audit?limit=99999")
    assert res.status_code == 200
    assert len(res.get_json()["audit"]) <= 500


def test_approve_requires_input(client):
    res = client.post("/api/toolgate/approve", json={})
    assert res.status_code == 400


def test_approve_action_updates_status(client):
    res = client.post("/api/toolgate/approve", json={"action": "file.write"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "file.write" in data["status"]["approved_actions"]


def test_revoke_action(client):
    client.post("/api/toolgate/approve", json={"action": "system.command"})
    res = client.post("/api/toolgate/revoke", json={"action": "system.command"})
    assert res.status_code == 200
    assert "system.command" not in res.get_json()["status"]["approved_actions"]


def test_approve_path(client):
    res = client.post("/api/toolgate/approve", json={"path": "D:/temp/allowed"})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
