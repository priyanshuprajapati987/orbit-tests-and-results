"""Unit tests for orbit/orbit/core/agent_coordination_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.agent_coordination_bp import agent_coordination_bp


class TestAgentCoordinationBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(agent_coordination_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(agent_coordination_bp.name, "agent_coordination_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/coordination/status", "/api/coordination/templates", "/api/coordination/run",
                  "/api/coordination/active", "/api/coordination/history"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.agent_coordination_bp.get_coordinator") as gc:
            gc.return_value.get_stats.return_value = {"active": 1}
            r = self.client.get("/api/coordination/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["active"], 1)

    def test_templates(self):
        with patch("orbit.core.agent_coordination_bp.get_coordinator") as gc:
            gc.return_value.get_templates.return_value = {"t": 1}
            r = self.client.get("/api/coordination/templates")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["t"], 1)

    def test_run_missing_fields_400(self):
        r = self.client.post("/api/coordination/run", json={"template": "t"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_run_success(self):
        stage = MagicMock()
        stage.stage_name = "s1"
        stage.agent = "TAS"
        stage.status = MagicMock(value="done")
        stage.latency_ms = 10
        stage.error = None
        result = MagicMock()
        result.pipeline_id = "p1"
        result.status = MagicMock(value="completed")
        result.stages = [stage]
        result.final_output = "final text"
        result.total_latency_ms = 50
        with patch("orbit.core.agent_coordination_bp.get_coordinator") as gc:
            gc.return_value.run_pipeline.return_value = result
            r = self.client.post("/api/coordination/run", json={"template": "t", "goal": "g", "context": {"k": "v"}})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["pipeline_id"], "p1")
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["stages"][0]["name"], "s1")
        self.assertEqual(body["stages"][0]["agent"], "TAS")
        self.assertEqual(body["stages"][0]["status"], "done")
        self.assertEqual(body["stages"][0]["latency_ms"], 10)
        self.assertIsNone(body["stages"][0]["error"])
        self.assertEqual(body["final_output"], "final text")
        self.assertEqual(body["total_latency_ms"], 50)
        gc.return_value.run_pipeline.assert_called_once_with("t", "g", {"k": "v"})

    def test_run_no_final_output(self):
        result = MagicMock()
        result.pipeline_id = "p2"
        result.status = MagicMock(value="completed")
        result.stages = []
        result.final_output = None
        result.total_latency_ms = 0
        with patch("orbit.core.agent_coordination_bp.get_coordinator") as gc:
            gc.return_value.run_pipeline.return_value = result
            r = self.client.post("/api/coordination/run", json={"template": "t", "goal": "g"})
        self.assertIsNone(r.get_json()["final_output"])
        gc.return_value.run_pipeline.assert_called_once_with("t", "g", None)

    def test_run_no_body(self):
        r = self.client.post("/api/coordination/run")
        self.assertEqual(r.status_code, 400)

    def test_active(self):
        with patch("orbit.core.agent_coordination_bp.get_coordinator") as gc:
            gc.return_value.get_active.return_value = {"active": 1}
            r = self.client.get("/api/coordination/active")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["active"], 1)

    def test_active_idle(self):
        with patch("orbit.core.agent_coordination_bp.get_coordinator") as gc:
            gc.return_value.get_active.return_value = None
            r = self.client.get("/api/coordination/active")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "idle"})

    def test_history(self):
        with patch("orbit.core.agent_coordination_bp.get_coordinator") as gc:
            gc.return_value.get_history.return_value = [{"p": 1}]
            r = self.client.get("/api/coordination/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["history"], [{"p": 1}])
        gc.return_value.get_history.assert_called_once_with(5)

    def test_history_default(self):
        with patch("orbit.core.agent_coordination_bp.get_coordinator") as gc:
            gc.return_value.get_history.return_value = []
            r = self.client.get("/api/coordination/history")
        gc.return_value.get_history.assert_called_once_with(20)


if __name__ == "__main__":
    unittest.main()
