"""Unit tests for orbit/orbit/core/agent_lifecycle_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.agent_lifecycle_bp import agent_lifecycle_bp


class TestAgentLifecycleBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(agent_lifecycle_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(agent_lifecycle_bp.name, "agent_lifecycle")

    def test_url_prefix(self):
        self.assertEqual(agent_lifecycle_bp.url_prefix, "/api/agent-lifecycle")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/agent-lifecycle/status", "/api/agent-lifecycle/create/<label>",
                  "/api/agent-lifecycle/remove/<label>", "/api/agent-lifecycle/test/<label>",
                  "/api/agent-lifecycle/cleanup", "/api/agent-lifecycle/record-success/<label>",
                  "/api/agent-lifecycle/record-failure/<label>", "/api/agent-lifecycle/circuit-breakers"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            gl.return_value.get_status.return_value = {"running": True}
            r = self.client.get("/api/agent-lifecycle/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["running"])

    def test_create_success(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            gl.return_value.create_or_get.return_value = object()
            r = self.client.post("/api/agent-lifecycle/create/TAS", json={"caller": "queen"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["label"], "TAS")
        self.assertEqual(r.get_json()["status"], "created_or_reused")
        gl.return_value.create_or_get.assert_called_once_with("TAS", caller="queen")

    def test_create_failure_400(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            gl.return_value.create_or_get.return_value = None
            r = self.client.post("/api/agent-lifecycle/create/TAS", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_create_no_body(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            gl.return_value.create_or_get.return_value = object()
            r = self.client.post("/api/agent-lifecycle/create/TAS")
        gl.return_value.create_or_get.assert_called_once_with("TAS", caller=None)

    def test_remove_success(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            gl.return_value.remove_agent.return_value = True
            r = self.client.post("/api/agent-lifecycle/remove/TAS")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "removed")
        gl.return_value.remove_agent.assert_called_once_with("TAS")

    def test_remove_failure_400(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            gl.return_value.remove_agent.return_value = False
            r = self.client.post("/api/agent-lifecycle/remove/TAS")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_test_agent(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            gl.return_value.run_test_suite.return_value = {"passed": 3}
            r = self.client.post("/api/agent-lifecycle/test/TAS")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["passed"], 3)
        gl.return_value.run_test_suite.assert_called_once_with("TAS")

    def test_cleanup(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            mgr = gl.return_value
            mgr._pool = [1, 2]
            r = self.client.post("/api/agent-lifecycle/cleanup")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "cleanup_complete")
        self.assertEqual(r.get_json()["remaining"], 2)
        mgr._cleanup_idle.assert_called_once()

    def test_record_success(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            r = self.client.post("/api/agent-lifecycle/record-success/TAS")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "success_recorded")
        gl.return_value.record_success.assert_called_once_with("TAS")

    def test_record_failure(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            r = self.client.post("/api/agent-lifecycle/record-failure/TAS", json={"error": "boom"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "failure_recorded")
        gl.return_value.record_failure.assert_called_once_with("TAS", "boom")

    def test_record_failure_no_body(self):
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle") as gl:
            r = self.client.post("/api/agent-lifecycle/record-failure/TAS")
        gl.return_value.record_failure.assert_called_once_with("TAS", "")

    def test_circuit_breakers(self):
        mgr = MagicMock()
        lock = MagicMock()
        mgr._lock = lock
        cb_mock = MagicMock()
        cb_mock.get_state.return_value = {"state": "closed"}
        mgr._circuit_breakers = {"TAS": cb_mock}
        with patch("orbit.core.agent_lifecycle_bp.get_lifecycle", return_value=mgr):
            r = self.client.get("/api/agent-lifecycle/circuit-breakers")
        self.assertEqual(r.status_code, 200)
        self.assertIn("TAS", r.get_json())
        self.assertEqual(r.get_json()["TAS"], {"state": "closed"})


if __name__ == "__main__":
    unittest.main()
