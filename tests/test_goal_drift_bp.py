"""Unit tests for orbit/orbit/core/goal_drift_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.goal_drift_bp import goal_drift_bp


class TestGoalDriftBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(goal_drift_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(goal_drift_bp.name, "goal_drift")

    def test_url_prefix(self):
        self.assertEqual(goal_drift_bp.url_prefix, "/api/goal-drift")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/goal-drift/set", "/api/goal-drift/activity", "/api/goal-drift/report"]:
            self.assertIn(p, rules)

    def test_set_missing_goal_400(self):
        r = self.client.post("/api/goal-drift/set", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_set_success(self):
        with patch("orbit.core.goal_drift_bp.get_goal_drift") as gg:
            gg.return_value.set_goal.return_value = {"id": "g1"}
            r = self.client.post("/api/goal-drift/set", json={"goal": "focus on coding"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["goal"]["id"], "g1")
        gg.return_value.set_goal.assert_called_once_with("focus on coding")

    def test_set_value_error_400(self):
        with patch("orbit.core.goal_drift_bp.get_goal_drift") as gg:
            gg.return_value.set_goal.side_effect = ValueError("bad")
            r = self.client.post("/api/goal-drift/set", json={"goal": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_set_no_body(self):
        r = self.client.post("/api/goal-drift/set")
        self.assertEqual(r.status_code, 400)

    def test_activity_missing_topic_400(self):
        r = self.client.post("/api/goal-drift/activity", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_activity_success(self):
        with patch("orbit.core.goal_drift_bp.get_goal_drift") as gg:
            gg.return_value.record_activity.return_value = 0.75
            r = self.client.post("/api/goal-drift/activity", json={"topic": "coding", "weight": 2.0})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["matched"], 0.75)
        gg.return_value.record_activity.assert_called_once_with("coding", 2.0)

    def test_activity_default_weight(self):
        with patch("orbit.core.goal_drift_bp.get_goal_drift") as gg:
            gg.return_value.record_activity.return_value = 0.5
            r = self.client.post("/api/goal-drift/activity", json={"topic": "coding"})
        gg.return_value.record_activity.assert_called_once_with("coding", 1.0)

    def test_activity_bad_weight(self):
        with patch("orbit.core.goal_drift_bp.get_goal_drift") as gg:
            gg.return_value.record_activity.return_value = 0.5
            r = self.client.post("/api/goal-drift/activity", json={"topic": "coding", "weight": "abc"})
        gg.return_value.record_activity.assert_called_once_with("coding", 1.0)

    def test_activity_no_body(self):
        r = self.client.post("/api/goal-drift/activity")
        self.assertEqual(r.status_code, 400)

    def test_report(self):
        with patch("orbit.core.goal_drift_bp.get_goal_drift") as gg:
            gg.return_value.report.return_value = {"drift": 0.2}
            r = self.client.get("/api/goal-drift/report")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["drift"], 0.2)


if __name__ == "__main__":
    unittest.main()
