"""
Inter-Agent Learning — Tests

Tests SolutionPatternIndexer (TF-IDF pattern retrieval) and LearningBridge (agent-to-agent learning).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbit.orbit.core.agent_awareness import AgentAwarenessManager
from orbit.orbit.core.agent_learning import (
    LearningBridge,
    SolutionPattern,
    SolutionPatternIndexer,
    get_learning_bridge,
    get_pattern_indexer,
)


class TestSolutionPattern(unittest.TestCase):
    def test_01_pattern_creation(self):
        sp = SolutionPattern(
            agent_source="CodeAgent",
            problem_type="timeout_handling",
            problem_description="API requests timeout after 30s",
            solution_approach="Implement exponential backoff with jitter",
            outcome_metric=1.0,
            domain_tags=["backend", "api"],
        )
        self.assertTrue(sp.id.startswith("sp_"))
        self.assertEqual(sp.agent_source, "CodeAgent")

    def test_02_pattern_to_dict_roundtrip(self):
        sp = SolutionPattern(
            agent_source="TestAgent",
            problem_type="parsing_error",
            problem_description="JSON parse failure",
            solution_approach="Use try/except with schema validation",
        )
        data = sp.to_dict()
        restored = SolutionPattern.from_dict(data)
        self.assertEqual(restored.id, sp.id)
        self.assertEqual(restored.agent_source, sp.agent_source)
        self.assertEqual(restored.solution_approach, sp.solution_approach)


class TestSolutionPatternIndexer(unittest.TestCase):
    def setUp(self):
        self.indexer = SolutionPatternIndexer()
        self.indexer.reset()

    def test_03_index_and_count(self):
        sp = SolutionPattern(
            "CodeAgent", "timeout_handling", "API timeout", "Exponential backoff"
        )
        self.indexer.index_pattern(sp)
        self.assertEqual(self.indexer.count_patterns(), 1)

    def test_04_find_patterns_returns_results(self):
        self.indexer.index_pattern(
            SolutionPattern(
                "CodeAgent",
                "timeout_handling",
                "API timeout after 30s",
                "Implement exponential backoff with jitter and max retries",
            )
        )
        results = self.indexer.find_patterns("How to handle API timeout?")
        self.assertGreater(len(results), 0)
        self.assertIn("similarity", results[0])
        self.assertIn("pattern", results[0])

    def test_05_find_patterns_no_match(self):
        self.indexer.index_pattern(
            SolutionPattern(
                "CodeAgent",
                "timeout_handling",
                "API timeout",
                "Exponential backoff implementation",
            )
        )
        results = self.indexer.find_patterns("quantum physics computation")
        self.assertEqual(len(results), 0)

    def test_06_multiple_patterns_ranked(self):
        self.indexer.index_pattern(
            SolutionPattern(
                "CodeAgent",
                "timeout_handling",
                "API timeout fix",
                "Exponential backoff with jitter for API calls",
            )
        )
        self.indexer.index_pattern(
            SolutionPattern(
                "ResearchAgent",
                "parsing_error",
                "JSON parse error",
                "Schema validation with try/except blocks",
            )
        )
        results = self.indexer.find_patterns("API timeout retry strategy", top_k=5)
        self.assertGreater(len(results), 0)
        self.assertIn("timeout", results[0]["pattern"]["problem_type"])

    def test_07_record_adaptation(self):
        sp = SolutionPattern("CodeAgent", "timeout", "API timeout", "Backoff")
        self.indexer.index_pattern(sp)
        ok = self.indexer.record_adaptation(sp.id, True)
        self.assertTrue(ok)
        self.assertEqual(self.indexer.patterns[sp.id].adaptation_count, 1)

    def test_08_record_adaptation_nonexistent(self):
        ok = self.indexer.record_adaptation("nonexistent", True)
        self.assertFalse(ok)

    def test_09_reset(self):
        self.indexer.index_pattern(SolutionPattern("A", "t", "p", "s"))
        self.indexer.reset()
        self.assertEqual(self.indexer.count_patterns(), 0)

    def test_10_get_all_patterns(self):
        self.indexer.index_pattern(SolutionPattern("A", "t", "p", "s"))
        self.indexer.index_pattern(SolutionPattern("B", "t", "p", "s"))
        self.assertEqual(len(self.indexer.get_all_patterns()), 2)

    def test_11_empty_query(self):
        results = self.indexer.find_patterns("")
        self.assertEqual(len(results), 0)

    def test_12_persistence(self):
        self.indexer.index_pattern(
            SolutionPattern(
                "CodeAgent",
                "timeout",
                "API timeout",
                "Exponential backoff",
            )
        )
        new_indexer = SolutionPatternIndexer()
        self.assertEqual(new_indexer.count_patterns(), 1)
        new_indexer.reset()

    def test_13_singleton(self):
        inst = get_pattern_indexer()
        self.assertIs(inst, get_pattern_indexer())


class TestLearningBridge(unittest.TestCase):
    def setUp(self):
        self.indexer = SolutionPatternIndexer()
        self.indexer.reset()
        self.awareness = AgentAwarenessManager()
        self.awareness.reset()
        self.bridge = LearningBridge(self.indexer, self.awareness)

    def test_14_agent_solved_problem_indexes_pattern(self):
        self.bridge.agent_solved_problem(
            "CodeAgent",
            "backend",
            "API requests timing out",
            "Implement exponential backoff",
        )
        self.assertEqual(self.indexer.count_patterns(), 1)

    def test_15_agent_solved_problem_logs_decision(self):
        self.awareness.register_agent("CodeAgent", ["backend"])
        self.bridge.agent_solved_problem(
            "CodeAgent", "backend", "API timeout", "Exponential backoff", success=True
        )
        journal = self.awareness.get_journal("CodeAgent")
        self.assertEqual(len(journal.decisions), 1)
        self.assertTrue(journal.decisions[0].correct)

    def test_16_agent_needs_help_returns_patterns(self):
        self.bridge.agent_solved_problem(
            "CodeAgent",
            "backend",
            "API requests timing out",
            "Exponential backoff with jitter",
        )
        results = self.bridge.agent_needs_help(
            "ResearchAgent", "data", "How to handle API call timeouts?"
        )
        self.assertGreater(len(results), 0)

    def test_17_classify_timeout(self):
        self.assertEqual(
            self.bridge._classify_problem("API timeout"), "timeout_handling"
        )

    def test_18_classify_retry(self):
        self.assertEqual(self.bridge._classify_problem("Retry failed"), "retry_logic")

    def test_19_classify_parse(self):
        self.assertEqual(
            self.bridge._classify_problem("JSON parse error"), "parsing_error"
        )

    def test_20_classify_auth(self):
        self.assertEqual(
            self.bridge._classify_problem("Auth token expired"), "authentication"
        )

    def test_21_classify_api(self):
        self.assertEqual(
            self.bridge._classify_problem("API request failed"), "api_integration"
        )

    def test_22_classify_general(self):
        self.assertEqual(self.bridge._classify_problem("Something random"), "general")

    def test_23_get_stats(self):
        stats = self.bridge.get_stats()
        self.assertIn("total_patterns", stats)
        self.assertIn("adaptations", stats)

    def test_24_cross_agent_learning(self):
        self.bridge.agent_solved_problem(
            "CodeAgent",
            "backend",
            "API rate limiting",
            "Queue requests + exponential backoff",
        )
        results = self.bridge.agent_needs_help(
            "ResearchAgent", "data", "Manage API call limits"
        )
        self.assertGreater(len(results), 0)

    def test_25_bridge_learning_bridge_singleton(self):
        bridge = get_learning_bridge()
        self.assertIs(bridge, get_learning_bridge())


if __name__ == "__main__":
    unittest.main()
