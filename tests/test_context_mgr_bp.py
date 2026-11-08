"""Unit tests for orbit/orbit/core/context_mgr_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.context_mgr_bp import context_mgr_bp


class TestContextMgrBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(context_mgr_bp)
        self.client = self.app.test_client()
        self.fake = MagicMock()
        sys.modules["orbit.orbit.core.context_window_manager"] = self.fake

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.context_window_manager", None)

    def test_blueprint_name(self):
        self.assertEqual(context_mgr_bp.name, "context_mgr")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/context-manager/register", "/api/context-manager/request",
                  "/api/context-manager/usage", "/api/context-manager/release",
                  "/api/context-manager/system-prompt", "/api/context-manager/overview",
                  "/api/context-manager/stats"]:
            self.assertIn(p, rules)

    def test_register_missing_agent_400(self):
        r = self.client.post("/api/context-manager/register", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_register_success(self):
        agent = MagicMock()
        agent.agent_id = "a1"
        agent.priority = 5
        self.fake.get_context_manager.return_value.register_agent.return_value = agent
        r = self.client.post("/api/context-manager/register", json={"agent_id": "a1", "priority": 5})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["agent_id"], "a1")
        self.assertEqual(body["priority"], 5)
        self.fake.get_context_manager.return_value.register_agent.assert_called_once_with("a1", 5)

    def test_register_default_priority(self):
        agent = MagicMock()
        agent.agent_id = "a2"
        agent.priority = None
        self.fake.get_context_manager.return_value.register_agent.return_value = agent
        r = self.client.post("/api/context-manager/register", json={"agent_id": "a2"})
        self.fake.get_context_manager.return_value.register_agent.assert_called_once_with("a2", None)

    def test_register_no_body(self):
        r = self.client.post("/api/context-manager/register")
        self.assertEqual(r.status_code, 400)

    def test_request_missing_400(self):
        r = self.client.post("/api/context-manager/request", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_request_bad_tokens_400(self):
        r = self.client.post("/api/context-manager/request", json={"agent_id": "a1", "tokens": 0})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_request_success(self):
        cr = MagicMock()
        cr.request_id = "r1"
        cr.granted_tokens = 5
        cr.status = "granted"
        self.fake.get_context_manager.return_value.request_tokens.return_value = cr
        r = self.client.post("/api/context-manager/request", json={"agent_id": "a1", "tokens": 5})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["request_id"], "r1")
        self.assertEqual(body["granted"], 5)
        self.assertEqual(body["status"], "granted")
        self.fake.get_context_manager.return_value.request_tokens.assert_called_once_with("a1", 5)

    def test_request_no_body(self):
        r = self.client.post("/api/context-manager/request")
        self.assertEqual(r.status_code, 400)

    def test_usage_missing_agent_400(self):
        r = self.client.post("/api/context-manager/usage", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_usage_success(self):
        r = self.client.post("/api/context-manager/usage", json={"agent_id": "a1", "tokens": 3})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "reported")
        self.fake.get_context_manager.return_value.report_usage.assert_called_once_with("a1", 3)

    def test_usage_default_tokens(self):
        r = self.client.post("/api/context-manager/usage", json={"agent_id": "a1"})
        self.fake.get_context_manager.return_value.report_usage.assert_called_once_with("a1", 0)

    def test_usage_no_body(self):
        r = self.client.post("/api/context-manager/usage")
        self.assertEqual(r.status_code, 400)

    def test_release_missing_agent_400(self):
        r = self.client.post("/api/context-manager/release", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_release_success(self):
        r = self.client.post("/api/context-manager/release", json={"agent_id": "a1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "released")
        self.fake.get_context_manager.return_value.release.assert_called_once_with("a1")

    def test_release_no_body(self):
        r = self.client.post("/api/context-manager/release")
        self.assertEqual(r.status_code, 400)

    def test_system_prompt(self):
        r = self.client.post("/api/context-manager/system-prompt", json={"tokens": 100})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "set")
        self.assertEqual(r.get_json()["tokens"], 100)
        self.fake.get_context_manager.return_value.set_system_prompt.assert_called_once_with(100)

    def test_system_prompt_default(self):
        r = self.client.post("/api/context-manager/system-prompt", json={})
        self.fake.get_context_manager.return_value.set_system_prompt.assert_called_once_with(0)

    def test_system_prompt_no_body(self):
        r = self.client.post("/api/context-manager/system-prompt")
        self.fake.get_context_manager.return_value.set_system_prompt.assert_called_once_with(0)

    def test_overview(self):
        self.fake.get_context_manager.return_value.get_overview.return_value = {"total": 5}
        r = self.client.get("/api/context-manager/overview")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_stats(self):
        self.fake.get_context_manager.return_value.get_stats.return_value = {"active": 2}
        r = self.client.get("/api/context-manager/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["active"], 2)


if __name__ == "__main__":
    unittest.main()
