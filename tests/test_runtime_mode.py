"""Unit tests for orbit/orbit/core/runtime_mode.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.runtime_mode import RuntimeMode, get_runtime_mode


class TestRuntimeMode(unittest.TestCase):
    def test_default_local(self):
        rm = RuntimeMode()
        self.assertEqual(rm.get(), "local")

    def test_set_auto(self):
        rm = RuntimeMode()
        self.assertEqual(rm.set("auto"), "auto")
        self.assertEqual(rm.get(), "auto")

    def test_set_invalid_raises(self):
        rm = RuntimeMode()
        with self.assertRaises(ValueError):
            rm.set("cloud")

    def test_force_offline(self):
        rm = RuntimeMode("local")
        self.assertTrue(rm.force_offline())
        rm.set("auto")
        self.assertFalse(rm.force_offline())

    def test_singleton(self):
        a = get_runtime_mode()
        b = get_runtime_mode()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
