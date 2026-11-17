"""Unit tests for orbit/orbit/core/metrics_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.metrics_bp import metrics_bp, _disk, _BOOT_TIME


class TestDisk(unittest.TestCase):
    def test_disk_returns_usage(self):
        d = _disk()
        self.assertGreater(d.total, 0)
        self.assertGreaterEqual(d.free, 0)
        self.assertGreaterEqual(d.used, 0)

    def test_disk_fallback_to_partitions(self):
        import psutil
        real_disk_usage = psutil.disk_usage
        calls = {"n": 0}
        def fake_disk_usage(path):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("fail-first")
            return real_disk_usage(path)
        with patch("psutil.disk_usage", side_effect=fake_disk_usage), \
             patch("psutil.disk_partitions") as dp:
            dp.return_value = [MagicMock(mountpoint=os.path.abspath(os.sep))]
            d = _disk()
        self.assertGreater(d.total, 0)
        self.assertEqual(calls["n"], 2)

    def test_disk_all_fail_raises(self):
        import psutil
        with patch("psutil.disk_usage", side_effect=RuntimeError("fail")), \
             patch("psutil.disk_partitions", return_value=[]):
            with self.assertRaises(RuntimeError):
                _disk()


class TestMetricsBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(metrics_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(metrics_bp.name, "metrics_bp")

    def test_routes_registered(self):
        rules = [(r.rule, sorted(r.methods - {"HEAD", "OPTIONS"})) for r in self.app.url_map.iter_rules()]
        self.assertIn(("/api/metrics/system", ["GET"]), rules)
        self.assertIn(("/api/metrics/custom", ["GET"]), rules)
        self.assertIn(("/api/metrics/record", ["POST"]), rules)

    def test_system_metrics(self):
        r = self.client.get("/api/metrics/system")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn("process", body)
        self.assertIn("system", body)
        self.assertIn("disk", body)
        self.assertIn("uptime_sec", body)
        self.assertGreaterEqual(body["uptime_sec"], 0)
        # process keys
        for k in ["memory_mb", "memory_percent", "cpu_percent", "threads"]:
            self.assertIn(k, body["process"])
        # system keys
        for k in ["total_gb", "used_gb", "available_gb", "percent", "cpu_count", "cpu_percent"]:
            self.assertIn(k, body["system"])
        # disk keys
        for k in ["total_gb", "used_gb", "free_gb"]:
            self.assertIn(k, body["disk"])
        self.assertGreater(body["disk"]["total_gb"], 0)

    def test_system_metrics_values_sane(self):
        r = self.client.get("/api/metrics/system")
        body = r.get_json()
        self.assertGreater(body["process"]["memory_mb"], 0)
        self.assertGreater(body["system"]["total_gb"], 0)
        self.assertGreaterEqual(body["system"]["cpu_count"], 1)

    def test_boot_time_is_module_level(self):
        import time
        self.assertLessEqual(_BOOT_TIME, time.time())


class TestCustomMetrics(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(metrics_bp)
        self.client = self.app.test_client()

    def test_custom_with_name(self):
        with patch("orbit.core.metrics_dashboard.get_metrics") as gm:
            gm.return_value.get_series.return_value = [1, 2, 3]
            r = self.client.get("/api/metrics/custom?name=cpu&n=3")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["name"], "cpu")
            self.assertEqual(body["series"], [1, 2, 3])
            gm.return_value.get_series.assert_called_once_with("cpu", 3)

    def test_custom_with_name_default_n(self):
        with patch("orbit.core.metrics_dashboard.get_metrics") as gm:
            gm.return_value.get_series.return_value = []
            r = self.client.get("/api/metrics/custom?name=mem")
            gm.return_value.get_series.assert_called_once_with("mem", 60)

    def test_custom_summary_no_name(self):
        with patch("orbit.core.metrics_dashboard.get_metrics") as gm:
            gm.return_value.get_summary.return_value = {"total": 5}
            gm.return_value.get_all_counters.return_value = {"hits": 2}
            r = self.client.get("/api/metrics/custom")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["summary"], {"total": 5})
            self.assertEqual(body["counters"], {"hits": 2})


class TestRecordMetric(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(metrics_bp)
        self.client = self.app.test_client()

    def test_record_success(self):
        with patch("orbit.core.metrics_dashboard.get_metrics") as gm:
            r = self.client.post("/api/metrics/record", json={"name": "cpu", "value": 42.5, "label": "test"})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.get_json()["ok"])
            gm.return_value.record.assert_called_once_with("cpu", 42.5, "test")

    def test_record_defaults(self):
        with patch("orbit.core.metrics_dashboard.get_metrics") as gm:
            r = self.client.post("/api/metrics/record", json={"name": "x"})
            self.assertEqual(r.status_code, 200)
            gm.return_value.record.assert_called_once_with("x", 0.0, "")

    def test_record_string_value_coerced(self):
        with patch("orbit.core.metrics_dashboard.get_metrics") as gm:
            r = self.client.post("/api/metrics/record", json={"name": "x", "value": "7"})
            self.assertEqual(r.status_code, 200)
            gm.return_value.record.assert_called_once_with("x", 7.0, "")

    def test_record_missing_name_400(self):
        r = self.client.post("/api/metrics/record", json={"value": 1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_no_body_400(self):
        r = self.client.post("/api/metrics/record")
        self.assertEqual(r.status_code, 400)

    def test_record_bad_value_500(self):
        # float("not-a-number") raises ValueError -> Flask 500
        r = self.client.post("/api/metrics/record", json={"name": "x", "value": "not-a-number"})
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
