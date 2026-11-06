"""Unit tests for orbit/orbit/core/capabilities.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.capabilities import CAPABILITIES, list_capabilities


class TestCapabilities(unittest.TestCase):
    def test_list_capabilities(self):
        r = list_capabilities()
        self.assertIsInstance(r, list)
        self.assertGreater(len(r), 0)
        self.assertIn("id", r[0])

    def test_constant(self):
        self.assertIs(list_capabilities(), CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
