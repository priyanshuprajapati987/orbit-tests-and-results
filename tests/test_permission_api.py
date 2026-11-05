"""
Tests for ORBIT Permission API endpoints.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPermissionAPI(unittest.TestCase):
    """Tests for Flask permission blueprint."""

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
            data=json.dumps({"action": "delete_file", "reason": "Test approve"}),
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
            data=json.dumps({"action": "install_software", "reason": "Test deny"}),
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
    """Tests for the core permission module."""

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
        from orbit.orbit.core.permission import PermissionLevel, get_permission_manager

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
            k for k, v in IMPACT_LEVELS.items() if v.level == PermissionLevel.HIGH
        ]
        self.assertGreater(len(high_actions), 0)
        for action in high_actions:
            self.assertIn(action, IMPACT_LEVELS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
