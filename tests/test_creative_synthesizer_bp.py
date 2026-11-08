"""Unit tests for orbit/orbit/core/creative_synthesizer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.creative_synthesizer_bp import creative_synthesizer_bp


class TestCreativeSynthesizerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(creative_synthesizer_bp)
        self.client = self.app.test_client()
        self.fake = MagicMock()
        sys.modules["orbit.orbit.core.creative_synthesizer"] = self.fake

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.creative_synthesizer", None)

    def test_blueprint_name(self):
        self.assertEqual(creative_synthesizer_bp.name, "creative_synthesizer")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/creative/patterns", "/api/creative/insights", "/api/creative/find-insights",
                  "/api/creative/domains", "/api/creative/stats", "/api/creative/reset"]:
            self.assertIn(p, rules)

    def test_list_patterns(self):
        self.fake.get_creative_synthesizer.return_value.get_patterns.return_value = [{"p": 1}]
        r = self.client.get("/api/creative/patterns?domain=d&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["patterns"], [{"p": 1}])
        self.fake.get_creative_synthesizer.return_value.get_patterns.assert_called_once_with("d", 5)

    def test_list_patterns_default(self):
        self.fake.get_creative_synthesizer.return_value.get_patterns.return_value = []
        r = self.client.get("/api/creative/patterns")
        self.fake.get_creative_synthesizer.return_value.get_patterns.assert_called_once_with(None, 50)

    def test_register_pattern_missing_400(self):
        r = self.client.post("/api/creative/patterns", json={"name": "n"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_register_pattern_success(self):
        self.fake.get_creative_synthesizer.return_value.register_pattern.return_value = {"id": "p1"}
        r = self.client.post("/api/creative/patterns", json={"domain": "d", "name": "n", "description": "desc", "solution": "sol", "tags": ["t"]})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["id"], "p1")
        self.fake.get_creative_synthesizer.return_value.register_pattern.assert_called_once_with("d", "n", "desc", "sol", ["t"])

    def test_register_pattern_no_body(self):
        r = self.client.post("/api/creative/patterns")
        self.assertEqual(r.status_code, 400)

    def test_insights(self):
        self.fake.get_creative_synthesizer.return_value.get_insights.return_value = [{"i": 1}]
        r = self.client.get("/api/creative/insights?limit=3")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["insights"], [{"i": 1}])
        self.fake.get_creative_synthesizer.return_value.get_insights.assert_called_once_with(3)

    def test_insights_default(self):
        self.fake.get_creative_synthesizer.return_value.get_insights.return_value = []
        r = self.client.get("/api/creative/insights")
        self.fake.get_creative_synthesizer.return_value.get_insights.assert_called_once_with(50)

    def test_find_insights(self):
        self.fake.get_creative_synthesizer.return_value.find_cross_domain_insights.return_value = [{"i": 2}]
        r = self.client.get("/api/creative/find-insights?domain=d")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["insights"], [{"i": 2}])
        self.fake.get_creative_synthesizer.return_value.find_cross_domain_insights.assert_called_once_with("d")

    def test_find_insights_no_domain(self):
        self.fake.get_creative_synthesizer.return_value.find_cross_domain_insights.return_value = []
        r = self.client.get("/api/creative/find-insights")
        self.fake.get_creative_synthesizer.return_value.find_cross_domain_insights.assert_called_once_with(None)

    def test_register_domain_missing_400(self):
        r = self.client.post("/api/creative/domains", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_register_domain_success(self):
        r = self.client.post("/api/creative/domains", json={"domain": "d"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "registered")
        self.assertEqual(r.get_json()["domain"], "d")
        self.fake.get_creative_synthesizer.return_value.register_domain.assert_called_once_with("d")

    def test_register_domain_no_body(self):
        r = self.client.post("/api/creative/domains")
        self.assertEqual(r.status_code, 400)

    def test_stats(self):
        self.fake.get_creative_synthesizer.return_value.get_stats.return_value = {"total": 5}
        r = self.client.get("/api/creative/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_reset(self):
        r = self.client.post("/api/creative/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "reset")
        self.fake.get_creative_synthesizer.return_value.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
