"""Unit tests for orbit/orbit/core/capabilities_bp.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.capabilities_bp import capabilities_bp


class TestCapabilitiesBp(unittest.TestCase):
    def test_blueprint(self):
        self.assertEqual(capabilities_bp.name, "capabilities")
        self.assertEqual(capabilities_bp.url_prefix, "/api/capabilities")


if __name__ == "__main__":
    unittest.main()
