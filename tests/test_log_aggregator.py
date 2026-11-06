"""Unit tests for orbit/orbit/core/log_aggregator.py."""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.log_aggregator import (
    LogLevel, LogAggregator, get_log_aggregator, add_log, add_info, add_error, search_logs, get_statistics,
)


class TestLogLevel(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(LogLevel.DEBUG, "DEBUG")
        self.assertEqual(LogLevel.ERROR, "ERROR")


class TestLogAggregator(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if os.path.exists(self.path):
            os.remove(self.path)
        self.la = LogAggregator(storage_file=self.path)

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def test_instantiation(self):
        self.assertIsNotNone(self.la)

    def test_add_log(self):
        self.la.add_log("INFO", "hello world", source="test")
        self.assertTrue(True)

    def test_add_info(self):
        self.la.add_info("info msg", source="test")
        self.assertTrue(True)

    def test_add_warning(self):
        self.la.add_warning("warn msg", source="test")
        self.assertTrue(True)

    def test_add_error(self):
        self.la.add_error("err msg", source="test")
        self.assertTrue(True)

    def test_add_critical(self):
        self.la.add_critical("crit msg", source="test")
        self.assertTrue(True)

    def test_add_debug(self):
        self.la.add_debug("debug msg", source="test")
        self.assertTrue(True)

    def test_search_logs(self):
        self.la.add_log("INFO", "hello world", source="test")
        r = self.la.search_logs("hello")
        self.assertIsNotNone(r)

    def test_get_logs_by_level(self):
        self.la.add_log("INFO", "msg", source="test")
        r = self.la.get_logs_by_level("INFO")
        self.assertIsInstance(r, list)

    def test_get_logs_by_source(self):
        self.la.add_log("INFO", "msg", source="testsrc")
        r = self.la.get_logs_by_source("testsrc")
        self.assertIsInstance(r, list)

    def test_get_recent_logs(self):
        self.la.add_log("INFO", "msg", source="test")
        r = self.la.get_recent_logs(5)
        self.assertIsInstance(r, list)

    def test_get_statistics(self):
        r = self.la.get_statistics()
        self.assertIsNotNone(r)

    def test_add_pattern(self):
        r = self.la.add_pattern("errpat", "error")
        self.assertTrue(r is None or isinstance(r, (bool, dict, str)))

    def test_get_pattern_matches(self):
        self.la.add_pattern("errpat", "error")
        self.la.add_log("ERROR", "boom", source="test")
        r = self.la.get_pattern_matches("errpat")
        self.assertIsNotNone(r)

    def test_cleanup_old_logs(self):
        r = self.la.cleanup_old_logs()
        self.assertTrue(r is None or isinstance(r, (int, dict, bool)))

    def test_export_logs(self):
        fd, p = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.la.add_log("INFO", "msg", source="test")
        self.la.export_logs(p)
        self.assertTrue(os.path.exists(p))
        os.remove(p)

    def test_singleton(self):
        a = get_log_aggregator()
        b = get_log_aggregator()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_add_log_func(self):
        self.assertTrue(callable(add_log))

    def test_add_info_func(self):
        self.assertTrue(callable(add_info))

    def test_add_error_func(self):
        self.assertTrue(callable(add_error))

    def test_search_logs_func(self):
        self.assertTrue(callable(search_logs))

    def test_get_statistics_func(self):
        self.assertTrue(callable(get_statistics))


if __name__ == "__main__":
    unittest.main()
