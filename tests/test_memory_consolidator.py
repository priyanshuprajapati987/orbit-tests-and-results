"""Unit tests for orbit/orbit/core/memory_consolidator.py (re-export module)."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core import memory_consolidator as mc


class TestMemoryConsolidatorReexport(unittest.TestCase):
    def test_all_names_present(self):
        for name in mc.__all__:
            self.assertTrue(hasattr(mc, name), f"missing {name}")

    def test_alias_equal(self):
        self.assertIs(mc.MemoryConsolidator, mc.MemoryConsolidation)

    def test_get_consolidator_callable(self):
        self.assertTrue(callable(mc.get_consolidator))

    def test_singleton(self):
        a = mc.get_consolidator()
        b = mc.get_consolidator()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
