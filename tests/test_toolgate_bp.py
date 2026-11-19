"""Unit tests for orbit/orbit/core/toolgate_bp.py (toolgate_bp).

Unit tests (mocked PolicyEngine + require_admin paths) + integration
tests (full create_app server, real PolicyEngine) restored from the
original test_toolgate_bp.py.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask

from orbit.core.toolgate_bp import toolgate_bp


def _engine():
    eng = MagicMock()
    eng.stats.return_value = {
        "workspace": "/tmp/ws",
        "strict": True,
        "approved_paths": 0,
        "approved_actions": 0,
    }
    eng.get_audit_log.return_value = [{"event": "gate.allow",
                                       "detail": "x"}]
    eng.approve_path.return_value = True
    return eng


def _session_factory_with_users():
    Session = MagicMock()
    db = Session.return_value.__enter__.return_value
    db.query.return_value.count.return_value = 1
    return Session


class TgBase(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(toolgate_bp)
        self.client = app.test_client()
        self.engine = _engine()

    def _eng_patch(self):
        return patch("orbit.core.toolgate_bp.get_policy_engine",
                     return_value=self.engine)

    def _no_users(self):
        """Gate falls through (single-user deployment)."""
        return patch("orbit.core.auth.store.get_session_factory",
                     side_effect=RuntimeError("no db"))


class TestRegistration(TgBase):
    def test_routes_registered(self):
        rules = {str(r.rule): sorted(r.methods - {"HEAD", "OPTIONS"})
                 for r in self.client.application.url_map.iter_rules()}
        self.assertEqual(rules.get("/api/toolgate/status"), ["GET"])
        self.assertEqual(rules.get("/api/toolgate/audit"), ["GET"])
        self.assertEqual(rules.get("/api/toolgate/approve"), ["POST"])
        self.assertEqual(rules.get("/api/toolgate/revoke"), ["POST"])

    def test_blueprint_prefix(self):
        self.assertEqual(toolgate_bp.url_prefix, "/api/toolgate")


class TestStatus(TgBase):
    def test_returns_engine_stats(self):
        with self._no_users(), self._eng_patch():
            r = self.client.get("/api/toolgate/status")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["workspace"], "/tmp/ws")
        self.assertTrue(data["strict"])

    def test_engine_failure_returns_500(self):
        with self._no_users(), self._eng_patch() as ge:
            ge.return_value.stats.side_effect = RuntimeError("engine broke")
            r = self.client.get("/api/toolgate/status")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(), {"error": "engine broke"})


class TestAudit(TgBase):
    def test_default_limit_50(self):
        with self._no_users(), self._eng_patch():
            self.client.get("/api/toolgate/audit")
        self.engine.get_audit_log.assert_called_once_with(limit=50)

    def test_custom_limit(self):
        with self._no_users(), self._eng_patch():
            self.client.get("/api/toolgate/audit?limit=100")
        self.engine.get_audit_log.assert_called_once_with(limit=100)

    def test_limit_clamped_to_500(self):
        with self._no_users(), self._eng_patch():
            self.client.get("/api/toolgate/audit?limit=999")
        self.engine.get_audit_log.assert_called_once_with(limit=500)

    def test_zero_limit_becomes_1(self):
        with self._no_users(), self._eng_patch():
            self.client.get("/api/toolgate/audit?limit=0")
        self.engine.get_audit_log.assert_called_once_with(limit=1)

    def test_negative_limit_becomes_1(self):
        with self._no_users(), self._eng_patch():
            self.client.get("/api/toolgate/audit?limit=-4")
        self.engine.get_audit_log.assert_called_once_with(limit=1)

    def test_non_numeric_limit_defaults_50(self):
        with self._no_users(), self._eng_patch():
            self.client.get("/api/toolgate/audit?limit=zz")
        self.engine.get_audit_log.assert_called_once_with(limit=50)

    def test_audit_payload_passthrough(self):
        with self._no_users(), self._eng_patch():
            r = self.client.get("/api/toolgate/audit")
        self.assertEqual(r.get_json(),
                         {"audit": [{"event": "gate.allow",
                                     "detail": "x"}]})

    def test_engine_failure_returns_500(self):
        with self._no_users(), self._eng_patch() as ge:
            ge.return_value.get_audit_log.side_effect = RuntimeError("bad")
            r = self.client.get("/api/toolgate/audit")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(), {"error": "bad"})


class TestApprove(TgBase):
    def test_approve_path(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post("/api/toolgate/approve",
                                 json={"path": "/etc/hosts"})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"]["workspace"], "/tmp/ws")
        self.engine.approve_path.assert_called_once_with("/etc/hosts")

    def test_approve_action(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post("/api/toolgate/approve",
                                 json={"action": "shell"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.engine.approve_action.assert_called_once_with("shell")

    def test_path_wins_over_action(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post(
                "/api/toolgate/approve",
                json={"path": "/tmp/x", "action": "shell"})
        self.assertEqual(r.status_code, 200)
        self.engine.approve_path.assert_called_once()
        self.engine.approve_action.assert_not_called()

    def test_neither_path_nor_action_400(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post("/api/toolgate/approve", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.get_json(),
            {"error": "provide a valid 'path' or 'action'"})

    def test_empty_body_400(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post("/api/toolgate/approve",
                                 data="", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_engine_failure_returns_500(self):
        with self._no_users(), self._eng_patch() as ge:
            ge.return_value.approve_path.side_effect = RuntimeError("x")
            r = self.client.post("/api/toolgate/approve",
                                 json={"path": "/tmp/y"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(), {"error": "x"})


class TestRevoke(TgBase):
    def test_revoke_path(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post("/api/toolgate/revoke",
                                 json={"path": "/etc/hosts"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.engine.deny_path.assert_called_once_with("/etc/hosts")

    def test_revoke_action(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post("/api/toolgate/revoke",
                                 json={"action": "shell"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.engine.revoke_action.assert_called_once_with("shell")

    def test_neither_path_nor_action_400(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post("/api/toolgate/revoke", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.get_json(),
            {"error": "provide a valid 'path' or 'action'"})

    def test_engine_failure_returns_500(self):
        with self._no_users(), self._eng_patch() as ge:
            ge.return_value.deny_path.side_effect = RuntimeError("zz")
            r = self.client.post("/api/toolgate/revoke",
                                 json={"path": "/tmp/z"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(), {"error": "zz"})


class TestAdminGuard(TgBase):
    def test_no_users_falls_through(self):
        with self._no_users(), self._eng_patch():
            r = self.client.post("/api/toolgate/approve",
                                 json={"path": "/tmp/ok"})
        self.assertEqual(r.status_code, 200)

    def test_users_without_login_401(self):
        with patch("orbit.core.auth.store.get_session_factory",
                   return_value=_session_factory_with_users()), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "", "role": ""}), \
             self._eng_patch():
            r = self.client.post("/api/toolgate/approve",
                                 json={"path": "/tmp/x"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json(), {"error": "login required"})
        self.engine.approve_path.assert_not_called()

    def test_non_admin_403(self):
        with patch("orbit.core.auth.store.get_session_factory",
                   return_value=_session_factory_with_users()), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "u1", "role": "user"}), \
             self._eng_patch():
            r = self.client.post("/api/toolgate/approve",
                                 json={"path": "/tmp/x"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json(), {"error": "admin required"})

    def test_admin_passes_gate(self):
        with patch("orbit.core.auth.store.get_session_factory",
                   return_value=_session_factory_with_users()), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "u1", "role": "admin"}), \
             self._eng_patch():
            r = self.client.post("/api/toolgate/approve",
                                 json={"path": "/tmp/x"})
        self.assertEqual(r.status_code, 200)
        self.engine.approve_path.assert_called_once_with("/tmp/x")

    def test_revoke_requires_login_too(self):
        with patch("orbit.core.auth.store.get_session_factory",
                   return_value=_session_factory_with_users()), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "", "role": ""}), \
             self._eng_patch():
            r = self.client.post("/api/toolgate/revoke",
                                 json={"path": "/tmp/x"})
        self.assertEqual(r.status_code, 401)
        self.engine.deny_path.assert_not_called()

    def test_status_and_audit_not_admin_gated(self):
        with patch("orbit.core.auth.store.get_session_factory",
                   return_value=_session_factory_with_users()), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "", "role": ""}), \
             self._eng_patch():
            s = self.client.get("/api/toolgate/status")
            a = self.client.get("/api/toolgate/audit")
        self.assertEqual(s.status_code, 200)
        self.assertEqual(a.status_code, 200)


# ---------------------------------------------------------------------------
# Integration tests (restored from original test_toolgate_bp.py): full
# create_app server + real PolicyEngine.
# ---------------------------------------------------------------------------


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
    res = client.post("/api/toolgate/approve",
                      json={"action": "file.write"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "file.write" in data["status"]["approved_actions"]


def test_revoke_action(client):
    client.post("/api/toolgate/approve", json={"action": "system.command"})
    res = client.post("/api/toolgate/revoke",
                      json={"action": "system.command"})
    assert res.status_code == 200
    assert "system.command" not in \
        res.get_json()["status"]["approved_actions"]


def test_approve_path(client):
    res = client.post("/api/toolgate/approve",
                      json={"path": "D:/temp/allowed"})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True


if __name__ == "__main__":
    unittest.main()
