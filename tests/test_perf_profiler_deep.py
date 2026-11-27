"""Deep tests for orbit/orbit/core/perf_profiler.py (Loop 19/3)."""

import json
import threading
import time
import unittest
from collections import deque
from pathlib import Path
from unittest import mock

from orbit.orbit.core import perf_profiler as pp


class PerfSampleStatsTests(unittest.TestCase):
    def test_perf_sample_defaults(self):
        s = pp.PerfSample(component="c", component_type="agent",
                          operation="run", latency_ms=10.0, success=True)
        self.assertEqual(s.tokens_in, 0)
        self.assertEqual(s.tokens_out, 0)
        self.assertIsNone(s.error)
        self.assertIsInstance(s.timestamp, float)
        self.assertEqual(s.metadata, {})

    def test_perf_stats_avg_with_count(self):
        s = pp.PerfStats(count=4, total_ms=100)
        self.assertEqual(s.avg_ms, 25.0)

    def test_perf_stats_avg_zero_count(self):
        s = pp.PerfStats(count=0, total_ms=0)
        self.assertEqual(s.avg_ms, 0.0)

    def test_perf_stats_success_rate(self):
        s = pp.PerfStats(count=4, success_count=3)
        self.assertEqual(s.success_rate, 75.0)

    def test_perf_stats_success_rate_zero(self):
        s = pp.PerfStats(count=0)
        self.assertEqual(s.success_rate, 0.0)

    def test_perf_stats_min_ms_inf(self):
        s = pp.PerfStats()
        self.assertEqual(s.min_ms, float("inf"))


class InitLoadSaveTests(unittest.TestCase):
    def test_init_creates_data_dir(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        with mock.patch("pathlib.Path.mkdir") as mk:
            p = pp.PerformanceProfiler(data_dir=d)
        mk.assert_called_once_with(parents=True, exist_ok=True)
        self.assertTrue(hasattr(p, "_lock"))

    def test_load_existing(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        stats_file = d / "stats.json"
        stats_file.write_text(json.dumps({
            "agents": {"a": {"count": 2, "total_ms": 10, "min_ms": 3,
                             "max_ms": 7, "success_count": 2, "fail_count": 0,
                             "errors": []}},
            "tools": {"t": {"count": 1, "total_ms": 5, "min_ms": 5,
                            "max_ms": 5, "success_count": 1, "fail_count": 0,
                            "errors": []}},
            "queries": {"q": {"count": 3, "total_ms": 30, "min_ms": 8,
                              "max_ms": 12, "success_count": 2, "fail_count": 1,
                              "errors": ["err"]}},
        }), encoding="utf-8")
        p = pp.PerformanceProfiler(data_dir=d)
        self.assertEqual(p._agent_stats["a"].count, 2)
        self.assertEqual(p._tool_stats["t"].count, 1)
        self.assertEqual(p._query_stats["q"].count, 3)
        self.assertEqual(p._query_stats["q"].errors, ["err"])

    def test_load_corrupt_ignored(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        (d / "stats.json").write_text("{bad", encoding="utf-8")
        p = pp.PerformanceProfiler(data_dir=d)
        self.assertEqual(len(p._agent_stats), 0)

    def test_load_missing(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        p = pp.PerformanceProfiler(data_dir=d)
        self.assertEqual(len(p._agent_stats), 0)

    def test_save_success(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        p = pp.PerformanceProfiler(data_dir=d)
        p.record_agent("a", 10.0, True)
        # save called during record; verify file exists
        self.assertTrue((d / "stats.json").exists())

    def test_save_failure_logged(self):
        p = pp.PerformanceProfiler.__new__(pp.PerformanceProfiler)
        p._data_dir = Path("/tmp/x")
        p._lock = threading.RLock()
        p._agent_stats = {}
        p._tool_stats = {}
        p._query_stats = {}
        with mock.patch.object(Path, "with_name", side_effect=OSError("boom")), \
                mock.patch.object(pp, "logger") as lg:
            p._save()
        lg.warning.assert_called_once()


class RecordTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return pp.PerformanceProfiler(data_dir=d)

    def test_record_agent(self):
        p = self._make()
        p.record("a", "agent", "run", 50.0, True, tokens_in=10, tokens_out=5,
                 error=None, metadata={"k": "v"})
        self.assertEqual(len(p._recent_samples), 1)
        s = p._recent_samples[0]
        self.assertEqual(s.component, "a")
        self.assertEqual(s.component_type, "agent")
        self.assertEqual(s.operation, "run")
        self.assertEqual(s.latency_ms, 50.0)
        self.assertTrue(s.success)
        self.assertEqual(s.tokens_in, 10)
        self.assertEqual(s.tokens_out, 5)
        self.assertEqual(s.metadata, {"k": "v"})
        # agent stats updated
        self.assertEqual(p._agent_stats["a"].count, 1)
        self.assertEqual(p._agent_stats["a"].total_ms, 50.0)
        self.assertEqual(p._agent_stats["a"].min_ms, 50.0)
        self.assertEqual(p._agent_stats["a"].max_ms, 50.0)
        self.assertEqual(p._agent_stats["a"].success_count, 1)
        self.assertEqual(p._agent_stats["a"].fail_count, 0)

    def test_record_tool(self):
        p = self._make()
        p.record("t", "tool", "exec", 20.0, False, error="err")
        self.assertEqual(p._tool_stats["t"].count, 1)
        self.assertEqual(p._tool_stats["t"].fail_count, 1)
        self.assertEqual(p._tool_stats["t"].errors, ["err"])

    def test_record_query(self):
        p = self._make()
        p.record("q", "query", "process", 30.0, True)
        self.assertEqual(p._query_stats["q"].count, 1)

    def test_record_system(self):
        p = self._make()
        p.record("sys", "system", "op", 10.0, True)
        self.assertIn("system:sys", p._agent_stats)

    def test_record_error_cap_10(self):
        p = self._make()
        for i in range(12):
            p.record("t", "tool", "exec", 10.0, False, error=f"err{i}")
        self.assertEqual(len(p._tool_stats["t"].errors), 10)

    def test_record_error_none_not_appended(self):
        p = self._make()
        p.record("t", "tool", "exec", 10.0, False, error=None)
        self.assertEqual(p._tool_stats["t"].errors, [])

    def test_record_error_empty_not_appended(self):
        p = self._make()
        p.record("t", "tool", "exec", 10.0, False, error="")
        self.assertEqual(p._tool_stats["t"].errors, [])

    def test_record_min_max(self):
        p = self._make()
        p.record("a", "agent", "run", 10.0, True)
        p.record("a", "agent", "run", 5.0, True)
        p.record("a", "agent", "run", 20.0, True)
        s = p._agent_stats["a"]
        self.assertEqual(s.min_ms, 5.0)
        self.assertEqual(s.max_ms, 20.0)
        self.assertEqual(s.total_ms, 35.0)

    def test_time_series_new_bucket(self):
        p = self._make()
        with mock.patch("time.time", return_value=1000.0):
            p.record("a", "agent", "run", 10.0, True)
        self.assertEqual(len(p._time_series), 1)
        b = p._time_series[0]
        self.assertEqual(b["count"], 1)
        self.assertEqual(b["total_ms"], 10.0)
        self.assertEqual(b["success"], 1)

    def test_time_series_existing_bucket(self):
        p = self._make()
        with mock.patch("time.time", return_value=1000.0):
            p.record("a", "agent", "run", 10.0, True)
            p.record("b", "agent", "run", 20.0, False)
        self.assertEqual(len(p._time_series), 1)
        b = p._time_series[0]
        self.assertEqual(b["count"], 2)
        self.assertEqual(b["total_ms"], 30.0)
        self.assertEqual(b["success"], 1)

    def test_record_agent(self):
        p = self._make()
        p.record_agent("agent1", 50.0, True, error="e")
        self.assertEqual(p._agent_stats["agent1"].count, 1)
        self.assertEqual(p._agent_stats["agent1"].errors, [])

    def test_record_tool(self):
        p = self._make()
        p.record_tool("tool1", 20.0, False)
        self.assertEqual(p._tool_stats["tool1"].count, 1)

    def test_record_query(self):
        p = self._make()
        p.record_query("q1", 30.0, True)
        self.assertEqual(p._query_stats["q1"].count, 1)


class PercentilesTests(unittest.TestCase):
    def test_empty(self):
        p = pp.PerformanceProfiler.__new__(pp.PerformanceProfiler)
        self.assertEqual(p._compute_percentiles([]), {"p50": 0, "p95": 0, "p99": 0})

    def test_single(self):
        p = pp.PerformanceProfiler.__new__(pp.PerformanceProfiler)
        r = p._compute_percentiles([10.0])
        self.assertEqual(r["p50"], 10.0)
        self.assertEqual(r["p95"], 10.0)
        self.assertEqual(r["p99"], 10.0)

    def test_multiple(self):
        p = pp.PerformanceProfiler.__new__(pp.PerformanceProfiler)
        r = p._compute_percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(r["p50"], 6.0)
        self.assertGreaterEqual(r["p95"], 9.0)
        self.assertGreaterEqual(r["p99"], 9.0)


class DetectBottlenecksTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return pp.PerformanceProfiler(data_dir=d)

    def test_none(self):
        p = self._make()
        self.assertEqual(p.detect_bottlenecks(), [])

    def test_bottleneck_found(self):
        p = self._make()
        # need >5 calls and avg > threshold
        for i in range(6):
            p.record("slow", "agent", "run", 3000.0, True)
        bn = p.detect_bottlenecks(threshold_ms=2000)
        self.assertEqual(len(bn), 1)
        self.assertEqual(bn[0]["component"], "slow")
        self.assertEqual(bn[0]["kind"], "agent")
        self.assertEqual(bn[0]["avg_ms"], 3000.0)
        self.assertEqual(bn[0]["max_ms"], 3000.0)
        self.assertEqual(bn[0]["count"], 6)
        self.assertEqual(bn[0]["success_rate"], 100.0)

    def test_below_threshold_excluded(self):
        p = self._make()
        for i in range(6):
            p.record("fast", "agent", "run", 100.0, True)
        self.assertEqual(p.detect_bottlenecks(threshold_ms=2000), [])

    def test_fewer_than_5_calls_excluded(self):
        p = self._make()
        for i in range(5):
            p.record("slow", "agent", "run", 3000.0, True)
        self.assertEqual(p.detect_bottlenecks(threshold_ms=2000), [])

    def test_tool_bottleneck(self):
        p = self._make()
        for i in range(6):
            p.record("slowtool", "tool", "exec", 3000.0, True)
        bn = p.detect_bottlenecks(threshold_ms=2000)
        self.assertEqual(bn[0]["kind"], "tool")

    def test_sorted_desc(self):
        p = self._make()
        for i in range(6):
            p.record("a", "agent", "run", 3000.0, True)
            p.record("b", "agent", "run", 5000.0, True)
        bn = p.detect_bottlenecks(threshold_ms=2000)
        self.assertEqual(bn[0]["component"], "b")

    def test_custom_threshold(self):
        p = self._make()
        for i in range(6):
            p.record("x", "agent", "run", 1500.0, True)
        self.assertEqual(len(p.detect_bottlenecks(threshold_ms=1000)), 1)
        self.assertEqual(len(p.detect_bottlenecks(threshold_ms=2000)), 0)


class DetectRegressionsTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return pp.PerformanceProfiler(data_dir=d)

    def test_no_regressions(self):
        p = self._make()
        self.assertEqual(p.detect_regressions(), [])

    def test_regression_detected(self):
        p = self._make()
        now = time.time()
        # older samples (60-120 min ago): fast
        for i in range(5):
            s = pp.PerfSample(component="c", component_type="agent",
                              operation="run", latency_ms=100.0, success=True,
                              timestamp=now - 90 * 60)
            p._recent_samples.append(s)
        # recent samples (< 60 min ago): slow (4x degradation)
        for i in range(5):
            s = pp.PerfSample(component="c", component_type="agent",
                              operation="run", latency_ms=500.0, success=True,
                              timestamp=now - 10 * 60)
            p._recent_samples.append(s)
        regs = p.detect_regressions(window=60)
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["component"], "c")
        self.assertEqual(regs[0]["recent_avg_ms"], 500.0)
        self.assertEqual(regs[0]["older_avg_ms"], 100.0)
        self.assertEqual(regs[0]["degradation_pct"], 400.0)

    def test_fewer_than_3_older_no_regression(self):
        p = self._make()
        now = time.time()
        for i in range(2):
            s = pp.PerfSample(component="c", component_type="agent",
                              operation="run", latency_ms=100.0, success=True,
                              timestamp=now - 90 * 60)
            p._recent_samples.append(s)
        for i in range(5):
            s = pp.PerfSample(component="c", component_type="agent",
                              operation="run", latency_ms=500.0, success=True,
                              timestamp=now - 10 * 60)
            p._recent_samples.append(s)
        self.assertEqual(p.detect_regressions(), [])

    def test_degradation_below_30_pct_no_regression(self):
        p = self._make()
        now = time.time()
        for i in range(5):
            s = pp.PerfSample(component="c", component_type="agent",
                              operation="run", latency_ms=100.0, success=True,
                              timestamp=now - 90 * 60)
            p._recent_samples.append(s)
        for i in range(5):
            s = pp.PerfSample(component="c", component_type="agent",
                              operation="run", latency_ms=110.0, success=True,
                              timestamp=now - 10 * 60)
            p._recent_samples.append(s)
        self.assertEqual(p.detect_regressions(), [])

    def test_zero_older_avg_no_regression(self):
        p = self._make()
        now = time.time()
        for i in range(5):
            s = pp.PerfSample(component="c", component_type="agent",
                              operation="run", latency_ms=0.0, success=True,
                              timestamp=now - 90 * 60)
            p._recent_samples.append(s)
        for i in range(5):
            s = pp.PerfSample(component="c", component_type="agent",
                              operation="run", latency_ms=500.0, success=True,
                              timestamp=now - 10 * 60)
            p._recent_samples.append(s)
        self.assertEqual(p.detect_regressions(), [])


class GetStatsTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return pp.PerformanceProfiler(data_dir=d)

    def test_agent_stats_empty(self):
        p = self._make()
        self.assertEqual(p.get_agent_stats(), {})

    def test_agent_stats_populated(self):
        p = self._make()
        p.record("a", "agent", "run", 100.0, True)
        p.record("a", "agent", "run", 200.0, False, error="e")
        stats = p.get_agent_stats()
        self.assertIn("a", stats)
        self.assertEqual(stats["a"]["count"], 2)
        self.assertEqual(stats["a"]["avg_ms"], 150.0)
        self.assertEqual(stats["a"]["min_ms"], 100.0)
        self.assertEqual(stats["a"]["max_ms"], 200.0)
        self.assertEqual(stats["a"]["success_rate"], 50.0)
        self.assertEqual(stats["a"]["fail_count"], 1)

    def test_agent_stats_min_ms_inf_becomes_0(self):
        # PerfStats with count 0 won't appear; but min_ms inf handling:
        p = self._make()
        p.record("a", "agent", "run", 10.0, True)
        # manually set min_ms to inf to test the branch
        p._agent_stats["a"].min_ms = float("inf")
        stats = p.get_agent_stats()
        self.assertEqual(stats["a"]["min_ms"], 0)

    def test_tool_stats(self):
        p = self._make()
        p.record("t", "tool", "exec", 50.0, True)
        p.record("t", "tool", "exec", 60.0, False)
        stats = p.get_tool_stats()
        self.assertIn("t", stats)
        self.assertEqual(stats["t"]["count"], 2)
        self.assertEqual(stats["t"]["avg_ms"], 55.0)
        self.assertEqual(stats["t"]["success_rate"], 50.0)
        self.assertEqual(stats["t"]["fail_count"], 1)

    def test_query_stats(self):
        p = self._make()
        p.record("q", "query", "process", 30.0, True)
        p.record("q", "query", "process", 40.0, True)
        stats = p.get_query_stats()
        self.assertIn("q", stats)
        self.assertEqual(stats["q"]["count"], 2)
        self.assertEqual(stats["q"]["avg_ms"], 35.0)
        self.assertEqual(stats["q"]["success_rate"], 100.0)

    def test_sorting_by_avg_desc(self):
        p = self._make()
        p.record("a", "agent", "run", 100.0, True)
        p.record("b", "agent", "run", 200.0, True)
        stats = p.get_agent_stats()
        keys = list(stats.keys())
        self.assertEqual(keys[0], "b")

    def test_query_sorting_by_count_desc(self):
        p = self._make()
        p.record("a", "query", "process", 10.0, True)
        p.record("b", "query", "process", 10.0, True)
        p.record("b", "query", "process", 10.0, True)
        stats = p.get_query_stats()
        keys = list(stats.keys())
        self.assertEqual(keys[0], "b")


class GetTimeSeriesTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return pp.PerformanceProfiler(data_dir=d)

    def test_empty(self):
        p = self._make()
        self.assertEqual(p.get_time_series(), [])

    def test_with_data(self):
        p = self._make()
        with mock.patch("time.time", return_value=1000.0):
            p.record("a", "agent", "run", 100.0, True)
            p.record("a", "agent", "run", 200.0, False)
        with mock.patch("time.time", return_value=1000.0):
            ts = p.get_time_series(minutes=60)
        self.assertEqual(len(ts), 1)
        self.assertEqual(ts[0]["count"], 2)
        self.assertEqual(ts[0]["avg_ms"], 150.0)
        self.assertEqual(ts[0]["success_rate"], 50.0)

    def test_cutoff_filters_old(self):
        p = self._make()
        # bucket far in the past
        with mock.patch("time.time", return_value=1000.0):
            p.record("a", "agent", "run", 10.0, True)
        # now time is much later
        with mock.patch("time.time", return_value=1000.0 + 3600 * 2):
            ts = p.get_time_series(minutes=60)
        self.assertEqual(ts, [])

    def test_custom_minutes(self):
        p = self._make()
        with mock.patch("time.time", return_value=1000.0):
            p.record("a", "agent", "run", 10.0, True)
        with mock.patch("time.time", return_value=1000.0):
            ts = p.get_time_series(minutes=1)
        self.assertEqual(len(ts), 1)


class GetDashboardTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return pp.PerformanceProfiler(data_dir=d)

    def test_empty(self):
        p = self._make()
        d = p.get_dashboard()
        self.assertIn("timestamp", d)
        self.assertEqual(d["total_samples"], 0)
        self.assertEqual(d["overall_latency"], {"p50": 0, "p95": 0, "p99": 0})
        self.assertEqual(d["overall_success_rate"], 0.0)  # 0 / max(1,0) * 100 = 0
        self.assertEqual(d["agents"], {})
        self.assertEqual(d["tools"], {})
        self.assertEqual(d["queries"], {})
        self.assertEqual(d["bottlenecks"], [])
        self.assertEqual(d["regressions"], [])

    def test_with_samples(self):
        p = self._make()
        p.record("a", "agent", "run", 100.0, True)
        p.record("a", "agent", "run", 200.0, False)
        d = p.get_dashboard()
        self.assertEqual(d["total_samples"], 2)
        self.assertEqual(d["overall_success_rate"], 50.0)
        self.assertIn("a", d["agents"])


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = pp._profiler
        pp._profiler = None
        self.addCleanup(setattr, pp, "_profiler", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.perf_profiler.PerformanceProfiler",
                        wraps=pp.PerformanceProfiler) as C:
            # can't easily inject data_dir; just call default (creates orbit_data/perf_profiler)
            pass
        a = pp.get_profiler()
        self.assertIsInstance(a, pp.PerformanceProfiler)
        self.assertIs(pp._profiler, a)

    def test_reuses(self):
        a = pp.get_profiler()
        b = pp.get_profiler()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
