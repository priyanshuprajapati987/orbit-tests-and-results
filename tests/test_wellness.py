"""Unit tests for orbit/orbit/core/wellness.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.wellness import status


class TestWellness(unittest.TestCase):
    def test_status(self):
        r = status()
        self.assertIsInstance(r, dict)
        self.assertIn("session_minutes", r)
        self.assertIn("suggestion", r)


if __name__ == "__main__":
    unittest.main()
