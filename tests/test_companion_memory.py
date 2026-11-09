"""Unit tests for orbit/orbit/core/companion_memory.py."""

import json
import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.companion_memory import CompanionMemory, get_companion_memory


class TestCompanionMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "cm.json")
        self.cm = CompanionMemory(store_path=self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_empty(self):
        self.assertEqual(self.cm.timeline(), [])

    def test_add_event(self):
        ev = self.cm.add_event("decided to switch jobs", "decision")
        self.assertEqual(ev["text"], "decided to switch jobs")
        self.assertEqual(ev["kind"], "decision")
        self.assertIn("ts", ev)
        self.assertEqual(len(self.cm.timeline()), 1)

    def test_add_event_empty_returns_empty(self):
        self.assertEqual(self.cm.add_event(""), {})
        self.assertEqual(self.cm.add_event("   "), {})
        self.assertEqual(len(self.cm.timeline()), 0)

    def test_add_event_default_kind(self):
        ev = self.cm.add_event("hello")
        self.assertEqual(ev["kind"], "moment")

    def test_timeline_n(self):
        for i in range(5):
            self.cm.add_event(f"e{i}")
        self.assertEqual(len(self.cm.timeline(3)), 3)
        self.assertEqual(len(self.cm.timeline(10)), 5)

    def test_timeline_min_1(self):
        self.cm.add_event("e0")
        self.assertEqual(len(self.cm.timeline(0)), 1)

    def test_timeline_returns_copy(self):
        self.cm.add_event("e0")
        t = self.cm.timeline()
        t[0]["text"] = "modified"
        self.assertEqual(self.cm.timeline()[0]["text"], "e0")

    def test_summarize_empty(self):
        self.assertEqual(self.cm.summarize(), "No companion memories yet.")

    def test_summarize(self):
        self.cm.add_event("decided", "decision")
        self.cm.add_event("happy", "mood")
        s = self.cm.summarize()
        self.assertTrue(s.startswith("Recent life thread:"))
        self.assertIn("(decision) decided", s)
        self.assertIn("(mood) happy", s)

    def test_summarize_last_15(self):
        for i in range(20):
            self.cm.add_event(f"e{i}")
        s = self.cm.summarize()
        # only last 15
        self.assertNotIn("e0", s)
        self.assertIn("e19", s)

    def test_reset(self):
        self.cm.add_event("e0")
        self.cm.reset()
        self.assertEqual(self.cm.timeline(), [])

    def test_persist(self):
        self.cm.add_event("e0")
        cm2 = CompanionMemory(store_path=self.path)
        self.assertEqual(len(cm2.timeline()), 1)
        self.assertEqual(cm2.timeline()[0]["text"], "e0")

    def test_load_corrupt(self):
        with open(self.path, "w") as f:
            f.write("not json")
        cm = CompanionMemory(store_path=self.path)
        self.assertEqual(cm.timeline(), [])

    def test_load_non_list(self):
        with open(self.path, "w") as f:
            import json
            json.dump({"a": 1}, f)
        cm = CompanionMemory(store_path=self.path)
        self.assertEqual(cm.timeline(), [])

    def test_singleton(self):
        import orbit.core.companion_memory as cm_mod
        cm_mod._store = None
        a = get_companion_memory()
        b = get_companion_memory()
        self.assertIs(a, b)
        cm_mod._store = None


if __name__ == "__main__":
    unittest.main()
