"""Unit tests for orbit/orbit/core/reasoning_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.reasoning_bp import reasoning_bp


class TestReasoningBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(reasoning_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(reasoning_bp.name, "reasoning")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/reasoning/solve", "/api/reasoning/traces", "/api/reasoning/trace/<trace_id>",
                  "/api/reasoning/stats", "/api/reasoning/complexity"]:
            self.assertIn(p, rules)

    def test_solve_missing_task_400(self):
        r = self.client.post("/api/reasoning/solve", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_solve_success(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.solve.return_value = {"answer": "42"}
            r = self.client.post("/api/reasoning/solve", json={"task": "q", "strategy": "deep"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["answer"], "42")
        gre.return_value.solve.assert_called_once_with("q", "deep")

    def test_solve_no_strategy(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.solve.return_value = {"answer": "x"}
            r = self.client.post("/api/reasoning/solve", json={"task": "q"})
        gre.return_value.solve.assert_called_once_with("q", None)

    def test_solve_no_body(self):
        r = self.client.post("/api/reasoning/solve")
        self.assertEqual(r.status_code, 400)

    def test_solve_error(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.solve.side_effect = RuntimeError("boom")
            r = self.client.post("/api/reasoning/solve", json={"task": "q"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_traces(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.get_traces.return_value = [{"id": "t1"}]
            r = self.client.get("/api/reasoning/traces?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["traces"], [{"id": "t1"}])
        gre.return_value.get_traces.assert_called_once_with(5)

    def test_traces_default(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.get_traces.return_value = []
            r = self.client.get("/api/reasoning/traces")
        gre.return_value.get_traces.assert_called_once_with(50)

    def test_traces_error(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.get_traces.side_effect = RuntimeError("boom")
            r = self.client.get("/api/reasoning/traces")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_trace_found(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.get_trace.return_value = {"id": "t1"}
            r = self.client.get("/api/reasoning/trace/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "t1")

    def test_trace_not_found_404(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.get_trace.return_value = None
            r = self.client.get("/api/reasoning/trace/t1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_trace_error(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.get_trace.side_effect = RuntimeError("boom")
            r = self.client.get("/api/reasoning/trace/t1")
        self.assertEqual(r.status_code, 500)

    def test_stats(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/reasoning/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_stats_error(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.get_stats.side_effect = RuntimeError("boom")
            r = self.client.get("/api/reasoning/stats")
        self.assertEqual(r.status_code, 500)

    def test_complexity(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.detect_complexity.return_value = "high"
            gre.return_value.select_strategy.return_value = "deep"
            r = self.client.post("/api/reasoning/complexity", json={"task": "solve x"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["complexity"], "high")
        self.assertEqual(body["strategy"], "deep")
        gre.return_value.detect_complexity.assert_called_once_with("solve x")
        gre.return_value.select_strategy.assert_called_once_with("high")

    def test_complexity_missing_task_400(self):
        r = self.client.post("/api/reasoning/complexity", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_complexity_no_body(self):
        r = self.client.post("/api/reasoning/complexity")
        self.assertEqual(r.status_code, 400)

    def test_complexity_error(self):
        with patch("orbit.core.reasoning_bp.get_reasoning_engine") as gre:
            gre.return_value.detect_complexity.side_effect = RuntimeError("boom")
            r = self.client.post("/api/reasoning/complexity", json={"task": "x"})
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
