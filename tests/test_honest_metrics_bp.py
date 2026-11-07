"""Unit tests for orbit/orbit/core/honest_metrics_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.honest_metrics_bp import honest_metrics_bp


class TestHonestMetricsBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(honest_metrics_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(honest_metrics_bp.name, "honest_metrics_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/metrics/honest", "/api/metrics/honest/scan", "/api/metrics/honest/score"]:
            self.assertIn(p, rules)

    def test_get_metrics(self):
        with patch("orbit.core.honest_metrics_bp.get_honest_metrics") as gm:
            gm.return_value.get_metrics.return_value = {"cpu": 10}
            r = self.client.get("/api/metrics/honest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cpu"], 10)

    def test_scan_now(self):
        with patch("orbit.core.honest_metrics_bp.get_honest_metrics") as gm:
            gm.return_value.scan_now.return_value = {"scanned": True}
            r = self.client.post("/api/metrics/honest/scan")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        self.assertEqual(r.get_json()["metrics"], {"scanned": True})

    def test_get_score(self):
        with patch("orbit.core.honest_metrics_bp.get_honest_metrics") as gm:
            gm.return_value.get_honesty_score.return_value = 85.0
            r = self.client.get("/api/metrics/honest/score")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["score"], 85.0)
        self.assertEqual(body["label"], "85% honest")


if __name__ == "__main__":
    unittest.main()
