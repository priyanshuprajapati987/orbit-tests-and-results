"""Unit tests for orbit/orbit/agents/__init__.py (registry + re-exports)."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents import AGENT_REGISTRY


class TestAgentsInit(unittest.TestCase):
    def test_registry_size(self):
        self.assertEqual(len(AGENT_REGISTRY), 25)

    def test_queen_in_registry(self):
        self.assertIn("QUEEN", AGENT_REGISTRY)

    def test_all_values_are_classes(self):
        for label, cls in AGENT_REGISTRY.items():
            self.assertTrue(callable(cls), f"{label} not callable")

    def test_all_agents_instantiate(self):
        for label, cls in AGENT_REGISTRY.items():
            inst = cls()
            self.assertIsNotNone(inst, f"{label} failed to instantiate")

    def test_registry_labels_match_agent_labels(self):
        for label, cls in AGENT_REGISTRY.items():
            inst = cls()
            if label == "QUEEN":
                self.assertEqual(inst.label, "QNN")
            else:
                self.assertEqual(inst.label, label, f"{label} != {inst.label}")

    def test_specialized_reexports(self):
        import orbit.agents.specialized as sp
        self.assertEqual(len(sp.__all__), 17)


if __name__ == "__main__":
    unittest.main()
