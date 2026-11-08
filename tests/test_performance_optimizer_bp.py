"""Unit tests for orbit/orbit/core/performance_optimizer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.performance_optimizer_bp import performance_optimizer_bp


class TestPerformanceOptimizerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(performance_optimizer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(performance_optimizer_bp.name, "performance_optimizer_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/performance/metrics", "/api/performance/metrics/record",
                  "/api/performance/suggestions", "/api/performance/suggestions/add",
                  "/api/performance/suggestions/<suggestion_id>/vote",
                  "/api/performance/suggestions/<suggestion_id>/implement",
                  "/api/performance/stats", "/api/performance/auto-suggest"]:
            self.assertIn(p, rules)

    def test_metrics(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_metrics.return_value = [{"m": 1}]
            r = self.client.get("/api/performance/metrics?category=c&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["metrics"], [{"m": 1}])
        gp.return_value.get_metrics.assert_called_once_with("c", 5)

    def test_metrics_default(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_metrics.return_value = []
            r = self.client.get("/api/performance/metrics")
        gp.return_value.get_metrics.assert_called_once_with(None, 100)

    def test_metrics_invalid_limit(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_metrics.return_value = []
            r = self.client.get("/api/performance/metrics?limit=abc")
        self.assertEqual(r.status_code, 200)
        gp.return_value.get_metrics.assert_called_once_with(None, 100)

    def test_metrics_clamped(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_metrics.return_value = []
            r = self.client.get("/api/performance/metrics?limit=1000")
        gp.return_value.get_metrics.assert_called_once_with(None, 500)

    def test_metrics_record_missing_value_type(self):
        r = self.client.post("/api/performance/metrics/record", json={"value": "abc", "category": "c", "name": "n"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_metrics_record_success(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.record_metric.return_value = {"recorded": True}
            r = self.client.post("/api/performance/metrics/record", json={
                "category": "c", "name": "n", "value": 1.5, "unit": "ms", "tags": ["t"]
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["recorded"], True)
        gp.return_value.record_metric.assert_called_once_with(category="c", name="n", value=1.5, unit="ms", tags=["t"])

    def test_metrics_record_defaults(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.record_metric.return_value = {"recorded": True}
            r = self.client.post("/api/performance/metrics/record", json={})
        gp.return_value.record_metric.assert_called_once_with(category="", name="", value=0.0, unit="", tags=None)

    def test_metrics_record_no_body(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.record_metric.return_value = {"recorded": True}
            r = self.client.post("/api/performance/metrics/record")
        gp.return_value.record_metric.assert_called_once_with(category="", name="", value=0.0, unit="", tags=None)

    def test_suggestions(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_suggestions.return_value = [{"s": 1}]
            r = self.client.get("/api/performance/suggestions?category=c&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["suggestions"], [{"s": 1}])
        gp.return_value.get_suggestions.assert_called_once_with("c", 5)

    def test_suggestions_default(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_suggestions.return_value = []
            r = self.client.get("/api/performance/suggestions")
        gp.return_value.get_suggestions.assert_called_once_with(None, 50)

    def test_suggestions_invalid_limit(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_suggestions.return_value = []
            r = self.client.get("/api/performance/suggestions?limit=abc")
        self.assertEqual(r.status_code, 200)
        gp.return_value.get_suggestions.assert_called_once_with(None, 50)

    def test_suggestions_clamped(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_suggestions.return_value = []
            r = self.client.get("/api/performance/suggestions?limit=1000")
        gp.return_value.get_suggestions.assert_called_once_with(None, 500)

    def test_suggestions_add(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.add_suggestion.return_value = {"id": "s1"}
            r = self.client.post("/api/performance/suggestions/add", json={
                "title": "t", "description": "d", "expected_impact": "high", "category": "c"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "s1")
        gp.return_value.add_suggestion.assert_called_once_with(title="t", description="d", expected_impact="high", category="c")

    def test_suggestions_add_defaults(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.add_suggestion.return_value = {"id": "s2"}
            r = self.client.post("/api/performance/suggestions/add", json={})
        gp.return_value.add_suggestion.assert_called_once_with(title="", description="", expected_impact="medium", category="general")

    def test_suggestions_add_no_body(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.add_suggestion.return_value = {"id": "s3"}
            r = self.client.post("/api/performance/suggestions/add")
        gp.return_value.add_suggestion.assert_called_once_with(title="", description="", expected_impact="medium", category="general")

    def test_suggestion_vote(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.vote_suggestion.return_value = True
            r = self.client.post("/api/performance/suggestions/s1/vote")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        gp.return_value.vote_suggestion.assert_called_once_with("s1")

    def test_suggestion_implement(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.mark_implemented.return_value = True
            r = self.client.post("/api/performance/suggestions/s1/implement")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        gp.return_value.mark_implemented.assert_called_once_with("s1")

    def test_stats(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/performance/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_auto_suggest(self):
        with patch("orbit.core.performance_optimizer_bp.get_performance_optimizer") as gp:
            gp.return_value.generate_auto_suggestions.return_value = [{"s": 1}]
            r = self.client.post("/api/performance/auto-suggest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["suggestions"], [{"s": 1}])


if __name__ == "__main__":
    unittest.main()
