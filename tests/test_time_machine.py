"""Unit tests for orbit/orbit/core/time_machine.py."""

import json
import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.time_machine import TimeMachine, get_time_machine


class TestTimeMachine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "tm.json")
        self.tm = TimeMachine(store_path=self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_empty(self):
        self.assertEqual(self.tm.log(), [])

    def test_record(self):
        self.tm.record("hi", "hello")
        log = self.tm.log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["user"], "hi")
        self.assertEqual(log[0]["orbit"], "hello")
        self.assertIn("ts", log[0])

    def test_log_n(self):
        for i in range(5):
            self.tm.record(f"u{i}", f"o{i}")
        self.assertEqual(len(self.tm.log(3)), 3)
        self.assertEqual(len(self.tm.log(10)), 5)

    def test_log_min_1(self):
        self.tm.record("u", "o")
        self.assertEqual(len(self.tm.log(0)), 1)
        self.assertEqual(len(self.tm.log(-5)), 1)

    def test_restore_valid(self):
        self.tm.record("u0", "o0")
        self.tm.record("u1", "o1")
        r = self.tm.restore(0)
        self.assertEqual(r["user"], "u0")
        self.assertEqual(r["orbit"], "o0")

    def test_restore_invalid(self):
        self.tm.record("u0", "o0")
        self.assertIsNone(self.tm.restore(5))
        self.assertIsNone(self.tm.restore(-1))

    def test_restore_returns_copy(self):
        self.tm.record("u0", "o0")
        r = self.tm.restore(0)
        r["user"] = "modified"
        self.assertEqual(self.tm.restore(0)["user"], "u0")

    def test_reset(self):
        self.tm.record("u0", "o0")
        self.tm.reset()
        self.assertEqual(self.tm.log(), [])

    def test_persist(self):
        self.tm.record("u0", "o0")
        tm2 = TimeMachine(store_path=self.path)
        self.assertEqual(len(tm2.log()), 1)
        self.assertEqual(tm2.log()[0]["user"], "u0")

    def test_load_corrupt(self):
        with open(self.path, "w") as f:
            f.write("not json")
        tm = TimeMachine(store_path=self.path)
        self.assertEqual(tm.log(), [])

    def test_load_non_list(self):
        with open(self.path, "w") as f:
            import json
            json.dump({"a": 1}, f)
        tm = TimeMachine(store_path=self.path)
        self.assertEqual(tm.log(), [])

    def test_max_500_cap(self):
        for i in range(510):
            self.tm.record(f"u{i}", f"o{i}")
        self.assertEqual(len(self.tm.log(600)), 500)

    def test_singleton(self):
        import orbit.core.time_machine as tm_mod
        tm_mod._store = None
        a = get_time_machine()
        b = get_time_machine()
        self.assertIs(a, b)
        tm_mod._store = None


if __name__ == "__main__":
    unittest.main()
