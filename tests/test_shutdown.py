"""Unit tests for orbit/orbit/core/shutdown.py."""

import os
import sys
import threading
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.shutdown as sh_mod
from orbit.core.shutdown import ShutdownManager, get_shutdown_manager, setup_shutdown_handlers, safe_shutdown


class TestShutdownManager(unittest.TestCase):
    def setUp(self):
        self.m = ShutdownManager()

    def test_register_and_list(self):
        calls = []
        self.m.register("a", lambda: calls.append("a"), priority=10)
        self.m.register("b", lambda: calls.append("b"), priority=5)
        # priority sort: lower first
        self.m.shutdown()
        self.assertEqual(calls, ["b", "a"])

    def test_unregister(self):
        calls = []
        self.m.register("a", lambda: calls.append("a"))
        self.m.register("b", lambda: calls.append("b"))
        self.m.unregister("a")
        self.m.shutdown()
        self.assertEqual(calls, ["b"])

    def test_unregister_nonexistent(self):
        self.m.unregister("nope")  # no crash

    def test_handler_exception_recorded(self):
        def boom():
            raise RuntimeError("fail")

        self.m.register("boom", boom)
        self.m.shutdown()  # should not raise
        self.assertTrue(self.m.is_shutting_down())

    def test_is_shutting_down(self):
        self.assertFalse(self.m.is_shutting_down())
        self.m.shutdown()
        self.assertTrue(self.m.is_shutting_down())

    def test_shutdown_idempotent(self):
        calls = []
        self.m.register("a", lambda: calls.append("a"))
        self.m.shutdown()
        self.m.shutdown()  # second call returns early
        self.assertEqual(calls, ["a"])

    def test_wait_for_shutdown(self):
        self.m.shutdown()
        self.assertTrue(self.m.wait_for_shutdown(timeout=0.1))

    def test_wait_for_shutdown_timeout(self):
        self.assertFalse(self.m.wait_for_shutdown(timeout=0.01))

    def test_priority_default(self):
        self.m.register("a", lambda: None)
        with self.m._lock:
            self.assertEqual(self.m._handlers[0][2], 100)

    def test_handlers_sorted_by_priority(self):
        self.m.register("low", lambda: None, priority=200)
        self.m.register("high", lambda: None, priority=10)
        with self.m._lock:
            names = [h[0] for h in self.m._handlers]
        self.assertEqual(names, ["high", "low"])


class TestModuleFunctions(unittest.TestCase):
    def setUp(self):
        sh_mod._shutdown_manager = None

    def tearDown(self):
        sh_mod._shutdown_manager = None

    def test_get_shutdown_manager_singleton(self):
        a = get_shutdown_manager()
        b = get_shutdown_manager()
        self.assertIs(a, b)

    def test_safe_shutdown(self):
        calls = []
        mgr = get_shutdown_manager()
        mgr.register("a", lambda: calls.append("a"))
        safe_shutdown()
        self.assertEqual(calls, ["a"])
        self.assertTrue(mgr.is_shutting_down())

    def test_setup_shutdown_handlers(self):
        setup_shutdown_handlers()  # registers atexit; no crash
        # idempotent-ish
        setup_shutdown_handlers()


if __name__ == "__main__":
    unittest.main()
