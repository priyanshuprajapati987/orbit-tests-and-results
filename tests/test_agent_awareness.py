"""
Agent Awareness — Tests

Tests AgentPerformanceJournal (per-agent tracking) and AgentAwarenessManager (team orchestration).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbit.orbit.core.agent_awareness import (
    AgentAwarenessManager,
    AgentPerformanceJournal,
    Decision,
    get_awareness_manager,
)


class TestDecision(unittest.TestCase):
    def test_01_decision_creation(self):
        d = Decision("coding", "Write tests", "pass", "pass", True, 0.9, 1.2, 500, 0.01)
        self.assertEqual(d.domain, "coding")
        self.assertTrue(d.correct)

    def test_02_decision_to_dict_roundtrip(self):
        d = Decision("research", "Find API", "found", "found", True)
        data = d.to_dict()
        restored = Decision.from_dict(data)
        self.assertEqual(restored.domain, "research")
        self.assertEqual(restored.task, "Find API")
        self.assertTrue(restored.correct)
        self.assertEqual(restored.timestamp.isoformat(), d.timestamp.isoformat())


class TestAgentPerformanceJournal(unittest.TestCase):
    def setUp(self):
        self.journal = AgentPerformanceJournal(
            "TestAgent", ["coding", "research", "writing"]
        )

    def test_03_log_decision_increases_count(self):
        self.assertEqual(len(self.journal.decisions), 0)
        self.journal.log_decision(Decision("coding", "Fix bug", "fix", "fix", True))
        self.assertEqual(len(self.journal.decisions), 1)

    def test_04_accuracy_starts_at_1_after_first_success(self):
        self.journal.log_decision(Decision("coding", "Fix bug", "fix", "fix", True))
        self.assertEqual(self.journal.accuracy_per_domain["coding"], 1.0)

    def test_05_accuracy_drops_on_failure(self):
        self.journal.log_decision(Decision("coding", "Fix bug", "fix", "fix", True))
        self.journal.log_decision(
            Decision("coding", "Fix bug", "fix", "still_broken", False)
        )
        self.assertEqual(self.journal.accuracy_per_domain["coding"], 0.5)

    def test_06_confidence_reflects_accuracy(self):
        self.journal.log_decision(Decision("coding", "Fix bug", "fix", "fix", True))
        self.assertEqual(self.journal.get_confidence("coding"), 100.0)

    def test_07_confidence_unknown_domain(self):
        self.assertEqual(self.journal.get_confidence("unknown"), 50.0)

    def test_08_should_handle_unknown_domain(self):
        self.assertFalse(self.journal.should_handle_task("unknown"))

    def test_09_should_handle_high_complexity_low_accuracy(self):
        self.journal.log_decision(Decision("writing", "Write", "done", "done", True))
        self.journal.log_decision(Decision("writing", "Write", "done", "failed", False))
        self.journal.log_decision(Decision("writing", "Write", "done", "failed", False))
        self.assertFalse(
            self.journal.should_handle_task("writing", task_complexity=0.8)
        )

    def test_10_should_handle_simple_task(self):
        self.journal.log_decision(Decision("coding", "Fix bug", "fix", "fix", True))
        self.assertTrue(self.journal.should_handle_task("coding", task_complexity=0.3))

    def test_11_weak_domains(self):
        self.journal.log_decision(
            Decision("research", "Find", "found", "missed", False)
        )
        self.journal.log_decision(
            Decision("research", "Find", "found", "missed", False)
        )
        self.assertIn("research", self.journal.get_weak_domains(threshold=0.6))

    def test_12_strong_domains(self):
        self.journal.log_decision(Decision("coding", "Fix", "fix", "fix", True))
        self.journal.log_decision(Decision("coding", "Fix", "fix", "fix", True))
        self.assertIn("coding", self.journal.get_strong_domains(threshold=0.8))

    def test_13_failure_patterns_logged(self):
        self.journal.log_decision(Decision("coding", "Bug", "fix", "broke", False))
        self.assertEqual(len(self.journal.failure_patterns), 1)

    def test_14_no_failure_patterns_on_success(self):
        self.journal.log_decision(Decision("coding", "Bug", "fix", "fix", True))
        self.assertEqual(len(self.journal.failure_patterns), 0)

    def test_15_performance_summary_structure(self):
        self.journal.log_decision(Decision("coding", "Task", "done", "done", True))
        summary = self.journal.get_performance_summary()
        self.assertIn("agent", summary)
        self.assertIn("accuracy_per_domain", summary)
        self.assertIn("confidence_per_domain", summary)
        self.assertIn("failure_count", summary)
        self.assertEqual(summary["agent"], "TestAgent")

    def test_16_to_dict_roundtrip(self):
        self.journal.log_decision(
            Decision("coding", "Task A", "done", "done", True, 0.9, 1.5, 100, 0.01)
        )
        self.journal.log_decision(
            Decision(
                "research", "Task B", "found", "missed", False, 0.4, 2.0, 200, 0.02
            )
        )
        data = self.journal.to_dict()
        restored = AgentPerformanceJournal.from_dict(data)
        self.assertEqual(restored.agent_name, "TestAgent")
        self.assertEqual(len(restored.decisions), 2)
        self.assertIn("coding", restored.accuracy_per_domain)
        self.assertIn("research", restored.accuracy_per_domain)


class TestAgentAwarenessManager(unittest.TestCase):
    def setUp(self):
        self.mgr = AgentAwarenessManager()
        self.mgr.reset()

    def test_17_register_agent(self):
        self.mgr.register_agent("CodeAgent", ["coding", "debugging"])
        self.assertIn("CodeAgent", self.mgr.journals)

    def test_18_log_decision_updates_journal(self):
        self.mgr.register_agent("ResearchAgent", ["research"])
        self.mgr.log_decision(
            "ResearchAgent", Decision("research", "Find", "found", "found", True)
        )
        journal = self.mgr.get_journal("ResearchAgent")
        self.assertEqual(len(journal.decisions), 1)

    def test_19_best_agent_for_domain(self):
        self.mgr.register_agent("AgentA", ["coding"])
        self.mgr.register_agent("AgentB", ["coding"])
        self.mgr.log_decision("AgentA", Decision("coding", "Fix", "fix", "fix", True))
        self.mgr.log_decision("AgentB", Decision("coding", "Fix", "fix", "fix", True))
        self.mgr.log_decision("AgentA", Decision("coding", "Fix", "fix", "fix", True))
        best = self.mgr.get_best_agent_for_domain("coding")
        self.assertEqual(best, "AgentA")

    def test_20_best_agent_no_candidates(self):
        best = self.mgr.get_best_agent_for_domain("nonexistent")
        self.assertIsNone(best)

    def test_21_team_summary(self):
        self.mgr.register_agent("AgentA", ["coding"])
        self.mgr.register_agent("AgentB", ["research"])
        self.mgr.log_decision(
            "AgentA", Decision("coding", "Task", "done", "done", True)
        )
        summary = self.mgr.get_team_summary()
        self.assertEqual(summary["team_size"], 2)
        self.assertEqual(summary["total_decisions"], 1)

    def test_22_get_all_journals(self):
        self.mgr.register_agent("AgentA", ["coding"])
        self.mgr.register_agent("AgentB", ["research"])
        journals = self.mgr.get_all_journals()
        self.assertEqual(len(journals), 2)

    def test_23_reset(self):
        self.mgr.register_agent("AgentA", ["coding"])
        self.mgr.reset()
        self.assertEqual(len(self.mgr.journals), 0)

    def test_24_singleton(self):
        inst = get_awareness_manager()
        self.assertIs(inst, get_awareness_manager())
        self.assertIsInstance(inst, AgentAwarenessManager)

    def test_25_persistence(self):
        self.mgr.register_agent("PersistAgent", ["coding"])
        self.mgr.log_decision(
            "PersistAgent", Decision("coding", "T", "done", "done", True)
        )
        new_mgr = AgentAwarenessManager()
        self.assertIn("PersistAgent", new_mgr.journals)
        new_mgr.reset()


if __name__ == "__main__":
    unittest.main()
