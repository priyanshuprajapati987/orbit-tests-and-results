"""Unit tests for orbit/orbit/core/observability_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.observability_bp import observability_bp


class TestObservabilityBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(observability_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(observability_bp.name, "observability_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/observability/dashboard", "/api/observability/routing",
                  "/api/observability/tasks", "/api/observability/tools",
                  "/api/observability/recovery", "/api/observability/memory",
                  "/api/observability/latency", "/api/observability/interventions",
                  "/api/observability/record"]:
            self.assertIn(p, rules)

    def test_dashboard(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            go.return_value.get_dashboard.return_value = {"total": 5}
            r = self.client.get("/api/observability/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_routing(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            go.return_value.get_routing_accuracy.return_value = {"acc": 0.9}
            r = self.client.get("/api/observability/routing")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["acc"], 0.9)

    def test_tasks(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            go.return_value.get_task_completion.return_value = {"done": 3}
            r = self.client.get("/api/observability/tasks")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["done"], 3)

    def test_tools(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            go.return_value.get_tool_success.return_value = {"ok": True}
            r = self.client.get("/api/observability/tools")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_recovery(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            go.return_value.get_recovery_rate.return_value = {"rate": 0.8}
            r = self.client.get("/api/observability/recovery")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["rate"], 0.8)

    def test_memory(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            go.return_value.get_memory_accuracy.return_value = {"acc": 0.7}
            r = self.client.get("/api/observability/memory")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["acc"], 0.7)

    def test_latency(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            go.return_value.get_latency.return_value = {"avg": 1.2}
            r = self.client.get("/api/observability/latency")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["avg"], 1.2)

    def test_interventions(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            go.return_value.get_interventions.return_value = {"count": 2}
            r = self.client.get("/api/observability/interventions")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 2)

    def test_record_unknown_type_400(self):
        r = self.client.post("/api/observability/record", json={"type": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_routing(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            r = self.client.post("/api/observability/record", json={
                "type": "routing", "query": "q", "routed_to": "TAS", "correct": True, "confidence": 0.9
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "recorded")
        go.return_value.record_routing.assert_called_once_with(query="q", routed_to="TAS", correct=True, confidence=0.9)

    def test_record_task(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            r = self.client.post("/api/observability/record", json={
                "type": "task", "task_id": "t1", "success": False, "latency_ms": 10, "agent": "TAS"
            })
        self.assertEqual(r.status_code, 200)
        go.return_value.record_task.assert_called_once_with(task_id="t1", success=False, latency_ms=10, agent="TAS")

    def test_record_tool(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            r = self.client.post("/api/observability/record", json={
                "type": "tool", "tool_name": "search", "success": True, "latency_ms": 5, "agent": "RES"
            })
        self.assertEqual(r.status_code, 200)
        go.return_value.record_tool.assert_called_once_with(tool_name="search", success=True, latency_ms=5, agent="RES")

    def test_record_recovery(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            r = self.client.post("/api/observability/record", json={
                "type": "recovery", "attempt": 2, "success": True, "strategy": "retry", "latency_ms": 100
            })
        self.assertEqual(r.status_code, 200)
        go.return_value.record_recovery.assert_called_once_with(attempt=2, success=True, strategy="retry", latency_ms=100)

    def test_record_memory(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            r = self.client.post("/api/observability/record", json={
                "type": "memory", "query": "q", "relevant": False, "score": 0.5
            })
        self.assertEqual(r.status_code, 200)
        go.return_value.record_memory.assert_called_once_with(query="q", relevant=False, score=0.5)

    def test_record_intervention(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            r = self.client.post("/api/observability/record", json={
                "type": "intervention", "reason": "r", "agent": "TAS", "corrected_to": "COD"
            })
        self.assertEqual(r.status_code, 200)
        go.return_value.record_intervention.assert_called_once_with(reason="r", agent="TAS", corrected_to="COD")

    def test_record_defaults(self):
        with patch("orbit.core.observability_bp.get_observability") as go:
            r = self.client.post("/api/observability/record", json={"type": "routing"})
        go.return_value.record_routing.assert_called_once_with(query="", routed_to="", correct=True, confidence=0)

    def test_record_no_body(self):
        r = self.client.post("/api/observability/record")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
