"""Unit tests for orbit/orbit/core/response_evaluator_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.response_evaluator_bp import response_evaluator_bp


class TestResponseEvaluatorBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(response_evaluator_bp)
        self.client = self.app.test_client()
        self.fake_re = MagicMock()
        sys.modules["orbit.orbit.core.response_evaluator"] = self.fake_re

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.response_evaluator", None)

    def test_blueprint_name(self):
        self.assertEqual(response_evaluator_bp.name, "response_evaluator")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/evaluator/evaluate", "/api/evaluator/recent", "/api/evaluator/lowest",
                  "/api/evaluator/agent/<agent_id>", "/api/evaluator/stats"]:
            self.assertIn(p, rules)

    def test_evaluate_missing_fields_400(self):
        r = self.client.post("/api/evaluator/evaluate", json={"query": "q"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_evaluate_success(self):
        ev = MagicMock()
        ev.eval_id = "e1"
        ev.scores = {"acc": 0.9}
        ev.overall_score = 0.9
        ev.flags = []
        self.fake_re.get_response_evaluator.return_value.evaluate.return_value = ev
        r = self.client.post("/api/evaluator/evaluate", json={"query": "q", "response": "r", "context": "c", "agent_id": "a1"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["eval_id"], "e1")
        self.assertEqual(body["overall_score"], 0.9)
        self.fake_re.get_response_evaluator.return_value.evaluate.assert_called_once_with("q", "r", context="c", agent_id="a1")

    def test_evaluate_defaults(self):
        ev = MagicMock()
        ev.eval_id = "e2"
        ev.scores = {}
        ev.overall_score = 0.5
        ev.flags = []
        self.fake_re.get_response_evaluator.return_value.evaluate.return_value = ev
        r = self.client.post("/api/evaluator/evaluate", json={"query": "q", "response": "r"})
        self.fake_re.get_response_evaluator.return_value.evaluate.assert_called_once_with("q", "r", context="", agent_id="")

    def test_evaluate_no_body(self):
        r = self.client.post("/api/evaluator/evaluate")
        self.assertEqual(r.status_code, 400)

    def test_recent(self):
        self.fake_re.get_response_evaluator.return_value.get_recent.return_value = [{"id": "e1"}]
        r = self.client.get("/api/evaluator/recent?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [{"id": "e1"}])
        self.fake_re.get_response_evaluator.return_value.get_recent.assert_called_once_with(5)

    def test_recent_default(self):
        self.fake_re.get_response_evaluator.return_value.get_recent.return_value = []
        r = self.client.get("/api/evaluator/recent")
        self.fake_re.get_response_evaluator.return_value.get_recent.assert_called_once_with(20)

    def test_lowest(self):
        self.fake_re.get_response_evaluator.return_value.get_lowest.return_value = [{"id": "e2"}]
        r = self.client.get("/api/evaluator/lowest?limit=3")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [{"id": "e2"}])
        self.fake_re.get_response_evaluator.return_value.get_lowest.assert_called_once_with(3)

    def test_lowest_default(self):
        self.fake_re.get_response_evaluator.return_value.get_lowest.return_value = []
        r = self.client.get("/api/evaluator/lowest")
        self.fake_re.get_response_evaluator.return_value.get_lowest.assert_called_once_with(10)

    def test_agent_stats(self):
        self.fake_re.get_response_evaluator.return_value.get_agent_stats.return_value = {"agent": "a1", "score": 0.8}
        r = self.client.get("/api/evaluator/agent/a1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["agent"], "a1")

    def test_stats(self):
        self.fake_re.get_response_evaluator.return_value.get_stats.return_value = {"total": 5}
        r = self.client.get("/api/evaluator/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
