"""Dead Hand — server-side authorization matrix tests (P1).

Verifies the before_request enforcement:
  * flagged identity -> 403 on every /api/* (except local /api/deadhand/*)
  * restricted/lockout profile -> mutating methods 403 (except recovery + health)
  * fail-open: broken dead-hand never bricks the app
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orbit.orbit.core.dead_hand import DeadHand, reset_dead_hand_for_tests
from orbit.orbit.core import dead_hand as dh_mod


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("ORBIT_DEADHAND", raising=False)
    monkeypatch.delenv("ORBIT_DEADHAND_RESPONSE", raising=False)
    monkeypatch.setattr(dh_mod, "is_frozen", lambda: False, raising=False)
    reset_dead_hand_for_tests(None)
    yield
    reset_dead_hand_for_tests(None)


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Flask app with a hermetic DeadHand engine injected."""
    engine = DeadHand(
        store_dir=tmp_path / "sec",
        code_root=tmp_path / "app",
        armed=True,
        exit_on_trigger=False,
        profile="audit",
    )
    monkeypatch.setattr(dh_mod, "_instance", engine, raising=False)
    from orbit.orbit.server import create_app
    application = create_app()
    return application, engine


class TestFlaggedEnforcement:
    def test_flagged_identity_gets_403(self, app):
        application, engine = app
        engine._flag(["ip:127.0.0.1"], reason="test")
        client = application.test_client()
        resp = client.get("/api/deadhand/status")
        # status is exempt (recovery path) — flagged caller still reaches it
        assert resp.status_code == 200
        # a non-recovery API gets 403
        resp = client.get("/api/providers/status")
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "access_revoked"

    def test_unflagged_passes(self, app):
        application, engine = app
        client = application.test_client()
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_flagged_local_recovery_path_still_open(self, app):
        application, engine = app
        engine._flag(["ip:127.0.0.1"], reason="test")
        client = application.test_client()
        resp = client.get("/api/deadhand/status")
        assert resp.status_code == 200  # recovery path exempt

    def test_flagged_expires_after_ttl(self, app):
        application, engine = app
        engine._flag(["ip:9.9.9.9"], reason="remote")
        # simulate expiry
        from datetime import datetime, timedelta, timezone
        flag_file = Path(engine._store_dir) / "deadhand_flagged.json"
        data = json.loads(flag_file.read_text(encoding="utf-8"))
        data["entries"]["ip:9.9.9.9"]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat() + "Z"
        flag_file.write_text(json.dumps(data), encoding="utf-8")
        engine._flag_cache = None
        assert engine.has_flagged() is False


class TestRestrictedMode:
    def test_restricted_blocks_mutating_methods(self, app):
        application, engine = app
        engine._state["profile_override"] = None
        engine._profile_override = "restricted"
        # risk 3 -> restricted
        engine.record_attempt("integrity", "modified")
        client = application.test_client()
        resp = client.post("/api/billing/checkout", json={})
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "restricted_mode"

    def test_restricted_allows_get(self, app):
        application, engine = app
        engine._profile_override = "restricted"
        engine.record_attempt("integrity", "modified")
        client = application.test_client()
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_restricted_allows_deadhand_recovery_posts(self, app):
        application, engine = app
        engine._profile_override = "restricted"
        engine.record_attempt("integrity", "modified")
        client = application.test_client()
        resp = client.post("/api/deadhand/reset", json={"reason": "recover"})
        # recovery path exempt from restricted block
        assert resp.status_code != 403 or resp.get_json().get("error") != "restricted_mode"

    def test_audit_profile_never_restricts(self, app):
        application, engine = app
        engine._profile_override = "audit"
        engine.record_attempt("debugger", "attached")
        client = application.test_client()
        resp = client.post("/api/billing/checkout", json={})
        assert resp.status_code != 403  # audit profile: no method block

    def test_lockout_profile_restricts(self, app):
        application, engine = app
        engine._profile_override = "lockout"
        engine.record_attempt("integrity", "one")
        engine.record_attempt("state_tamper", "two")
        assert engine.get_status()["triggered"] is True
        client = application.test_client()
        resp = client.post("/api/billing/checkout", json={})
        assert resp.status_code == 403


class TestFailOpen:
    def test_broken_engine_never_bricks(self, app):
        application, engine = app
        # sabotage the engine
        engine._flag = None  # type: ignore
        client = application.test_client()
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_non_api_paths_unaffected(self, app):
        application, engine = app
        engine._flag(["ip:127.0.0.1"], reason="test")
        client = application.test_client()
        resp = client.get("/")
        assert resp.status_code in (200, 404)  # SPA shell or fallback, never 403
