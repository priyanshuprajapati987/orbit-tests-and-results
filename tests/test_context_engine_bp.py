"""Unit tests for orbit/orbit/core/context_engine_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.context_engine_bp import context_engine_bp


class TestContextEngineBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(context_engine_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(context_engine_bp.name, "context_engine")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/context-engine/upcoming-meetings", "/api/context-engine/predict",
                  "/api/context-engine/briefings", "/api/context-engine/briefings/generate",
                  "/api/context-engine/briefings/<briefing_id>/dismiss",
                  "/api/context-engine/briefings/<briefing_id>/feedback",
                  "/api/context-engine/predictions", "/api/context-engine/stats",
                  "/api/context-engine/reset"]:
            self.assertIn(p, rules)

    def test_upcoming_meetings(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.get_upcoming_meetings.return_value = [{"id": "m1"}]
            r = self.client.get("/api/context-engine/upcoming-meetings?hours=12")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["meetings"], [{"id": "m1"}])
        ge.return_value.get_upcoming_meetings.assert_called_once_with(hours_ahead=12)

    def test_upcoming_meetings_default(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.get_upcoming_meetings.return_value = []
            r = self.client.get("/api/context-engine/upcoming-meetings")
        ge.return_value.get_upcoming_meetings.assert_called_once_with(hours_ahead=24)

    def test_predict(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.predict_briefing_needs.return_value = [{"p": 1}]
            r = self.client.get("/api/context-engine/predict")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["predictions"], [{"p": 1}])

    def test_list_briefings(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.get_all_briefings.return_value = [{"id": "b1"}]
            r = self.client.get("/api/context-engine/briefings")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["briefings"], [{"id": "b1"}])

    def test_list_briefings_active_only(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.get_active_briefings.return_value = [{"id": "b2"}]
            r = self.client.get("/api/context-engine/briefings?active=true")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["briefings"], [{"id": "b2"}])
        ge.return_value.get_active_briefings.assert_called_once()

    def test_generate_briefing_missing_event_400(self):
        r = self.client.post("/api/context-engine/briefings/generate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_generate_briefing_success(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.generate_briefing.return_value = {"id": "b1"}
            r = self.client.post("/api/context-engine/briefings/generate", json={"event_id": "e1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["briefing"]["id"], "b1")
        ge.return_value.generate_briefing.assert_called_once_with("e1")

    def test_generate_briefing_not_found_404(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.generate_briefing.return_value = None
            r = self.client.post("/api/context-engine/briefings/generate", json={"event_id": "e1"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_generate_briefing_no_body(self):
        r = self.client.post("/api/context-engine/briefings/generate")
        self.assertEqual(r.status_code, 400)

    def test_dismiss_briefing_success(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.dismiss_briefing.return_value = True
            r = self.client.post("/api/context-engine/briefings/b1/dismiss")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "dismissed")
        ge.return_value.dismiss_briefing.assert_called_once_with("b1")

    def test_dismiss_briefing_not_found_404(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.dismiss_briefing.return_value = False
            r = self.client.post("/api/context-engine/briefings/b1/dismiss")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_briefing_feedback(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.record_accuracy_feedback.return_value = True
            r = self.client.post("/api/context-engine/briefings/b1/feedback", json={"correct": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "feedback recorded")
        ge.return_value.record_accuracy_feedback.assert_called_once_with("b1", True)

    def test_briefing_feedback_default(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.record_accuracy_feedback.return_value = True
            r = self.client.post("/api/context-engine/briefings/b1/feedback", json={})
        ge.return_value.record_accuracy_feedback.assert_called_once_with("b1", False)

    def test_briefing_feedback_not_found_404(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.record_accuracy_feedback.return_value = False
            r = self.client.post("/api/context-engine/briefings/b1/feedback", json={"correct": True})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_briefing_feedback_no_body(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.record_accuracy_feedback.return_value = True
            r = self.client.post("/api/context-engine/briefings/b1/feedback")
        ge.return_value.record_accuracy_feedback.assert_called_once_with("b1", False)

    def test_predictions(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.get_predictions.return_value = [{"p": 1}]
            r = self.client.get("/api/context-engine/predictions")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["predictions"], [{"p": 1}])

    def test_stats(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            ge.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/context-engine/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["stats"], {"total": 5})

    def test_reset(self):
        with patch("orbit.core.context_engine_bp.get_context_engine") as ge:
            r = self.client.post("/api/context-engine/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "reset")
        ge.return_value.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
