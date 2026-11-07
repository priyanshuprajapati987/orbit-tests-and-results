"""Unit tests for orbit/orbit/core/realtime_learning_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.realtime_learning_bp import learning_bp


class TestRealtimeLearningBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(learning_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(learning_bp.name, "realtime_learning")

    def test_url_prefix(self):
        self.assertEqual(learning_bp.url_prefix, "/api/learning")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/learning/status", "/api/learning/feedback", "/api/learning/suggest", "/api/learning/reset"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.realtime_learning_bp.get_realtime_learner") as gl:
            gl.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/learning/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_feedback_invalid_json(self):
        r = self.client.post("/api/learning/feedback", data="not json", content_type="text/plain")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["success"])

    def test_feedback_success(self):
        with patch("orbit.core.realtime_learning_bp.get_realtime_learner") as gl:
            gl.return_value.record_feedback.return_value = {"recorded": True}
            r = self.client.post("/api/learning/feedback", json={"query": "q", "response": "r", "rating": 0.8, "context": {"k": "v"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["recorded"], True)
        gl.return_value.record_feedback.assert_called_once_with("q", "r", 0.8, {"k": "v"})

    def test_feedback_rating_clamped(self):
        with patch("orbit.core.realtime_learning_bp.get_realtime_learner") as gl:
            gl.return_value.record_feedback.return_value = {"recorded": True}
            r = self.client.post("/api/learning/feedback", json={"query": "q", "response": "r", "rating": 5.0})
        gl.return_value.record_feedback.assert_called_once_with("q", "r", 1.0, {})

    def test_feedback_rating_bad(self):
        with patch("orbit.core.realtime_learning_bp.get_realtime_learner") as gl:
            gl.return_value.record_feedback.return_value = {"recorded": True}
            r = self.client.post("/api/learning/feedback", json={"query": "q", "response": "r", "rating": "abc"})
        gl.return_value.record_feedback.assert_called_once_with("q", "r", 0.5, {})

    def test_feedback_context_non_dict(self):
        with patch("orbit.core.realtime_learning_bp.get_realtime_learner") as gl:
            gl.return_value.record_feedback.return_value = {"recorded": True}
            r = self.client.post("/api/learning/feedback", json={"query": "q", "response": "r", "context": "str"})
        gl.return_value.record_feedback.assert_called_once_with("q", "r", 0.5, {})

    def test_feedback_no_body(self):
        r = self.client.post("/api/learning/feedback")
        self.assertEqual(r.status_code, 400)

    def test_suggest(self):
        with patch("orbit.core.realtime_learning_bp.get_realtime_learner") as gl:
            gl.return_value.get_adaptation_suggestion.return_value = "sug"
            r = self.client.get("/api/learning/suggest?q=hello")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["suggestion"], "sug")
        gl.return_value.get_adaptation_suggestion.assert_called_once_with("hello")

    def test_suggest_default(self):
        with patch("orbit.core.realtime_learning_bp.get_realtime_learner") as gl:
            gl.return_value.get_adaptation_suggestion.return_value = None
            r = self.client.get("/api/learning/suggest")
        gl.return_value.get_adaptation_suggestion.assert_called_once_with("")

    def test_reset(self):
        with patch("orbit.core.realtime_learning_bp.get_realtime_learner") as gl:
            r = self.client.post("/api/learning/reset")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        gl.return_value.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
