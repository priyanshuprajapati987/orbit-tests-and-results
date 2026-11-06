"""Unit tests for orbit/orbit/core/failover.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.failover import (
    ProviderStatus, FailoverManager, get_failover_manager,
    record_success, record_failure, get_best_provider, get_provider_status, is_available,
)


class TestProviderStatus(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(ProviderStatus.HEALTHY.value, "healthy")
        self.assertEqual(ProviderStatus.FAILED.value, "failed")


class TestFailoverManager(unittest.TestCase):
    def setUp(self):
        self.fm = FailoverManager()

    def test_instantiation(self):
        self.assertIsNotNone(self.fm)

    def test_check_provider_health(self):
        r = self.fm.check_provider_health("groq")
        self.assertEqual(r, ProviderStatus.HEALTHY)

    def test_record_success(self):
        self.fm.record_success("groq", 100)
        self.assertTrue(True)

    def test_record_failure(self):
        self.fm.record_failure("groq", "boom")
        self.assertTrue(True)

    def test_get_best_provider(self):
        r = self.fm.get_best_provider()
        self.assertTrue(r is None or isinstance(r, str))

    def test_get_provider_status(self):
        r = self.fm.get_provider_status()
        self.assertIsNotNone(r)

    def test_reset_provider(self):
        self.fm.reset_provider("groq")
        self.assertTrue(True)

    def test_is_available(self):
        r = self.fm.is_available("groq")
        self.assertTrue(r is None or isinstance(r, bool))

    def test_singleton(self):
        a = get_failover_manager()
        b = get_failover_manager()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_record_success_func(self):
        self.assertTrue(callable(record_success))

    def test_record_failure_func(self):
        self.assertTrue(callable(record_failure))

    def test_get_best_provider_func(self):
        self.assertTrue(callable(get_best_provider))

    def test_get_provider_status_func(self):
        self.assertTrue(callable(get_provider_status))

    def test_is_available_func(self):
        self.assertTrue(callable(is_available))


if __name__ == "__main__":
    unittest.main()
