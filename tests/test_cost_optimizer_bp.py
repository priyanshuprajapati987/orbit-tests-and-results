"""Unit tests for orbit/orbit/core/cost_optimizer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.cost_optimizer_bp import cost_optimizer_bp


class TestCostOptimizerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(cost_optimizer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(cost_optimizer_bp.name, "cost_optimizer")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/cost/record", "/api/cost/recommend", "/api/cost/budget", "/api/cost/forecast", "/api/cost/stats"]:
            self.assertIn(p, rules)

    def test_record(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.record_call.return_value = {"cost_usd": 0.001}
            r = self.client.post("/api/cost/record", json={"model": "gpt-4o", "tokens_in": 10, "tokens_out": 5, "task_type": "code"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cost_usd"], 0.001)
        gc.return_value.record_call.assert_called_once_with(model="gpt-4o", tokens_in=10, tokens_out=5, task_type="code")

    def test_record_defaults(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.record_call.return_value = {"cost_usd": 0.0}
            r = self.client.post("/api/cost/record", json={})
        gc.return_value.record_call.assert_called_once_with(model="gpt-4o-mini", tokens_in=0, tokens_out=0, task_type="general")

    def test_record_input_tokens_alias(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.record_call.return_value = {"cost_usd": 0.0}
            r = self.client.post("/api/cost/record", json={"input_tokens": 7, "output_tokens": 3})
        gc.return_value.record_call.assert_called_once_with(model="gpt-4o-mini", tokens_in=7, tokens_out=3, task_type="general")

    def test_record_no_body(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.record_call.return_value = {"cost_usd": 0.0}
            r = self.client.post("/api/cost/record")
        gc.return_value.record_call.assert_called_once_with(model="gpt-4o-mini", tokens_in=0, tokens_out=0, task_type="general")

    def test_recommend(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.select_model.return_value = {"model": "gpt-4o-mini"}
            r = self.client.get("/api/cost/recommend?task_type=fast&quality=high&max_cost=0.1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["model"], "gpt-4o-mini")
        gc.return_value.select_model.assert_called_once_with("fast", "high", 0.1)

    def test_recommend_defaults(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.select_model.return_value = {}
            r = self.client.get("/api/cost/recommend")
        gc.return_value.select_model.assert_called_once_with("fast", "medium", 0.05)

    def test_budget_get(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.get_budget_status.return_value = {"remaining": 9.5}
            r = self.client.get("/api/cost/budget")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["remaining"], 9.5)

    def test_budget_set(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.set_budget.return_value = {"limit": 20}
            r = self.client.post("/api/cost/budget", json={"limit": 20})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["limit"], 20)
        gc.return_value.set_budget.assert_called_once_with(20)

    def test_budget_set_daily_alias(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.set_budget.return_value = {"limit": 5}
            r = self.client.post("/api/cost/budget", json={"daily": 5})
        gc.return_value.set_budget.assert_called_once_with(5)

    def test_budget_set_default(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.set_budget.return_value = {"limit": 10}
            r = self.client.post("/api/cost/budget", json={})
        gc.return_value.set_budget.assert_called_once_with(10)

    def test_budget_set_no_body(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.set_budget.return_value = {"limit": 10}
            r = self.client.post("/api/cost/budget")
        gc.return_value.set_budget.assert_called_once_with(10)

    def test_forecast(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.optimize_prompt.return_value = {"saved": 0.01}
            r = self.client.get("/api/cost/forecast")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["saved"], 0.01)
        gc.return_value.optimize_prompt.assert_called_once_with("Help me write a function")

    def test_forecast_with_prompt(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.optimize_prompt.return_value = {"saved": 0.02}
            r = self.client.get("/api/cost/forecast?prompt=write code")
        gc.return_value.optimize_prompt.assert_called_once_with("write code")

    def test_stats(self):
        with patch("orbit.core.cost_optimizer_bp.get_cost_optimizer") as gc:
            gc.return_value.get_stats.return_value = {"total": 100}
            r = self.client.get("/api/cost/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 100)


if __name__ == "__main__":
    unittest.main()
