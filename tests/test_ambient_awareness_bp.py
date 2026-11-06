"""Unit tests for orbit/orbit/core/ambient_awareness_bp.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.ambient_awareness_bp import ambient_awareness_bp


class TestAmbientAwarenessBp(unittest.TestCase):
    def test_blueprint(self):
        self.assertEqual(ambient_awareness_bp.name, "ambient_awareness")
        self.assertEqual(ambient_awareness_bp.url_prefix, "/api/awareness")


if __name__ == "__main__":
    unittest.main()
