"""Unit tests for orbit/orbit/core/cost_tracker_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.cost_tracker_bp import cost_tracker_bp


class TestCostTrackerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(cost_tracker_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(cost_tracker_bp.name, "cost_tracker_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/cost-tracker/dashboard", "/api/cost-tracker/record", "/api/cost-tracker/budget",
                  "/api/cost-tracker/providers", "/api/cost-tracker/agents",
                  "/api/cost-tracker/daily", "/api/cost-tracker/records"]:
            self.assertIn(p, rules)

    def test_dashboard(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            gc.return_value.get_dashboard.return_value = {"total": 1.5}
            r = self.client.get("/api/cost-tracker/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 1.5)

    def test_record(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            r = self.client.post("/api/cost-tracker/record", json={
                "provider": "openai", "model": "gpt-4", "agent": "TAS",
                "tokens_in": 10, "tokens_out": 5, "latency_ms": 100
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "recorded")
        gc.return_value.record.assert_called_once_with("openai", "gpt-4", "TAS", 10, 5, 100, source="manual")

    def test_record_defaults(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            r = self.client.post("/api/cost-tracker/record", json={})
        gc.return_value.record.assert_called_once_with("ollama", "", "unknown", 0, 0, 0, source="manual")

    def test_record_no_body(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            r = self.client.post("/api/cost-tracker/record")
        gc.return_value.record.assert_called_once_with("ollama", "", "unknown", 0, 0, 0, source="manual")

    def test_budget_get(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            gc.return_value.check_budget.return_value = {"ok": True}
            r = self.client.get("/api/cost-tracker/budget")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_budget_set(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            r = self.client.post("/api/cost-tracker/budget", json={"daily": 5.0, "monthly": 100.0, "alert_pct": 0.8})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "updated")
        gc.return_value.set_budget.assert_called_once_with(5.0, 100.0, 0.8)

    def test_budget_set_partial(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            r = self.client.post("/api/cost-tracker/budget", json={"daily": 5.0})
        gc.return_value.set_budget.assert_called_once_with(5.0, None, None)

    def test_budget_set_no_body(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            r = self.client.post("/api/cost-tracker/budget")
        gc.return_value.set_budget.assert_called_once_with(None, None, None)

    def test_providers(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            gc.return_value.get_provider_breakdown.return_value = {"openai": 1.0}
            r = self.client.get("/api/cost-tracker/providers")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["openai"], 1.0)

    def test_agents(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            gc.return_value.get_agent_breakdown.return_value = {"TAS": 0.5}
            r = self.client.get("/api/cost-tracker/agents")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["TAS"], 0.5)

    def test_daily(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            gc.return_value.get_daily_costs.return_value = [{"day": "2026-01-01"}]
            r = self.client.get("/api/cost-tracker/daily?days=7")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"day": "2026-01-01"}])
        gc.return_value.get_daily_costs.assert_called_once_with(7)

    def test_daily_default(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            gc.return_value.get_daily_costs.return_value = []
            r = self.client.get("/api/cost-tracker/daily")
        gc.return_value.get_daily_costs.assert_called_once_with(30)

    def test_records(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            gc.return_value.get_recent_records.return_value = [{"id": 1}]
            r = self.client.get("/api/cost-tracker/records?limit=10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"id": 1}])
        gc.return_value.get_recent_records.assert_called_once_with(10)

    def test_records_default(self):
        with patch("orbit.core.cost_tracker_bp.get_cost_tracker") as gc:
            gc.return_value.get_recent_records.return_value = []
            r = self.client.get("/api/cost-tracker/records")
        gc.return_value.get_recent_records.assert_called_once_with(50)


if __name__ == "__main__":
    unittest.main()
