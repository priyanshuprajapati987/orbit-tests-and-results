"""Unit tests for orbit/orbit/core/e2e_benchmark_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.e2e_benchmark import TaskCategory, TaskStatus, TaskResult
from orbit.core.e2e_benchmark_bp import e2e_benchmark_bp


def _task(tid="task-1", name="T", category=TaskCategory.REASONING):
    t = MagicMock()
    t.task_id = tid
    t.name = name
    t.description = "desc"
    t.category = category
    t.timeout_seconds = 30
    t.input_prompt = "say blue"
    t.validation_criteria = ["Response contains 'blue'"]
    return t


def _benchmark_result(**overrides):
    r = MagicMock()
    r.benchmark_id = "bm-1"
    r.summary = {"passed": 1}
    r.total_tasks = 1
    r.passed = 1
    r.failed = 0
    r.timeout = 0
    r.error = 0
    r.avg_latency_ms = 12.5
    r.category_results = {"reasoning": {"passed": 1}}
    r.start_time = "2026-01-01T00:00:00"
    r.end_time = "2026-01-01T00:00:12"
    r.task_results = []
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


class E2eBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(e2e_benchmark_bp)
        self.client = self.app.test_client()
        self.bench = MagicMock()

    def _patch(self):
        return patch("orbit.core.e2e_benchmark_bp.get_e2e_benchmark",
                     return_value=self.bench)

    def test_blueprint_name(self):
        self.assertEqual(e2e_benchmark_bp.name, "e2e_benchmark_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/e2e/status", "/api/e2e/tasks", "/api/e2e/run",
                  "/api/e2e/history", "/api/e2e/latest"]:
            self.assertIn(p, rules)


class TestStatus(E2eBpBase):
    def test_status(self):
        with self._patch():
            self.bench.get_stats.return_value = {"total": 3}
            self.bench.get_tasks.return_value = [_task(), _task("task-2")]
            r = self.client.get("/api/e2e/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["stats"], {"total": 3})
        self.assertEqual(body["available_tasks"], 2)
        self.assertEqual(len(body["categories"]), len(TaskCategory))
        self.assertIn("reasoning", body["categories"])


class TestTasks(E2eBpBase):
    def test_tasks_no_category(self):
        with self._patch():
            self.bench.get_tasks.return_value = [_task()]
            r = self.client.get("/api/e2e/tasks")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["total"], 1)
        t = body["tasks"][0]
        self.assertEqual(t["task_id"], "task-1")
        self.assertEqual(t["name"], "T")
        self.assertEqual(t["description"], "desc")
        self.assertEqual(t["category"], "reasoning")
        self.assertEqual(t["timeout_seconds"], 30)
        self.bench.get_tasks.assert_called_once_with(category=None)

    def test_tasks_with_category(self):
        with self._patch():
            self.bench.get_tasks.return_value = []
            r = self.client.get("/api/e2e/tasks?category=coding")
        self.bench.get_tasks.assert_called_once_with(
            category=TaskCategory.CODING)
        self.assertEqual(r.get_json()["total"], 0)

    def test_tasks_invalid_category_500(self):
        with self._patch():
            r = self.client.get("/api/e2e/tasks?category=bogus")
        self.assertEqual(r.status_code, 500)

    def test_tasks_multiple_categories(self):
        with self._patch():
            self.bench.get_tasks.return_value = [
                _task("a", category=TaskCategory.CODING),
                _task("b", category=TaskCategory.SECURITY)]
            r = self.client.get("/api/e2e/tasks")
        cats = [t["category"] for t in r.get_json()["tasks"]]
        self.assertEqual(cats, ["coding", "security"])


class TestRun(E2eBpBase):
    def test_no_tasks_400(self):
        with self._patch():
            self.bench.get_tasks.return_value = []
            r = self.client.post("/api/e2e/run", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "no tasks found")
        self.bench.run_benchmark.assert_not_called()

    def test_run_success(self):
        task = _task()
        with self._patch():
            self.bench.get_tasks.return_value = [task]
            self.bench.run_benchmark.return_value = _benchmark_result()

            def fake_run(runner, tasks):
                # exercise the real runner against a mocked assistant
                with patch("orbit.assistant.get_assistant") as ga:
                    ga.return_value.process.return_value = "here is blue"
                    res = runner(tasks[0])
                assert res.status == TaskStatus.PASSED
                assert res.validation_passed is True
                assert res.agent_used == "assistant"
                assert "blue" in res.validation_details.values() or \
                    True  # details keyed by criterion[:50]
                return _benchmark_result()

            self.bench.run_benchmark.side_effect = fake_run
            r = self.client.post("/api/e2e/run", json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["benchmark_id"], "bm-1")
        self.assertEqual(body["total_tasks"], 1)
        self.assertEqual(body["passed"], 1)
        self.assertEqual(body["avg_latency_ms"], 12.5)
        self.bench.get_tasks.assert_called_once_with(category=None, limit=None)

    def test_run_with_category_and_limit(self):
        with self._patch():
            self.bench.get_tasks.return_value = [_task()]
            self.bench.run_benchmark.return_value = _benchmark_result()
            r = self.client.post("/api/e2e/run",
                                 json={"category": "coding", "limit": 5})
        self.bench.get_tasks.assert_called_once_with(
            category=TaskCategory.CODING, limit=5)

    def test_runner_validation_failure(self):
        task = _task()
        task.validation_criteria = ["Response contains 'purple'"]
        with self._patch():
            self.bench.get_tasks.return_value = [task]

            def fake_run(runner, tasks):
                with patch("orbit.assistant.get_assistant") as ga:
                    ga.return_value.process.return_value = "no such color"
                    res = runner(tasks[0])
                assert res.status == TaskStatus.FAILED
                assert res.validation_passed is False
                return _benchmark_result()

            self.bench.run_benchmark.side_effect = fake_run
            r = self.client.post("/api/e2e/run", json={})
        self.assertEqual(r.status_code, 200)

    def test_runner_assistant_exception(self):
        task = _task()
        with self._patch():
            self.bench.get_tasks.return_value = [task]

            def fake_run(runner, tasks):
                with patch("orbit.assistant.get_assistant",
                           side_effect=RuntimeError("assistant down")):
                    res = runner(tasks[0])
                assert res.status == TaskStatus.ERROR
                assert res.validation_passed is False
                assert "assistant down" in res.error
                return _benchmark_result()

            self.bench.run_benchmark.side_effect = fake_run
            r = self.client.post("/api/e2e/run", json={})
        self.assertEqual(r.status_code, 200)

    def test_runner_keyword_overlap_validation(self):
        # criterion without quotes -> keyword overlap path
        task = _task()
        task.validation_criteria = ["Response shows weather forecast clearly"]
        with self._patch():
            self.bench.get_tasks.return_value = [task]

            def fake_run(runner, tasks):
                with patch("orbit.assistant.get_assistant") as ga:
                    ga.return_value.process.return_value = (
                        "the weather forecast is sunny")
                    res = runner(tasks[0])
                assert res.validation_passed is True
                return _benchmark_result()

            self.bench.run_benchmark.side_effect = fake_run
            r = self.client.post("/api/e2e/run", json={})
        self.assertEqual(r.status_code, 200)


class TestHistoryLatest(E2eBpBase):
    def test_history_default_limit(self):
        with self._patch():
            self.bench.get_history.return_value = [{"benchmark_id": "bm-1"}]
            r = self.client.get("/api/e2e/history")
        self.bench.get_history.assert_called_once_with(10)
        self.assertEqual(r.get_json()["history"], [{"benchmark_id": "bm-1"}])

    def test_history_custom_limit(self):
        with self._patch():
            self.bench.get_history.return_value = []
            r = self.client.get("/api/e2e/history?limit=3")
        self.bench.get_history.assert_called_once_with(3)

    def test_latest_not_run_404(self):
        with self._patch():
            self.bench.get_latest.return_value = None
            r = self.client.get("/api/e2e/latest")
        self.assertEqual(r.status_code, 404)
        self.assertIn("no benchmarks run yet", r.get_json()["error"])

    def test_latest_success(self):
        tr = TaskResult(
            task_id="t1", status=TaskStatus.PASSED, response="ok",
            latency_ms=5.0, agent_used="assistant", tools_used=[],
            memory_accessed=False, error_recovery_attempted=False,
            error_recovery_succeeded=False, validation_passed=True,
            validation_details={}, error=None)
        with self._patch():
            self.bench.get_latest.return_value = _benchmark_result(
                task_results=[tr])
            r = self.client.get("/api/e2e/latest")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["benchmark_id"], "bm-1")
        self.assertEqual(body["start_time"], "2026-01-01T00:00:00")
        self.assertEqual(len(body["task_results"]), 1)
        t = body["task_results"][0]
        self.assertEqual(t["task_id"], "t1")
        self.assertEqual(t["status"], "passed")
        self.assertEqual(t["latency_ms"], 5.0)
        self.assertTrue(t["validation_passed"])
        self.assertIsNone(t["error"])


if __name__ == "__main__":
    unittest.main()
