"""Unit tests for orbit/orbit/core/decision_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.decision_bp import decision_bp


class TestDecisionBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(decision_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(decision_bp.name, "decision")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/decision/analyze", "/api/decision/history", "/api/decision/<decision_id>",
                  "/api/decision/stats", "/api/decision/personalities"]:
            self.assertIn(p, rules)

    def test_analyze_missing_fields_400(self):
        r = self.client.post("/api/decision/analyze", json={"question": "q"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_options_not_list_400(self):
        r = self.client.post("/api/decision/analyze", json={"question": "q", "options": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_options_not_dicts_400(self):
        r = self.client.post("/api/decision/analyze", json={"question": "q", "options": ["a"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_success(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.analyze.return_value = {"winner": "A"}
            r = self.client.post("/api/decision/analyze", json={
                "question": "q", "options": [{"name": "A"}], "category": "work",
                "criteria": ["cost"], "personality": "p"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["winner"], "A")
        gd.return_value.analyze.assert_called_once_with(
            question="q", options=[{"name": "A"}], category="work",
            criteria=["cost"], personality="p"
        )

    def test_analyze_defaults(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.analyze.return_value = {"winner": "B"}
            r = self.client.post("/api/decision/analyze", json={"question": "q", "options": [{"name": "B"}]})
        gd.return_value.analyze.assert_called_once_with(
            question="q", options=[{"name": "B"}], category="personal",
            criteria=None, personality="tony_stark"
        )

    def test_analyze_no_body(self):
        r = self.client.post("/api/decision/analyze")
        self.assertEqual(r.status_code, 400)

    def test_analyze_error(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.analyze.side_effect = RuntimeError("boom")
            r = self.client.post("/api/decision/analyze", json={"question": "q", "options": [{"name": "A"}]})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_history(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.get_history.return_value = [{"id": 1}]
            r = self.client.get("/api/decision/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["decisions"], [{"id": 1}])
        gd.return_value.get_history.assert_called_once_with(5)

    def test_history_default(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.get_history.return_value = []
            r = self.client.get("/api/decision/history")
        gd.return_value.get_history.assert_called_once_with(50)

    def test_history_error(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.get_history.side_effect = RuntimeError("boom")
            r = self.client.get("/api/decision/history")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_detail_found(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.get_decision.return_value = {"id": "d1"}
            r = self.client.get("/api/decision/d1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "d1")
        gd.return_value.get_decision.assert_called_once_with("d1")

    def test_detail_not_found_404(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.get_decision.return_value = None
            r = self.client.get("/api/decision/d1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_detail_error(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.get_decision.side_effect = RuntimeError("boom")
            r = self.client.get("/api/decision/d1")
        self.assertEqual(r.status_code, 500)

    def test_stats(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/decision/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_stats_error(self):
        with patch("orbit.core.decision_bp.get_decision_engine") as gd:
            gd.return_value.get_stats.side_effect = RuntimeError("boom")
            r = self.client.get("/api/decision/stats")
        self.assertEqual(r.status_code, 500)

    def test_personalities(self):
        with patch("orbit.core.decision_bp.PERSONALITY_FILTERS", {"a": 1, "b": 2}):
            r = self.client.get("/api/decision/personalities")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["personalities"], {"a": 1, "b": 2})


if __name__ == "__main__":
    unittest.main()
