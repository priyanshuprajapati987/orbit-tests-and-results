"""Unit tests for orbit/orbit/core/daily_digest_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.daily_digest_bp import daily_digest_bp


class TestDailyDigestBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(daily_digest_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(daily_digest_bp.name, "daily_digest")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/digest/generate", "/api/digest/today", "/api/digest/history"]:
            self.assertIn(p, rules)

    def test_generate(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.generate_digest.return_value = {"digest": "today"}
            r = self.client.post("/api/digest/generate")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["digest"], "today")

    def test_generate_error(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.generate_digest.side_effect = RuntimeError("boom")
            r = self.client.post("/api/digest/generate")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_today_ok(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.get_today_digest.return_value = {"digest": "today"}
            r = self.client.get("/api/digest/today")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["digest"], "today")

    def test_today_empty_404(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.get_today_digest.return_value = None
            r = self.client.get("/api/digest/today")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_today_error(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.get_today_digest.side_effect = RuntimeError("boom")
            r = self.client.get("/api/digest/today")
        self.assertEqual(r.status_code, 500)

    def test_history(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.get_history.return_value = [{"d": 1}, {"d": 2}]
            r = self.client.get("/api/digest/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"d": 1}, {"d": 2}])
        gd.return_value.get_history.assert_called_once_with(limit=5)

    def test_history_default(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.get_history.return_value = []
            r = self.client.get("/api/digest/history")
        gd.return_value.get_history.assert_called_once_with(limit=7)

    def test_history_clamped(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.get_history.return_value = []
            r = self.client.get("/api/digest/history?limit=200")
        gd.return_value.get_history.assert_called_once_with(limit=100)

    def test_history_error(self):
        with patch("orbit.core.daily_digest_bp.get_daily_digest") as gd:
            gd.return_value.get_history.side_effect = RuntimeError("boom")
            r = self.client.get("/api/digest/history")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
