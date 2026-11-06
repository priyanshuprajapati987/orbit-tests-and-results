"""Unit tests for orbit/orbit/core/performance_metrics.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.performance_metrics import (
    MetricType, PerformanceMetrics, get_performance_metrics,
    record_task, get_agent_stats, get_overall_stats, get_leaderboard, get_cost_breakdown,
)


class TestMetricType(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(MetricType.COUNTER, "counter")
        self.assertEqual(MetricType.GAUGE, "gauge")
        self.assertEqual(MetricType.HISTOGRAM, "histogram")


class TestPerformanceMetrics(unittest.TestCase):
    def setUp(self):
        self.pm = PerformanceMetrics()

    def test_instantiation(self):
        self.assertIsNotNone(self.pm)

    def test_record_task(self):
        self.pm.record_task("agent1", "code", True, 100, tokens_used=50, cost_usd=0.001)
        self.assertTrue(True)

    def test_increment_counter(self):
        self.pm.increment_counter("hits")
        self.pm.increment_counter("hits", 5)
        self.assertTrue(True)

    def test_set_gauge(self):
        self.pm.set_gauge("cpu", 0.5)
        self.assertTrue(True)

    def test_record_histogram(self):
        self.pm.record_histogram("latency", 12.5)
        self.assertTrue(True)

    def test_get_agent_stats(self):
        self.pm.record_task("agent1", "code", True, 100)
        r = self.pm.get_agent_stats("agent1")
        self.assertIsNotNone(r)

    def test_get_task_stats(self):
        self.pm.record_task("agent1", "code", True, 100)
        r = self.pm.get_task_stats("code")
        self.assertIsNotNone(r)

    def test_get_overall_stats(self):
        r = self.pm.get_overall_stats()
        self.assertIsNotNone(r)

    def test_get_leaderboard(self):
        self.pm.record_task("agent1", "code", True, 100)
        r = self.pm.get_leaderboard()
        self.assertIsNotNone(r)

    def test_get_recent_activity(self):
        self.pm.record_task("agent1", "code", True, 100)
        r = self.pm.get_recent_activity(5)
        self.assertIsNotNone(r)

    def test_get_cost_breakdown(self):
        self.pm.record_task("agent1", "code", True, 100, cost_usd=0.001)
        r = self.pm.get_cost_breakdown()
        self.assertIsNotNone(r)

    def test_get_hourly_stats(self):
        r = self.pm.get_hourly_stats()
        self.assertIsNotNone(r)

    def test_reset_metrics(self):
        self.pm.record_task("agent1", "code", True, 100)
        self.pm.reset_metrics()
        self.assertTrue(True)

    def test_singleton(self):
        a = get_performance_metrics()
        b = get_performance_metrics()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_record_task_func(self):
        self.assertTrue(callable(record_task))

    def test_get_agent_stats_func(self):
        self.assertTrue(callable(get_agent_stats))

    def test_get_overall_stats_func(self):
        self.assertTrue(callable(get_overall_stats))

    def test_get_leaderboard_func(self):
        self.assertTrue(callable(get_leaderboard))

    def test_get_cost_breakdown_func(self):
        self.assertTrue(callable(get_cost_breakdown))


if __name__ == "__main__":
    unittest.main()
