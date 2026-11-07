"""Unit tests for orbit/orbit/agents/specialized.py (re-export module)."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents import specialized


class TestSpecializedReExports(unittest.TestCase):
    def test_all_exports(self):
        self.assertEqual(len(specialized.__all__), 17)

    def test_all_names_exist(self):
        for name in specialized.__all__:
            self.assertTrue(hasattr(specialized, name), f"missing {name}")

    def test_agents_are_classes(self):
        for name in specialized.__all__:
            obj = getattr(specialized, name)
            self.assertIsInstance(obj, type, f"{name} is not a class")

    def test_agents_instantiate(self):
        for name in specialized.__all__:
            cls = getattr(specialized, name)
            inst = cls()
            self.assertIsNotNone(inst)


if __name__ == "__main__":
    unittest.main()
