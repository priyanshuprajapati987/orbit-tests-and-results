"""Unit tests for orbit/orbit/core/transparency.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.transparency import TransparencyStore, get_transparency_store


class TestTransparencyStore(unittest.TestCase):
    def setUp(self):
        self.ts = TransparencyStore()

    def test_instantiation(self):
        self.assertIsNotNone(self.ts)

    def test_latest_empty(self):
        self.assertIsNone(self.ts.latest())

    def test_record_and_latest(self):
        self.ts.record({"content": "hi", "provider": "groq", "confidence": 0.9})
        r = self.ts.latest()
        self.assertIsNotNone(r)
        self.assertEqual(r["provider"], "groq")

    def test_history(self):
        self.ts.record({"content": "hi"})
        r = self.ts.history(5)
        self.assertIsInstance(r, list)
        self.assertEqual(len(r), 1)

    def test_reset(self):
        self.ts.record({"content": "hi"})
        self.ts.reset()
        self.assertIsNone(self.ts.latest())

    def test_singleton(self):
        a = get_transparency_store()
        b = get_transparency_store()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
