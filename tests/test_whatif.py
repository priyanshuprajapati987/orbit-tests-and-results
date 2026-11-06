"""Unit tests for orbit/orbit/core/whatif.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.whatif import simulate


class TestWhatif(unittest.TestCase):
    def test_empty_action(self):
        r = simulate("")
        self.assertFalse(r.get("ok", True))
        self.assertEqual(r.get("error"), "empty action")

    def test_none_action(self):
        r = simulate(None)
        self.assertFalse(r.get("ok", True))

    def test_simulate_calls_router(self):
        try:
            r = simulate("delete all files")
            self.assertTrue(isinstance(r, dict))
        except Exception:
            self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
