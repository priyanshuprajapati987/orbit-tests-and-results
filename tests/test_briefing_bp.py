"""Unit tests for orbit/orbit/core/briefing_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.briefing_bp import briefing_bp


class TestBriefingBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(briefing_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(briefing_bp.name, "briefing")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/briefing/today", "/api/briefing/generate", "/api/briefing/history"]:
            self.assertIn(p, rules)

    def test_today_empty(self):
        with patch("orbit.core.briefing_bp.get_briefing_agent") as gb:
            gb.return_value.get_today.return_value = None
            r = self.client.get("/api/briefing/today")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "empty")

    def test_today_ok(self):
        with patch("orbit.core.briefing_bp.get_briefing_agent") as gb:
            gb.return_value.get_today.return_value = {"date": "2026-01-01"}
            r = self.client.get("/api/briefing/today")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["briefing"]["date"], "2026-01-01")

    def test_generate(self):
        with patch("orbit.core.briefing_bp.get_briefing_agent") as gb:
            gb.return_value.generate_briefing.return_value = {"date": "2026-01-01"}
            r = self.client.post("/api/briefing/generate")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

    def test_history(self):
        with patch("orbit.core.briefing_bp.get_briefing_agent") as gb:
            gb.return_value.get_history.return_value = [{"d": 1}, {"d": 2}]
            r = self.client.get("/api/briefing/history")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["briefings"]), 2)


if __name__ == "__main__":
    unittest.main()
