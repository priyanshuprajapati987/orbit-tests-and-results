"""Unit tests for orbit/orbit/core/macro_learner.py."""

import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.macro_learner import MacroLearner, get_macro_learner


class TestMacroLearner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "macros.json")
        self.m = MacroLearner(store_path=self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_empty(self):
        self.assertEqual(self.m.list_macros(), [])

    def test_record(self):
        r = self.m.record("m1", [{"action": "open"}, {"action": "read"}])
        self.assertTrue(r["ok"])
        self.assertEqual(r["name"], "m1")
        self.assertEqual(r["steps"], 2)
        self.assertIn("m1", self.m.list_macros())

    def test_record_empty_name_generates(self):
        r = self.m.record("", [{"action": "x"}])
        self.assertTrue(r["ok"])
        self.assertTrue(r["name"].startswith("macro_"))

    def test_record_persists(self):
        self.m.record("m1", [{"action": "open"}])
        # reload from disk
        m2 = MacroLearner(store_path=self.path)
        self.assertIn("m1", m2.list_macros())

    def test_list_macros_sorted(self):
        self.m.record("b", [{"action": "x"}])
        self.m.record("a", [{"action": "y"}])
        self.assertEqual(self.m.list_macros(), ["a", "b"])

    def test_replay_plan_found(self):
        self.m.record("m1", [{"action": "open"}, {"action": "delete"}])
        r = self.m.replay_plan("m1")
        self.assertTrue(r["ok"])
        self.assertEqual(r["name"], "m1")
        self.assertEqual(len(r["plan"]), 2)
        self.assertEqual(r["risky_steps"], 1)

    def test_replay_plan_not_found(self):
        r = self.m.replay_plan("nope")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "no such macro")

    def test_reset(self):
        self.m.record("m1", [{"action": "x"}])
        self.m.reset()
        self.assertEqual(self.m.list_macros(), [])
        # persisted
        m2 = MacroLearner(store_path=self.path)
        self.assertEqual(m2.list_macros(), [])

    def test_load_corrupt_file(self):
        with open(self.path, "w") as f:
            f.write("not json")
        m = MacroLearner(store_path=self.path)
        self.assertEqual(m.list_macros(), [])

    def test_load_non_dict(self):
        with open(self.path, "w") as f:
            json.dump([1, 2, 3], f)
        m = MacroLearner(store_path=self.path)
        self.assertEqual(m.list_macros(), [])

    def test_singleton(self):
        import orbit.core.macro_learner as ml
        ml._store = None
        a = get_macro_learner()
        b = get_macro_learner()
        self.assertIs(a, b)
        ml._store = None


if __name__ == "__main__":
    unittest.main()
