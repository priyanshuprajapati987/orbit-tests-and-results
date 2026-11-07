"""Unit tests for orbit/orbit/core/runtime_stats.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.runtime_stats as rs


class TestRuntimeStats(unittest.TestCase):
    def setUp(self):
        # reset module state
        with rs._lock:
            rs._stats.clear()

    def tearDown(self):
        with rs._lock:
            rs._stats.clear()

    def test_set_and_get(self):
        rs.set_stat("k", 5)
        self.assertEqual(rs.get_stat("k"), 5)

    def test_get_default(self):
        self.assertEqual(rs.get_stat("missing"), None)
        self.assertEqual(rs.get_stat("missing", "default"), "default")

    def test_set_overwrites(self):
        rs.set_stat("k", 1)
        rs.set_stat("k", 2)
        self.assertEqual(rs.get_stat("k"), 2)

    def test_set_coerces_key_to_str(self):
        rs.set_stat(123, "v")
        self.assertEqual(rs.get_stat("123"), "v")

    def test_snapshot_copy(self):
        rs.set_stat("a", 1)
        snap = rs.snapshot()
        self.assertEqual(snap, {"a": 1})
        rs.set_stat("a", 2)
        self.assertEqual(snap, {"a": 1})  # snapshot is a copy

    def test_snapshot_empty(self):
        self.assertEqual(rs.snapshot(), {})


if __name__ == "__main__":
    unittest.main()
