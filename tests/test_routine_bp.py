"""Tests for the Daily Routine blueprint (snapshot + chat ping + feedback journal)."""

import json

import pytest


@pytest.fixture()
def client():
    from orbit.orbit.server import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture()
def feedback_file(tmp_path, monkeypatch):
    """Redirect the feedback journal into tmp so tests never touch orbit_data."""
    from orbit.orbit.core import routine_bp

    target = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(routine_bp, "_feedback_file", lambda: target)
    return target


def test_snapshot_shape(client):
    res = client.get("/api/routine/snapshot")
    assert res.status_code == 200
    data = res.get_json()
    for key in ("generated_at", "system", "providers", "safety", "boot", "llm_today"):
        assert key in data
    # every section carries ok/data-or-error (failure isolation)
    for key in ("system", "providers", "safety", "boot", "llm_today"):
        assert "ok" in data[key], f"{key} missing ok flag"


def test_snapshot_system_section(client):
    data = client.get("/api/routine/snapshot").get_json()
    sys_sec = data["system"]
    assert sys_sec["ok"] is True
    assert sys_sec["data"]["version"]
    assert sys_sec["data"]["blueprints"] >= 100


def test_snapshot_providers_section(client):
    data = client.get("/api/routine/snapshot").get_json()
    prov = data["providers"]
    assert prov["ok"] is True
    assert isinstance(prov["data"]["online"], int)
    assert prov["data"]["total"] >= 1


def test_ping_happy_path(client, monkeypatch):
    from orbit.orbit.core.llm import legacy_adapter as la

    monkeypatch.setattr(la, "generate", lambda *a, **k: "ORBIT online")
    res = client.post("/api/routine/ping", json={"message": "hello"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["latency_ms"] >= 0
    assert data["response"] == "ORBIT online"


def test_ping_error_reply_marks_not_ok(client, monkeypatch):
    from orbit.orbit.core.llm import legacy_adapter as la

    monkeypatch.setattr(la, "generate", lambda *a, **k: "[Error: provider down]")
    data = client.post("/api/routine/ping", json={}).get_json()
    assert data["ok"] is False


def test_feedback_requires_note(client, feedback_file):
    res = client.post("/api/routine/feedback", json={"mood": "good"})
    assert res.status_code == 400


def test_feedback_roundtrip(client, feedback_file):
    res = client.post(
        "/api/routine/feedback",
        json={"mood": "good", "note": "voice aaj smooth chala", "tags": ["voice", "ui"]},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    data = client.get("/api/routine/feedback?limit=10").get_json()
    assert data["total"] == 1
    entry = data["feedback"][0]
    assert entry["mood"] == "good"
    assert entry["note"] == "voice aaj smooth chala"
    assert entry["tags"] == ["voice", "ui"]
    assert "ts" in entry

    # persisted on disk too
    assert feedback_file.exists()
    assert json.loads(feedback_file.read_text(encoding="utf-8").strip())["mood"] == "good"


def test_feedback_invalid_mood_normalized(client, feedback_file):
    client.post("/api/routine/feedback", json={"mood": "awesome", "note": "x"})
    entry = client.get("/api/routine/feedback").get_json()["feedback"][0]
    assert entry["mood"] == "ok"


def test_feedback_newest_first_and_limit_clamped(client, feedback_file):
    for i in range(3):
        client.post("/api/routine/feedback", json={"note": f"note {i}"})
    data = client.get("/api/routine/feedback?limit=99999").get_json()
    assert data["total"] <= 100
    assert data["feedback"][0]["note"] == "note 2"  # newest first


def test_feedback_capped_at_500(client, feedback_file):
    from orbit.orbit.core import routine_bp

    with open(feedback_file, "w", encoding="utf-8") as f:
        for i in range(routine_bp._MAX_FEEDBACK + 5):
            f.write(json.dumps({"ts": "t", "mood": "ok", "note": f"old {i}", "tags": []}) + "\n")
    client.post("/api/routine/feedback", json={"note": "newest"})
    lines = [ln for ln in feedback_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == routine_bp._MAX_FEEDBACK
    assert json.loads(lines[-1])["note"] == "newest"


def test_feedback_list_empty(client, feedback_file):
    data = client.get("/api/routine/feedback").get_json()
    assert data == {"feedback": [], "total": 0}
