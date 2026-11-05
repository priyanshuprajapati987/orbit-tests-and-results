"""Tests for Team Restructurer (System 8)"""

import tempfile
import unittest


class TestTeamRestructurer(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()

    def _get_restructurer(self):
        import orbit.orbit.core.team_restructurer as m

        m.DATA_DIR = type(m.DATA_DIR)(self.data_dir)
        m.DATA_DIR.mkdir(parents=True, exist_ok=True)
        m._instance = None
        from orbit.orbit.core.team_restructurer import get_team_restructurer

        return get_team_restructurer()

    def test_import(self):
        from orbit.orbit.core.team_restructurer import (
            get_team_restructurer,
        )

        self.assertTrue(callable(get_team_restructurer))

    def test_analyze_load_light(self):
        r = self._get_restructurer()
        self.assertEqual(r.analyze_load(3), "light")
        self.assertEqual(r.analyze_load(4), "light")

    def test_analyze_load_medium(self):
        r = self._get_restructurer()
        self.assertEqual(r.analyze_load(5), "medium")
        self.assertEqual(r.analyze_load(14), "medium")

    def test_analyze_load_heavy(self):
        r = self._get_restructurer()
        self.assertEqual(r.analyze_load(15), "heavy")
        self.assertEqual(r.analyze_load(100), "heavy")

    def test_restructure_flat(self):
        r = self._get_restructurer()
        agents = [
            {
                "name": "A1",
                "label": "Agent 1",
                "category": "code",
                "overall_accuracy": 0.8,
            }
        ]
        result = r.restructure(agents, "light")
        self.assertEqual(result["load_level"], "light")
        self.assertEqual(result["structure"]["type"], "flat")
        self.assertEqual(len(result["structure"]["teams"]), 1)

    def test_restructure_specialist(self):
        r = self._get_restructurer()
        agents = [
            {
                "name": "A1",
                "label": "Agent 1",
                "category": "code",
                "overall_accuracy": 0.8,
            },
            {
                "name": "A2",
                "label": "Agent 2",
                "category": "research",
                "overall_accuracy": 0.7,
            },
            {
                "name": "A3",
                "label": "Agent 3",
                "category": "code",
                "overall_accuracy": 0.9,
            },
            {
                "name": "A4",
                "label": "Agent 4",
                "category": "writing",
                "overall_accuracy": 0.6,
            },
            {
                "name": "A5",
                "label": "Agent 5",
                "category": "research",
                "overall_accuracy": 0.75,
            },
        ]
        result = r.restructure(agents, "medium")
        self.assertEqual(result["structure"]["type"], "specialist")
        self.assertGreaterEqual(len(result["structure"]["teams"]), 2)

    def test_restructure_hierarchical(self):
        r = self._get_restructurer()
        agents = [
            {
                "name": "A1",
                "label": "Agent 1",
                "category": "code",
                "overall_accuracy": 0.9,
            },
            {
                "name": "A2",
                "label": "Agent 2",
                "category": "research",
                "overall_accuracy": 0.8,
            },
            {
                "name": "A3",
                "label": "Agent 3",
                "category": "code",
                "overall_accuracy": 0.7,
            },
            {
                "name": "A4",
                "label": "Agent 4",
                "category": "writing",
                "overall_accuracy": 0.6,
            },
            {
                "name": "A5",
                "label": "Agent 5",
                "category": "research",
                "overall_accuracy": 0.75,
            },
            {
                "name": "A6",
                "label": "Agent 6",
                "category": "social",
                "overall_accuracy": 0.85,
            },
            {
                "name": "A7",
                "label": "Agent 7",
                "category": "code",
                "overall_accuracy": 0.65,
            },
            {
                "name": "A8",
                "label": "Agent 8",
                "category": "writing",
                "overall_accuracy": 0.95,
            },
            {
                "name": "A9",
                "label": "Agent 9",
                "category": "system",
                "overall_accuracy": 0.7,
            },
            {
                "name": "A10",
                "label": "Agent 10",
                "category": "code",
                "overall_accuracy": 0.8,
            },
            {
                "name": "A11",
                "label": "Agent 11",
                "category": "research",
                "overall_accuracy": 0.72,
            },
            {
                "name": "A12",
                "label": "Agent 12",
                "category": "social",
                "overall_accuracy": 0.78,
            },
            {
                "name": "A13",
                "label": "Agent 13",
                "category": "code",
                "overall_accuracy": 0.88,
            },
            {
                "name": "A14",
                "label": "Agent 14",
                "category": "system",
                "overall_accuracy": 0.82,
            },
            {
                "name": "A15",
                "label": "Agent 15",
                "category": "writing",
                "overall_accuracy": 0.91,
            },
        ]
        result = r.restructure(agents, "heavy")
        self.assertEqual(result["structure"]["type"], "hierarchical")
        self.assertIsNotNone(result["structure"]["coordinator"])

    def test_get_history(self):
        r = self._get_restructurer()
        agents = [
            {
                "name": "A1",
                "label": "Agent 1",
                "category": "code",
                "overall_accuracy": 0.8,
            }
        ]
        r.restructure(agents)
        r.restructure(agents, "heavy")
        history = r.get_history()
        self.assertEqual(len(history), 2)

    def test_get_current_structure(self):
        r = self._get_restructurer()
        agents = [
            {
                "name": "A1",
                "label": "Agent 1",
                "category": "code",
                "overall_accuracy": 0.8,
            }
        ]
        r.restructure(agents)
        current = r.get_current_structure()
        self.assertIsNotNone(current)
        self.assertEqual(current["structure"]["type"], "flat")

    def test_get_stats(self):
        r = self._get_restructurer()
        agents = [
            {
                "name": "A1",
                "label": "Agent 1",
                "category": "code",
                "overall_accuracy": 0.8,
            }
        ]
        r.restructure(agents, "light")
        stats = r.get_stats()
        self.assertEqual(stats["total_restructures"], 1)
        self.assertIn("load_distribution", stats)

    def test_reset(self):
        r = self._get_restructurer()
        agents = [
            {
                "name": "A1",
                "label": "Agent 1",
                "category": "code",
                "overall_accuracy": 0.8,
            }
        ]
        r.restructure(agents)
        r.reset()
        self.assertEqual(len(r.get_history()), 0)

    def test_singleton(self):
        from orbit.orbit.core.team_restructurer import get_team_restructurer

        s1 = get_team_restructurer()
        s2 = get_team_restructurer()
        self.assertIs(s1, s2)

    def test_no_agents_structure(self):
        r = self._get_restructurer()
        result = r.restructure([], "light")
        self.assertEqual(len(result["structure"]["teams"][0]["agents"]), 0)

    def test_pick_best_no_agents(self):
        r = self._get_restructurer()
        self.assertIsNone(r._pick_best([]))

    def test_pick_best_accuracy(self):
        r = self._get_restructurer()
        agents = [
            {"name": "A1", "label": "A1", "category": "code", "overall_accuracy": 0.5},
            {"name": "A2", "label": "A2", "category": "code", "overall_accuracy": 0.9},
        ]
        best = r._pick_best(agents)
        self.assertEqual(best, "A2")


if __name__ == "__main__":
    unittest.main()
