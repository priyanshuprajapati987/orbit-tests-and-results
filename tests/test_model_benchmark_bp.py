"""Unit tests for orbit/orbit/core/model_benchmark_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.model_benchmark_bp import model_benchmark_bp


class TestModelBenchmarkBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(model_benchmark_bp)
        self.client = self.app.test_client()
        self.fake_mb = MagicMock()
        sys.modules["orbit.orbit.core.model_benchmark"] = self.fake_mb

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.model_benchmark", None)

    def test_blueprint_name(self):
        self.assertEqual(model_benchmark_bp.name, "model_benchmark")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/benchmark/tasks", "/api/benchmark/run", "/api/benchmark/record",
                  "/api/benchmark/leaderboard", "/api/model-benchmark/compare",
                  "/api/model-benchmark/results", "/api/model-benchmark/stats"]:
            self.assertIn(p, rules)

    def test_add_task_missing_400(self):
        r = self.client.post("/api/benchmark/tasks", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_task_missing_prompt_400(self):
        r = self.client.post("/api/benchmark/tasks", json={"name": "t"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_task_success(self):
        task = MagicMock()
        task.task_id = "t1"
        task.name = "task1"
        self.fake_mb.get_model_benchmark.return_value.add_task.return_value = task
        r = self.client.post("/api/benchmark/tasks", json={
            "name": "task1", "prompt": "p", "expected_keywords": ["k"], "category": "code", "max_tokens": 100
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["task_id"], "t1")
        self.assertEqual(r.get_json()["name"], "task1")
        self.fake_mb.get_model_benchmark.return_value.add_task.assert_called_once_with("task1", "p", ["k"], "code", 100)

    def test_add_task_defaults(self):
        task = MagicMock()
        task.task_id = "t2"
        task.name = "task2"
        self.fake_mb.get_model_benchmark.return_value.add_task.return_value = task
        r = self.client.post("/api/benchmark/tasks", json={"name": "task2", "prompt": "p"})
        self.fake_mb.get_model_benchmark.return_value.add_task.assert_called_once_with("task2", "p", None, "general", 200)

    def test_add_task_no_body(self):
        r = self.client.post("/api/benchmark/tasks")
        self.assertEqual(r.status_code, 400)

    def test_list_tasks(self):
        self.fake_mb.get_model_benchmark.return_value.get_tasks.return_value = [{"id": "t1"}]
        r = self.client.get("/api/benchmark/tasks")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["tasks"], [{"id": "t1"}])

    def test_run_missing_fields_400(self):
        r = self.client.post("/api/benchmark/run", json={"task_id": "t1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_run_success(self):
        self.fake_mb.get_model_benchmark.return_value.run_benchmark.return_value = {"results": []}
        r = self.client.post("/api/benchmark/run", json={"task_id": "t1", "providers": ["openai"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [])
        self.fake_mb.get_model_benchmark.return_value.run_benchmark.assert_called_once_with("t1", ["openai"])

    def test_run_no_body(self):
        r = self.client.post("/api/benchmark/run")
        self.assertEqual(r.status_code, 400)

    def test_record_missing_fields_400(self):
        r = self.client.post("/api/benchmark/record", json={"task_id": "t1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_success(self):
        result = MagicMock()
        result.result_id = "r1"
        result.overall_score = 0.9
        self.fake_mb.get_model_benchmark.return_value.record_result.return_value = result
        r = self.client.post("/api/benchmark/record", json={
            "task_id": "t1", "provider": "openai", "model": "gpt-4",
            "response": "hi", "latency_ms": 10, "tokens_used": 5, "error": "e"
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result_id"], "r1")
        self.assertEqual(r.get_json()["score"], 0.9)
        self.fake_mb.get_model_benchmark.return_value.record_result.assert_called_once_with(
            "t1", "openai", "gpt-4", "hi", 10, 5, "e"
        )

    def test_record_defaults(self):
        result = MagicMock()
        result.result_id = "r2"
        result.overall_score = 0.5
        self.fake_mb.get_model_benchmark.return_value.record_result.return_value = result
        r = self.client.post("/api/benchmark/record", json={
            "task_id": "t1", "provider": "openai", "model": "gpt-4", "response": "hi"
        })
        self.fake_mb.get_model_benchmark.return_value.record_result.assert_called_once_with(
            "t1", "openai", "gpt-4", "hi", 0, 0, ""
        )

    def test_record_no_body(self):
        r = self.client.post("/api/benchmark/record")
        self.assertEqual(r.status_code, 400)

    def test_leaderboard(self):
        self.fake_mb.get_model_benchmark.return_value.get_leaderboard.return_value = [{"rank": 1}]
        r = self.client.get("/api/benchmark/leaderboard")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["leaderboard"], [{"rank": 1}])

    def test_compare_missing_params_400(self):
        r = self.client.get("/api/model-benchmark/compare")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_compare_success(self):
        self.fake_mb.get_model_benchmark.return_value.compare_providers.return_value = {"winner": "a"}
        r = self.client.get("/api/model-benchmark/compare?a=openai&b=anthropic")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["winner"], "a")
        self.fake_mb.get_model_benchmark.return_value.compare_providers.assert_called_once_with("openai", "anthropic")

    def test_results(self):
        self.fake_mb.get_model_benchmark.return_value.get_results.return_value = [{"id": "r1"}]
        r = self.client.get("/api/model-benchmark/results?task_id=t1&provider=openai&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [{"id": "r1"}])
        self.fake_mb.get_model_benchmark.return_value.get_results.assert_called_once_with("t1", "openai", 5)

    def test_results_defaults(self):
        self.fake_mb.get_model_benchmark.return_value.get_results.return_value = []
        r = self.client.get("/api/model-benchmark/results")
        self.fake_mb.get_model_benchmark.return_value.get_results.assert_called_once_with(None, None, 50)

    def test_stats(self):
        self.fake_mb.get_model_benchmark.return_value.get_stats.return_value = {"total": 3}
        r = self.client.get("/api/model-benchmark/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 3)


if __name__ == "__main__":
    unittest.main()
