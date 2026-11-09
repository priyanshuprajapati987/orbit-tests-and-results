"""Unit tests for orbit/orbit/core/metrics_dashboard.py."""

import math
import os
import sys
import threading
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.metrics_dashboard import MetricsCollector, get_metrics, MetricPoint


class TestMetricPoint(unittest.TestCase):
    def test_defaults(self):
        m = MetricPoint(timestamp=1.0, value=2.0)
        self.assertEqual(m.label, "")


class TestMetricsCollector(unittest.TestCase):
    def setUp(self):
        self.c = MetricsCollector(max_points=5)

    def test_record_and_get_series(self):
        self.c.record("cpu", 10.0, "label1")
        self.c.record("cpu", 20.0)
        series = self.c.get_series("cpu")
        self.assertEqual(len(series), 2)
        self.assertEqual(series[0]["v"], 10.0)
        self.assertEqual(series[0]["l"], "label1")
        self.assertEqual(series[1]["v"], 20.0)

    def test_record_bad_value(self):
        self.c.record("cpu", "not a number")
        self.assertEqual(self.c.get_series("cpu"), [])

    def test_record_non_finite(self):
        self.c.record("cpu", float("inf"))
        self.c.record("cpu", float("nan"))
        self.assertEqual(self.c.get_series("cpu"), [])

    def test_record_max_points(self):
        for i in range(10):
            self.c.record("cpu", float(i))
        series = self.c.get_series("cpu")
        self.assertEqual(len(series), 5)
        self.assertEqual(series[-1]["v"], 9.0)

    def test_get_series_last_n(self):
        for i in range(5):
            self.c.record("cpu", float(i))
        series = self.c.get_series("cpu", last_n=2)
        self.assertEqual(len(series), 2)
        self.assertEqual(series[0]["v"], 3.0)
        self.assertEqual(series[1]["v"], 4.0)

    def test_get_series_unknown(self):
        self.assertEqual(self.c.get_series("nope"), [])

    def test_increment(self):
        self.c.increment("hits")
        self.c.increment("hits", 5)
        self.assertEqual(self.c.get_counter("hits"), 6)

    def test_get_counter_unknown(self):
        self.assertEqual(self.c.get_counter("nope"), 0)

    def test_get_all_counters(self):
        self.c.increment("a", 1)
        self.c.increment("b", 2)
        self.assertEqual(self.c.get_all_counters(), {"a": 1, "b": 2})

    def test_get_summary(self):
        self.c.record("cpu", 10.0)
        self.c.record("cpu", 20.0)
        s = self.c.get_summary()
        self.assertIn("cpu", s)
        self.assertEqual(s["cpu"]["current"], 20.0)
        self.assertEqual(s["cpu"]["avg"], 15.0)
        self.assertEqual(s["cpu"]["min"], 10.0)
        self.assertEqual(s["cpu"]["max"], 20.0)
        self.assertEqual(s["cpu"]["count"], 2)

    def test_get_summary_empty(self):
        self.assertEqual(self.c.get_summary(), {})

    def test_thread_safety_smoke(self):
        def worker():
            for i in range(50):
                self.c.record("x", float(i))
                self.c.increment("c")
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # max_points=5, so at most 5 series points
        self.assertLessEqual(len(self.c.get_series("x")), 5)
        self.assertEqual(self.c.get_counter("c"), 200)

    def test_singleton(self):
        import orbit.core.metrics_dashboard as md
        md._collector = None
        a = get_metrics()
        b = get_metrics()
        self.assertIs(a, b)
        md._collector = None


if __name__ == "__main__":
    unittest.main()
