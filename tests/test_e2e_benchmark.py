"""Unit tests for orbit/orbit/core/e2e_benchmark.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.e2e_benchmark as e2b
from orbit.core.e2e_benchmark import (
    TaskCategory,
    TaskStatus,
    E2ETask,
    TaskResult,
    BenchmarkResult,
    E2E_TASKS,
    E2EBenchmark,
    get_e2e_benchmark,
)


def make_task(task_id="custom-01", category=TaskCategory.REASONING, **kw):
    defaults = dict(
        name="Task",
        description="Desc",
        category=category,
        input_prompt="prompt",
        expected_behavior="behavior",
        validation_criteria=["c1"],
    )
    defaults.update(kw)
    return E2ETask(task_id=task_id, **defaults)


def make_result(task_id, status=TaskStatus.PASSED, **kw):
    defaults = dict(
        response="ok",
        latency_ms=1.0,
        agent_used="agent",
        tools_used=["tool"],
        memory_accessed=True,
        error_recovery_attempted=False,
        error_recovery_succeeded=False,
        validation_passed=True,
        validation_details={"c1": True},
    )
    defaults.update(kw)
    return TaskResult(task_id=task_id, status=status, **defaults)


class E2EBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        self.bench = E2EBenchmark(data_dir=self.data_dir)

    def write_results(self, payload):
        (self.data_dir / "results.json").write_text(
            json.dumps(payload), encoding="utf-8")


class TestEnums(unittest.TestCase):
    def test_task_categories(self):
        vals = [c.value for c in TaskCategory]
        self.assertEqual(len(vals), 10)
        self.assertIn("reasoning", vals)
        self.assertIn("security", vals)
        self.assertIn("memory_recall", vals)

    def test_task_statuses(self):
        vals = [s.value for s in TaskStatus]
        self.assertEqual(vals, ["pending", "running", "passed",
                                "failed", "timeout", "error"])


class TestDataclasses(unittest.TestCase):
    def test_task_defaults(self):
        t = make_task()
        self.assertEqual(t.timeout_seconds, 120)
        self.assertEqual(t.max_retries, 1)
        self.assertEqual(t.tags, [])
        self.assertEqual(t.depends_on, [])

    def test_task_custom_fields(self):
        t = make_task(timeout_seconds=30, max_retries=3,
                      tags=["fast"], depends_on=["reason-01"])
        self.assertEqual(t.timeout_seconds, 30)
        self.assertEqual(t.max_retries, 3)
        self.assertEqual(t.tags, ["fast"])

    def test_result_default_timestamp_and_error(self):
        r = make_result("x")
        # isoformat parseable
        from datetime import datetime
        datetime.fromisoformat(r.timestamp)
        self.assertIsNone(r.error)

    def test_result_explicit_error(self):
        r = make_result("x", status=TaskStatus.ERROR, error="boom")
        self.assertEqual(r.error, "boom")

    def test_benchmark_defaults(self):
        b = BenchmarkResult(benchmark_id="b1", start_time="t0")
        self.assertIsNone(b.end_time)
        self.assertEqual(b.total_tasks, 0)
        self.assertEqual(b.passed, 0)
        self.assertEqual(b.failed, 0)
        self.assertEqual(b.timeout, 0)
        self.assertEqual(b.error, 0)
        self.assertEqual(b.avg_latency_ms, 0.0)
        self.assertEqual(b.category_results, {})
        self.assertEqual(b.task_results, [])
        self.assertEqual(b.summary, "")


class TestTaskSuite(unittest.TestCase):
    def test_thirty_tasks(self):
        self.assertEqual(len(E2E_TASKS), 30)

    def test_unique_ids(self):
        ids = [t.task_id for t in E2E_TASKS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_three_per_category(self):
        for cat in TaskCategory:
            n = sum(1 for t in E2E_TASKS if t.category == cat)
            self.assertEqual(n, 3, f"{cat} has {n} tasks")

    def test_id_prefixes(self):
        prefixes = {
            TaskCategory.REASONING: "reason-",
            TaskCategory.MULTI_AGENT: "multi-",
            TaskCategory.BROWSER_RESEARCH: "browser-",
            TaskCategory.CODING: "code-",
            TaskCategory.EMAIL_CALENDAR: "email-",
            TaskCategory.MEMORY_RECALL: "memory-",
            TaskCategory.FAILURE_RECOVERY: "recovery-",
            TaskCategory.LONG_RUNNING: "long-",
            TaskCategory.AMBIGUOUS: "ambiguous-",
            TaskCategory.SECURITY: "security-",
        }
        for t in E2E_TASKS:
            self.assertTrue(
                t.task_id.startswith(prefixes[t.category]),
                f"{t.task_id} prefix mismatch for {t.category}")

    def test_all_have_criteria_and_positive_timeout(self):
        for t in E2E_TASKS:
            self.assertTrue(t.validation_criteria, t.task_id)
            self.assertGreater(t.timeout_seconds, 0, t.task_id)
            self.assertTrue(t.input_prompt, t.task_id)


class TestInitLoad(E2EBase):
    def test_creates_missing_dir(self):
        nested = self.data_dir / "a" / "b"
        b = E2EBenchmark(data_dir=nested)
        self.assertTrue(nested.is_dir())
        self.assertEqual(b._results, [])

    def test_no_results_file(self):
        self.assertEqual(self.bench._results, [])

    def test_loads_valid_results(self):
        self.write_results({"results": [
            {"benchmark_id": "bm-1", "start_time": "t0",
             "end_time": "t1", "total_tasks": 4, "passed": 3,
             "failed": 1, "timeout": 0, "error": 0,
             "avg_latency_ms": 12.5,
             "category_results": {"coding": {"total": 1}},
             "summary": "s"}]})
        b = E2EBenchmark(data_dir=self.data_dir)
        self.assertEqual(len(b._results), 1)
        r = b._results[0]
        self.assertIsInstance(r, BenchmarkResult)
        self.assertEqual(r.benchmark_id, "bm-1")
        self.assertEqual(r.passed, 3)
        # task_results not persisted -> default empty
        self.assertEqual(r.task_results, [])

    def test_missing_results_key(self):
        self.write_results({"other": []})
        b = E2EBenchmark(data_dir=self.data_dir)
        self.assertEqual(b._results, [])

    def test_invalid_json_resets(self):
        (self.data_dir / "results.json").write_text(
            "{not json", encoding="utf-8")
        b = E2EBenchmark(data_dir=self.data_dir)
        self.assertEqual(b._results, [])

    def test_unknown_field_resets(self):
        self.write_results({"results": [
            {"benchmark_id": "x", "start_time": "t", "bogus": 1}]})
        b = E2EBenchmark(data_dir=self.data_dir)
        self.assertEqual(b._results, [])


class TestSave(E2EBase):
    def _benchmark(self):
        return BenchmarkResult(
            benchmark_id="bm-9", start_time="t0", end_time="t1",
            total_tasks=2, passed=2, failed=0, timeout=0, error=0,
            avg_latency_ms=5.0,
            category_results={"reasoning": {"total": 2, "passed": 2,
                                            "failed": 0,
                                            "pass_rate": 100.0}},
            summary="s")

    def test_save_round_trip(self):
        self.bench._results.append(self._benchmark())
        self.bench._save()
        raw = json.loads(
            (self.data_dir / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(len(raw["results"]), 1)
        self.assertEqual(raw["results"][0]["benchmark_id"], "bm-9")
        self.assertEqual(raw["results"][0]["category_results"],
                         {"reasoning": {"total": 2, "passed": 2,
                                        "failed": 0, "pass_rate": 100.0}})
        self.assertNotIn("task_results", raw["results"][0])

    def test_save_uses_atomic_tmp_replace(self):
        self.bench._results.append(self._benchmark())
        self.bench._save()
        # tmp file replaced -> no leftover .tmp
        self.assertFalse(
            (self.data_dir / "results.json.tmp").exists())

    def test_save_failure_logs_warning(self):
        # pre-create a DIRECTORY at the tmp path -> write_text fails
        (self.data_dir / "results.json.tmp").mkdir()
        self.bench._results.append(self._benchmark())
        with self.assertLogs("orbit.core.e2e_benchmark",
                             level="WARNING") as cm:
            self.bench._save()
        self.assertIn("Failed to save E2E benchmark results",
                      cm.output[0])

    def test_save_failure_does_not_raise(self):
        (self.data_dir / "results.json.tmp").mkdir()
        self.bench._results.append(self._benchmark())
        self.bench._save()  # must not raise


class TestGetTasks(E2EBase):
    def test_default_returns_all(self):
        tasks = self.bench.get_tasks()
        self.assertEqual(len(tasks), 30)

    def test_category_filter(self):
        tasks = self.bench.get_tasks(category=TaskCategory.CODING)
        self.assertEqual(len(tasks), 3)
        self.assertTrue(all(t.category == TaskCategory.CODING
                            for t in tasks))

    def test_all_categories_filter_to_three(self):
        for cat in TaskCategory:
            self.assertEqual(len(self.bench.get_tasks(category=cat)), 3)

    def test_tags_filter_empty_suite(self):
        # no E2E_TASK defines tags -> tag filters match nothing
        self.assertEqual(self.bench.get_tasks(tags=["fast"]), [])

    def test_limit(self):
        tasks = self.bench.get_tasks(limit=5)
        self.assertEqual(len(tasks), 5)
        self.assertEqual(tasks[0].task_id, E2E_TASKS[0].task_id)

    def test_limit_none_returns_all(self):
        self.assertEqual(len(self.bench.get_tasks(limit=None)), 30)

    def test_limit_zero_returns_empty(self):
        # regression: `if limit:` used to treat 0 as "no limit"
        self.assertEqual(self.bench.get_tasks(limit=0), [])

    def test_limit_negative_returns_empty(self):
        self.assertEqual(self.bench.get_tasks(limit=-3), [])

    def test_category_and_limit_combined(self):
        tasks = self.bench.get_tasks(category=TaskCategory.SECURITY,
                                     limit=2)
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(t.category == TaskCategory.SECURITY
                            for t in tasks))

    def test_limit_larger_than_pool(self):
        self.assertEqual(len(self.bench.get_tasks(limit=999)), 30)


class TestGetTaskById(E2EBase):
    def test_found(self):
        t = self.bench.get_task_by_id("reason-01")
        self.assertIsNotNone(t)
        self.assertEqual(t.category, TaskCategory.REASONING)

    def test_not_found(self):
        self.assertIsNone(self.bench.get_task_by_id("nope"))


class TestRunSingleTask(E2EBase):
    def test_success_overwrites_latency(self):
        task = make_task()
        sentinel = make_result(task.task_id, latency_ms=999999.0)

        def runner(t):
            return sentinel

        out = self.bench.run_single_task(task, runner)
        self.assertIs(out, sentinel)
        self.assertGreaterEqual(out.latency_ms, 0.0)
        self.assertLess(out.latency_ms, 999999.0)

    def test_success_logs_completion(self):
        task = make_task("reason-01")
        with self.assertLogs("orbit.core.e2e_benchmark",
                             level="INFO") as cm:
            self.bench.run_single_task(
                task, lambda t: make_result(t.task_id))
        joined = "\n".join(cm.output)
        self.assertIn("Running task reason-01", joined)
        self.assertIn("completed", joined)
        self.assertIn("passed", joined)

    def test_exception_returns_error_result(self):
        task = make_task()

        def boom(t):
            raise RuntimeError("runner exploded")

        with self.assertLogs("orbit.core.e2e_benchmark",
                             level="ERROR") as cm:
            out = self.bench.run_single_task(task, boom)
        self.assertIn("runner exploded", cm.output[0])
        self.assertEqual(out.status, TaskStatus.ERROR)
        self.assertEqual(out.task_id, task.task_id)
        self.assertEqual(out.response, "")
        self.assertEqual(out.agent_used, "none")
        self.assertEqual(out.tools_used, [])
        self.assertFalse(out.validation_passed)
        self.assertEqual(out.error, "runner exploded")
        self.assertGreaterEqual(out.latency_ms, 0.0)

    def test_exception_still_returns_result_not_raise(self):
        out = self.bench.run_single_task(
            make_task(), lambda t: 1 / 0)
        self.assertEqual(out.status, TaskStatus.ERROR)
        self.assertIn("division by zero", out.error)


class RunHelpers:
    """Shared runner factory: PASSED by default, per-task override."""

    @staticmethod
    def runner(overrides=None, record=None):
        overrides = overrides or {}

        def fn(task):
            if record is not None:
                record.append(task.task_id)
            status = overrides.get(task.task_id, TaskStatus.PASSED)
            return make_result(
                task.task_id, status=status,
                error="e" if status == TaskStatus.ERROR else None,
                validation_passed=(status == TaskStatus.PASSED))

        return fn


class TestRunBenchmark(E2EBase):
    def test_sequential_counts(self):
        tasks = [make_task("reason-01"), make_task(
            "code-01", category=TaskCategory.CODING)]
        overrides = {"code-01": TaskStatus.FAILED}
        bm = self.bench.run_benchmark(
            RunHelpers.runner(overrides), tasks)
        self.assertEqual(bm.total_tasks, 2)
        self.assertEqual(bm.passed, 1)
        self.assertEqual(bm.failed, 1)
        self.assertEqual(bm.timeout, 0)
        self.assertEqual(bm.error, 0)
        self.assertGreaterEqual(bm.avg_latency_ms, 0.0)
        self.assertIsNotNone(bm.end_time)

    def test_all_four_statuses_counted(self):
        tasks = [make_task("reason-01"),
                 make_task("code-01", category=TaskCategory.CODING),
                 make_task("multi-01",
                           category=TaskCategory.MULTI_AGENT),
                 make_task("browser-01",
                           category=TaskCategory.BROWSER_RESEARCH)]
        overrides = {"reason-01": TaskStatus.PASSED,
                     "code-01": TaskStatus.FAILED,
                     "multi-01": TaskStatus.TIMEOUT,
                     "browser-01": TaskStatus.ERROR}
        bm = self.bench.run_benchmark(
            RunHelpers.runner(overrides), tasks)
        self.assertEqual(bm.passed, 1)
        self.assertEqual(bm.failed, 1)
        self.assertEqual(bm.timeout, 1)
        self.assertEqual(bm.error, 1)

    def test_benchmark_id_shape(self):
        bm = self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        self.assertEqual(len(bm.benchmark_id), 12)
        self.assertTrue(all(c in "0123456789abcdef"
                            for c in bm.benchmark_id))

    def test_summary_format(self):
        bm = self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        self.assertIn(f"E2E Benchmark {bm.benchmark_id}:", bm.summary)
        self.assertIn("1/1 passed (100.0%)", bm.summary)
        self.assertIn("avg latency", bm.summary)
        self.assertIn("0 failed, 0 timeout, 0 errors", bm.summary)

    def test_category_results_for_known_tasks(self):
        tasks = [make_task("reason-01"), make_task("reason-02")]
        bm = self.bench.run_benchmark(RunHelpers.runner(), tasks)
        self.assertEqual(bm.category_results["reasoning"], {
            "total": 2, "passed": 2, "failed": 0, "pass_rate": 100.0})

    def test_category_results_partial_pass(self):
        tasks = [make_task("reason-01"),
                 make_task("code-01", category=TaskCategory.CODING)]
        overrides = {"code-01": TaskStatus.FAILED}
        bm = self.bench.run_benchmark(
            RunHelpers.runner(overrides), tasks)
        self.assertEqual(bm.category_results["reasoning"]["pass_rate"],
                         100.0)
        self.assertEqual(bm.category_results["coding"], {
            "total": 1, "passed": 0, "failed": 1, "pass_rate": 0.0})

    def test_unknown_task_id_excluded_from_categories(self):
        # task not present in E2E_TASKS -> _get_task None -> excluded
        bm = self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("ghost-99")])
        self.assertEqual(bm.total_tasks, 1)
        self.assertEqual(bm.category_results, {})

    def test_concurrent_runs_all(self):
        record = []
        tasks = [make_task("reason-01"),
                 make_task("code-01", category=TaskCategory.CODING),
                 make_task("multi-01",
                           category=TaskCategory.MULTI_AGENT)]
        bm = self.bench.run_benchmark(
            RunHelpers.runner(record=record), tasks,
            max_concurrent=3)
        self.assertEqual(bm.total_tasks, 3)
        self.assertEqual(bm.passed, 3)
        self.assertEqual(sorted(record),
                         ["code-01", "multi-01", "reason-01"])

    def test_concurrent_mixed_statuses(self):
        tasks = [make_task("reason-01"),
                 make_task("code-01", category=TaskCategory.CODING)]
        overrides = {"reason-01": TaskStatus.PASSED,
                     "code-01": TaskStatus.ERROR}
        bm = self.bench.run_benchmark(
            RunHelpers.runner(overrides), tasks, max_concurrent=2)
        self.assertEqual(bm.passed, 1)
        self.assertEqual(bm.error, 1)

    def test_appends_to_history_and_get_latest(self):
        bm = self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        self.assertIs(self.bench.get_latest(), bm)
        self.assertEqual(len(self.bench.get_history()), 1)

    def test_persists_to_disk(self):
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        raw = json.loads(
            (self.data_dir / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(len(raw["results"]), 1)

    def test_default_suite_when_tasks_none(self):
        bm = self.bench.run_benchmark(RunHelpers.runner(), None)
        self.assertEqual(bm.total_tasks, 30)
        self.assertEqual(len(bm.category_results), 10)

    def test_explicit_empty_list_runs_nothing(self):
        # regression: `tasks or E2E_TASKS` used to run all 30 tasks
        bm = self.bench.run_benchmark(RunHelpers.runner(), [])
        self.assertEqual(bm.total_tasks, 0)
        self.assertEqual(bm.passed, 0)
        self.assertEqual(bm.category_results, {})
        self.assertIn("0/0 passed (0.0%)", bm.summary)
        self.assertEqual(bm.avg_latency_ms, 0.0)

    def test_empty_run_still_recorded(self):
        self.bench.run_benchmark(RunHelpers.runner(), [])
        self.assertEqual(len(self.bench.get_history()), 1)
        self.assertEqual(self.bench.get_latest().total_tasks, 0)

    def test_runner_exception_becomes_error_result(self):
        def boom(t):
            raise ValueError("kaput")

        bm = self.bench.run_benchmark(boom, [make_task("reason-01")])
        self.assertEqual(bm.error, 1)
        self.assertEqual(bm.task_results[0].error, "kaput")

    def test_task_results_attached(self):
        tasks = [make_task("reason-01")]
        bm = self.bench.run_benchmark(RunHelpers.runner(), tasks)
        self.assertEqual(len(bm.task_results), 1)
        self.assertEqual(bm.task_results[0].task_id, "reason-01")

    def test_multiple_runs_accumulate(self):
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-02")])
        self.assertEqual(len(self.bench._results), 2)


class TestGetLatestHistoryStats(E2EBase):
    def test_latest_empty_none(self):
        self.assertIsNone(self.bench.get_latest())

    def test_history_empty(self):
        self.assertEqual(self.bench.get_history(), [])

    def test_stats_empty(self):
        self.assertEqual(self.bench.get_stats(),
                         {"total_benchmarks": 0})

    def test_history_limit(self):
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-02")])
        hist = self.bench.get_history(limit=1)
        self.assertEqual(len(hist), 1)
        # chronological: last run kept
        self.assertEqual(len(self.bench.get_history(limit=10)), 2)

    def test_history_entry_shape(self):
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        entry = self.bench.get_history()[0]
        self.assertEqual(set(entry.keys()), {
            "benchmark_id", "start_time", "end_time", "total_tasks",
            "passed", "failed", "pass_rate", "avg_latency_ms"})
        self.assertEqual(entry["pass_rate"], 100.0)

    def test_history_pass_rate_partial(self):
        tasks = [make_task("reason-01"),
                 make_task("code-01", category=TaskCategory.CODING)]
        overrides = {"code-01": TaskStatus.FAILED}
        self.bench.run_benchmark(
            RunHelpers.runner(overrides), tasks)
        entry = self.bench.get_history()[0]
        self.assertEqual(entry["pass_rate"], 50.0)

    def test_history_limit_zero_returns_empty(self):
        # regression: `self._results[-0:]` is a FULL slice
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        self.assertEqual(self.bench.get_history(limit=0), [])

    def test_history_negative_limit_returns_empty(self):
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])
        self.assertEqual(self.bench.get_history(limit=-1), [])

    def test_stats_after_run(self):
        tasks = [make_task("reason-01"),
                 make_task("code-01", category=TaskCategory.CODING)]
        overrides = {"code-01": TaskStatus.FAILED}
        self.bench.run_benchmark(
            RunHelpers.runner(overrides), tasks)
        stats = self.bench.get_stats()
        self.assertEqual(stats["total_benchmarks"], 1)
        self.assertEqual(stats["avg_pass_rate"], 50.0)
        self.assertEqual(stats["total_tasks_run"], 2)
        self.assertEqual(stats["total_passed"], 1)
        self.assertIn("E2E Benchmark", stats["latest"])

    def test_stats_average_across_runs(self):
        self.bench.run_benchmark(
            RunHelpers.runner(), [make_task("reason-01")])  # 100%
        tasks = [make_task("reason-01"),
                 make_task("code-01", category=TaskCategory.CODING)]
        overrides = {"code-01": TaskStatus.FAILED}
        self.bench.run_benchmark(
            RunHelpers.runner(overrides), tasks)  # 50%
        stats = self.bench.get_stats()
        self.assertEqual(stats["total_benchmarks"], 2)
        self.assertEqual(stats["avg_pass_rate"], 75.0)
        self.assertEqual(stats["total_tasks_run"], 3)
        self.assertEqual(stats["total_passed"], 2)

    def test_stats_zero_task_run_guard(self):
        # total_tasks=0 -> max(1, ...) guard prevents ZeroDivision
        self.bench.run_benchmark(RunHelpers.runner(), [])
        stats = self.bench.get_stats()
        self.assertEqual(stats["total_benchmarks"], 1)
        self.assertEqual(stats["avg_pass_rate"], 0.0)


class TestSingleton(unittest.TestCase):
    def test_same_instance(self):
        self.assertIs(get_e2e_benchmark(), get_e2e_benchmark())

    def test_is_benchmark_instance(self):
        with tempfile.TemporaryDirectory() as td:
            inst = E2EBenchmark(data_dir=Path(td))
            with patch.object(e2b, "_e2e_benchmark", None), \
                 patch.object(e2b, "E2EBenchmark",
                              return_value=inst) as ctor:
                m1 = get_e2e_benchmark()
                self.assertIs(m1, inst)
                self.assertIs(get_e2e_benchmark(), m1)
                ctor.assert_called_once()

    def test_returns_cached_without_recreating(self):
        cached = object()
        with patch.object(e2b, "_e2e_benchmark", cached):
            self.assertIs(get_e2e_benchmark(), cached)


if __name__ == "__main__":
    unittest.main()
