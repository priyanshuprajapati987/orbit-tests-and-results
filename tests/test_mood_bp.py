"""Unit tests for orbit/orbit/core/mood_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.mood_bp import mood_bp


class TestMoodBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(mood_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(mood_bp.name, "mood_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/mood/log", "/api/mood/history", "/api/mood/today", "/api/mood/patterns",
                  "/api/mood/weekly", "/api/mood/tone", "/api/mood/status", "/api/mood/adapt",
                  "/api/mood/stats", "/api/mood/force"]:
            self.assertIn(p, rules)

    def test_log(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.log_mood.return_value = {"logged": True}
            r = self.client.post("/api/mood/log", json={"score": 8, "category": "happy", "note": "n", "productivity": 5})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["logged"])
        gm.return_value.log_mood.assert_called_once_with(8, "happy", "n", 5)

    def test_log_defaults(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.log_mood.return_value = {"logged": True}
            r = self.client.post("/api/mood/log", json={})
        gm.return_value.log_mood.assert_called_once_with(5, "happy", "", 0)

    def test_log_no_body(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.log_mood.return_value = {"logged": True}
            r = self.client.post("/api/mood/log")
        gm.return_value.log_mood.assert_called_once_with(5, "happy", "", 0)

    def test_history(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.get_history.return_value = [{"m": 1}]
            r = self.client.get("/api/mood/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"m": 1}])
        gm.return_value.get_history.assert_called_once_with(5)

    def test_history_default(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.get_history.return_value = []
            r = self.client.get("/api/mood/history")
        gm.return_value.get_history.assert_called_once_with(30)

    def test_today_with_mood(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.get_today.return_value = {"score": 7}
            r = self.client.get("/api/mood/today")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["score"], 7)

    def test_today_none(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.get_today.return_value = None
            r = self.client.get("/api/mood/today")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.get_json()["mood"])

    def test_patterns(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.get_patterns.return_value = {"avg": 6}
            r = self.client.get("/api/mood/patterns")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["avg"], 6)

    def test_weekly(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.get_weekly_report.return_value = {"week": 1}
            r = self.client.get("/api/mood/weekly")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["week"], 1)

    def test_tone(self):
        with patch("orbit.core.mood_bp.get_mood_tracker") as gm:
            gm.return_value.get_tone_suggestion.return_value = "cheerful"
            r = self.client.get("/api/mood/tone")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["tone"], "cheerful")

    def test_status(self):
        with patch("orbit.core.mood_detector.get_mood_detector") as gm:
            gm.return_value.get_mood.return_value = {"mood": "happy"}
            r = self.client.get("/api/mood/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["mood"], "happy")

    def test_adapt(self):
        with patch("orbit.core.mood_detector.get_mood_detector") as gm:
            gm.return_value.get_adaptation_rules.return_value = {"rule": "x"}
            r = self.client.get("/api/mood/adapt")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["rule"], "x")

    def test_stats(self):
        with patch("orbit.core.mood_detector.get_mood_detector") as gm:
            gm.return_value.get_stats.return_value = {"count": 5}
            r = self.client.get("/api/mood/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 5)

    def test_force_missing_mood_400(self):
        r = self.client.post("/api/mood/force", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_force_success(self):
        with patch("orbit.core.mood_detector.get_mood_detector") as gm:
            gm.return_value.get_mood.return_value = {"mood": "sad"}
            r = self.client.post("/api/mood/force", json={"mood": "sad", "energy": "low"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["mood"], "sad")
        gm.return_value.force_mood.assert_called_once_with("sad", "low")

    def test_force_default_energy(self):
        with patch("orbit.core.mood_detector.get_mood_detector") as gm:
            gm.return_value.get_mood.return_value = {"mood": "happy"}
            r = self.client.post("/api/mood/force", json={"mood": "happy"})
        gm.return_value.force_mood.assert_called_once_with("happy", "")

    def test_force_no_body(self):
        r = self.client.post("/api/mood/force")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
