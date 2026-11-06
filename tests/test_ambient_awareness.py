"""Unit tests for orbit/orbit/core/ambient_awareness.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.ambient_awareness import situation


class TestAmbientAwareness(unittest.TestCase):
    def test_situation(self):
        r = situation()
        self.assertIsInstance(r, dict)
        self.assertIn("ambient", r)
        self.assertIn("suggestions", r)
        self.assertIn("offers_help", r)


if __name__ == "__main__":
    unittest.main()
