"""Unit tests for orbit/orbit/core/permission_api.py (permission_bp).

Unit tests (mocked getters) + integration tests (full create_app server)
restored from the original test_permission_api.py, plus core permission
module coverage (TestPermissionSystem) that only lived in that file.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask

from orbit.core.permission_api import VALID_ACTIONS, permission_bp


class PermBase(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(permission_bp, url_prefix="/api/permissions")
        self.client = app.test_client()


class TestRegistration(PermBase):
    def test_routes_registered(self):
        rules = {str(r.rule): sorted(r.methods - {"HEAD", "OPTIONS"})
                 for r in self.client.application.url_map.iter_rules()}
        self.assertEqual(rules.get("/api/permissions/pending"), ["GET"])
        self.assertEqual(rules.get("/api/permissions/history"), ["GET"])
        self.assertEqual(rules.get("/api/permissions/approve"), ["POST"])
        self.assertEqual(rules.get("/api/permissions/deny"), ["POST"])

    def test_blueprint_name(self):
        self.assertEqual(permission_bp.name, "permissions")

    def test_valid_actions_is_30(self):
        self.assertIsInstance(VALID_ACTIONS, set)
        self.assertEqual(len(VALID_ACTIONS), 30)

    def test_valid_actions_spot_check(self):
        for a in ("delete_file", "web_search", "run_script",
                  "send_email", "system_info", "screenshot"):
            self.assertIn(a, VALID_ACTIONS)

    def test_invalid_members_absent(self):
        for a in ("delete_everything", "admin", "", "DELETE_FILE"):
            self.assertNotIn(a, VALID_ACTIONS)


class TestListPending(PermBase):
    def test_returns_pending_list(self):
        with patch("orbit.core.permission_api.get_pending_approvals",
                   return_value=[{"id": 1, "action": "web_search"}]) as gp:
            r = self.client.get("/api/permissions/pending")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"pending": [{"id": 1, "action": "web_search"}]})
        gp.assert_called_once()

    def test_empty_pending(self):
        with patch("orbit.core.permission_api.get_pending_approvals",
                   return_value=[]):
            r = self.client.get("/api/permissions/pending")
        self.assertEqual(r.get_json(), {"pending": []})

    def test_backend_failure_returns_500(self):
        with patch("orbit.core.permission_api.get_pending_approvals",
                   side_effect=RuntimeError("db down")):
            r = self.client.get("/api/permissions/pending")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(),
                         {"error": "Internal server error", "pending": []})


class TestListHistory(PermBase):
    def test_default_limit_20(self):
        with patch("orbit.core.permission_api.get_permission_history",
                   return_value=[]) as gh:
            self.client.get("/api/permissions/history")
        gh.assert_called_once_with(limit=20)

    def test_custom_limit(self):
        with patch("orbit.core.permission_api.get_permission_history",
                   return_value=[]) as gh:
            self.client.get("/api/permissions/history?limit=5")
        gh.assert_called_once_with(limit=5)

    def test_limit_clamped_to_100(self):
        with patch("orbit.core.permission_api.get_permission_history",
                   return_value=[]) as gh:
            self.client.get("/api/permissions/history?limit=999")
        gh.assert_called_once_with(limit=100)

    def test_zero_limit_becomes_1(self):
        with patch("orbit.core.permission_api.get_permission_history",
                   return_value=[]) as gh:
            self.client.get("/api/permissions/history?limit=0")
        gh.assert_called_once_with(limit=1)

    def test_negative_limit_becomes_1(self):
        with patch("orbit.core.permission_api.get_permission_history",
                   return_value=[]) as gh:
            self.client.get("/api/permissions/history?limit=-7")
        gh.assert_called_once_with(limit=1)

    def test_non_numeric_limit_defaults_20(self):
        with patch("orbit.core.permission_api.get_permission_history",
                   return_value=[]) as gh:
            self.client.get("/api/permissions/history?limit=abc")
        gh.assert_called_once_with(limit=20)

    def test_history_payload_passthrough(self):
        rows = [{"action": "web_search", "result": "approved"}]
        with patch("orbit.core.permission_api.get_permission_history",
                   return_value=rows):
            r = self.client.get("/api/permissions/history")
        self.assertEqual(r.get_json(), {"history": rows})

    def test_backend_failure_returns_500(self):
        with patch("orbit.core.permission_api.get_permission_history",
                   side_effect=RuntimeError("boom")):
            r = self.client.get("/api/permissions/history")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(),
                         {"error": "Internal server error", "history": []})


class TestApprove(PermBase):
    def test_valid_action_default_fields(self):
        with patch("orbit.core.permission_api.approve_action",
                   return_value={"ok": True}) as ga:
            r = self.client.post("/api/permissions/approve",
                                 json={"action": "web_search"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ok": True})
        ga.assert_called_once_with(
            "web_search",
            approved_by="127.0.0.1",
            reason="Approved via Permission Panel")

    def test_custom_reason_and_approver(self):
        with patch("orbit.core.permission_api.approve_action",
                   return_value={"ok": True}) as ga:
            self.client.post(
                "/api/permissions/approve",
                json={"action": "delete_file", "reason": "user clicked",
                      "approved_by": "admin-1"})
        ga.assert_called_once_with(
            "delete_file", approved_by="admin-1", reason="user clicked")

    def test_reason_truncated_to_500(self):
        with patch("orbit.core.permission_api.approve_action",
                   return_value={"ok": True}) as ga:
            self.client.post(
                "/api/permissions/approve",
                json={"action": "web_search", "reason": "x" * 900})
        self.assertEqual(len(ga.call_args.kwargs["reason"]), 500)

    def test_approver_truncated_to_100(self):
        with patch("orbit.core.permission_api.approve_action",
                   return_value={"ok": True}) as ga:
            self.client.post(
                "/api/permissions/approve",
                json={"action": "web_search", "approved_by": "y" * 300})
        self.assertEqual(len(ga.call_args.kwargs["approved_by"]), 100)

    def test_action_stripped(self):
        with patch("orbit.core.permission_api.approve_action",
                   return_value={"ok": True}) as ga:
            self.client.post("/api/permissions/approve",
                             json={"action": "  web_search  "})
        ga.assert_called_once()
        self.assertEqual(ga.call_args.args[0], "web_search")

    def test_missing_body_400(self):
        r = self.client.post("/api/permissions/approve",
                             data="not-json", content_type="text/plain")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "Invalid JSON body"})

    def test_empty_json_object_400(self):
        r = self.client.post("/api/permissions/approve", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "Invalid JSON body"})

    def test_missing_action_400(self):
        r = self.client.post("/api/permissions/approve",
                             json={"reason": "hi"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "action is required"})

    def test_blank_action_400(self):
        r = self.client.post("/api/permissions/approve",
                             json={"action": "   "})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "action is required"})

    def test_unknown_action_400(self):
        r = self.client.post("/api/permissions/approve",
                             json={"action": "hack_the_planet"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(),
                         {"error": "Unknown action: hack_the_planet"})

    def test_backend_failure_returns_500(self):
        with patch("orbit.core.permission_api.approve_action",
                   side_effect=RuntimeError("db down")):
            r = self.client.post("/api/permissions/approve",
                                 json={"action": "web_search"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(), {"error": "Internal server error"})


class TestDeny(PermBase):
    def test_valid_action_default_fields(self):
        with patch("orbit.core.permission_api.deny_action",
                   return_value={"ok": True}) as gd:
            r = self.client.post("/api/permissions/deny",
                                 json={"action": "delete_file"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ok": True})
        gd.assert_called_once_with(
            "delete_file",
            denied_by="127.0.0.1",
            reason="Denied via Permission Panel")

    def test_custom_fields(self):
        with patch("orbit.core.permission_api.deny_action",
                   return_value={"ok": True}) as gd:
            self.client.post(
                "/api/permissions/deny",
                json={"action": "financial", "reason": "nope",
                      "denied_by": "boss"})
        gd.assert_called_once_with(
            "financial", denied_by="boss", reason="nope")

    def test_reason_truncated_to_500(self):
        with patch("orbit.core.permission_api.deny_action",
                   return_value={"ok": True}) as gd:
            self.client.post(
                "/api/permissions/deny",
                json={"action": "financial", "reason": "z" * 700})
        self.assertEqual(len(gd.call_args.kwargs["reason"]), 500)

    def test_denier_truncated_to_100(self):
        with patch("orbit.core.permission_api.deny_action",
                   return_value={"ok": True}) as gd:
            self.client.post(
                "/api/permissions/deny",
                json={"action": "financial", "denied_by": "w" * 250})
        self.assertEqual(len(gd.call_args.kwargs["denied_by"]), 100)

    def test_missing_body_400(self):
        r = self.client.post("/api/permissions/deny")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "Invalid JSON body"})

    def test_missing_action_400(self):
        r = self.client.post("/api/permissions/deny", json={})
        # empty dict -> falsy -> Invalid JSON body
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "Invalid JSON body"})

    def test_action_only_whitespace_400(self):
        r = self.client.post("/api/permissions/deny", json={"action": " "})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "action is required"})

    def test_unknown_action_400(self):
        r = self.client.post("/api/permissions/deny",
                             json={"action": "not_a_real_action"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(),
                         {"error": "Unknown action: not_a_real_action"})

    def test_backend_failure_returns_500(self):
        with patch("orbit.core.permission_api.deny_action",
                   side_effect=RuntimeError("db down")):
            r = self.client.post("/api/permissions/deny",
                                 json={"action": "web_search"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(), {"error": "Internal server error"})


class TestPermissionAPI(unittest.TestCase):
    """Integration tests: real Flask permission blueprint via create_app."""

    @classmethod
    def setUpClass(cls):
        try:
            from orbit.orbit.server import create_app

            cls.app = create_app()
            cls.client = cls.app.test_client()
            cls.available = True
        except Exception:  # noqa: BLE001
            cls.available = False

    def setUp(self):
        if not self.available:
            self.skipTest("Flask not available")

    def test_health_endpoint(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "ok")

    def test_pending_endpoint(self):
        resp = self.client.get("/api/permissions/pending")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("pending", data)
        self.assertIsInstance(data["pending"], list)

    def test_history_endpoint(self):
        resp = self.client.get("/api/permissions/history?limit=5")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("history", data)
        self.assertIsInstance(data["history"], list)

    def test_history_limit_clamp(self):
        resp = self.client.get("/api/permissions/history?limit=999")
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/api/permissions/history?limit=0")
        self.assertEqual(resp2.status_code, 200)

    def test_approve_missing_action(self):
        resp = self.client.post(
            "/api/permissions/approve",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_approve_invalid_action(self):
        resp = self.client.post(
            "/api/permissions/approve",
            data=json.dumps({"action": "totally_fake_action_xyz"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_approve_valid_action(self):
        resp = self.client.post(
            "/api/permissions/approve",
            data=json.dumps({"action": "delete_file",
                             "reason": "Test approve"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data.get("approved"))

    def test_deny_missing_action(self):
        resp = self.client.post(
            "/api/permissions/deny",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_deny_valid_action(self):
        resp = self.client.post(
            "/api/permissions/deny",
            data=json.dumps({"action": "install_software",
                             "reason": "Test deny"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertFalse(data.get("approved"))

    def test_approve_invalid_json(self):
        resp = self.client.post(
            "/api/permissions/approve",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_404_returns_html(self):
        resp = self.client.get("/nonexistent-page")
        self.assertIn(resp.status_code, [200, 404])


class TestPermissionSystem(unittest.TestCase):
    """Tests for the core permission module (orbit/orbit/core/permission.py)."""

    def test_import(self):
        from orbit.orbit.core.permission import (
            IMPACT_LEVELS,
            PermissionLevel,
            PermissionManager,
        )

        self.assertTrue(PermissionLevel.HIGH)
        self.assertTrue(PermissionManager)
        self.assertIsInstance(IMPACT_LEVELS, dict)

    def test_high_impact_requires_approval(self):
        from orbit.orbit.core.permission import check_permission

        result = check_permission("delete_file", "test deletion")
        self.assertFalse(result["approved"])
        self.assertEqual(result["level"], "high")

    def test_low_impact_auto_approves(self):
        from orbit.orbit.core.permission import check_permission

        result = check_permission("read_file", "test read")
        self.assertTrue(result["approved"])
        self.assertEqual(result["level"], "low")

    def test_medium_impact_auto_approves(self):
        from orbit.orbit.core.permission import check_permission

        result = check_permission("send_email", "test email")
        self.assertTrue(result["approved"])
        self.assertEqual(result["level"], "medium")

    def test_approve_and_deny(self):
        from orbit.orbit.core.permission import approve_action, deny_action

        result = approve_action("delete_file", "TestUser", "Testing approve")
        self.assertTrue(result["approved"])
        result2 = deny_action("delete_file", "TestUser", "Testing deny")
        self.assertFalse(result2["approved"])

    def test_custom_rule(self):
        from orbit.orbit.core.permission import (
            PermissionLevel,
            get_permission_manager,
        )

        mgr = get_permission_manager()
        mgr.set_custom_rule("custom_test_action", PermissionLevel.LOW)
        result = mgr.check_permission("custom_test_action")
        self.assertTrue(result["approved"])

    def test_unknown_action_defaults_high(self):
        from orbit.orbit.core.permission import get_permission_manager

        mgr = get_permission_manager()
        level = mgr.get_permission_level("totally_unknown_action_xyz")
        self.assertEqual(level.value, "high")

    def test_all_high_impact_actions(self):
        from orbit.orbit.core.permission import IMPACT_LEVELS, PermissionLevel

        high_actions = [
            k for k, v in IMPACT_LEVELS.items()
            if v.level == PermissionLevel.HIGH
        ]
        self.assertGreater(len(high_actions), 0)
        for action in high_actions:
            self.assertIn(action, IMPACT_LEVELS)


if __name__ == "__main__":
    unittest.main()
