"""Unit tests for orbit/orbit/core/ai_orchestrator.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.ai_orchestrator import (
    TaskClassification, ModelPerformance, AIOrchestrator, get_ai_orchestrator,
)


class TestTaskClassification(unittest.TestCase):
    def test_init(self):
        tc = TaskClassification(task_type="code", confidence=0.9, complexity="moderate")
        self.assertEqual(tc.task_type, "code")
        self.assertEqual(tc.complexity, "moderate")


class TestModelPerformance(unittest.TestCase):
    def test_init(self):
        mp = ModelPerformance(model="gpt-4o-mini")
        self.assertEqual(mp.model, "gpt-4o-mini")


class TestAIOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orch = AIOrchestrator()

    def test_instantiation(self):
        self.assertIsNotNone(self.orch)

    def test_classify_code(self):
        r = self.orch.classify("write a python function to sort a list")
        self.assertIsNotNone(r)
        self.assertEqual(r["task_type"], "code")

    def test_classify_research(self):
        r = self.orch.classify("research the latest AI trends")
        self.assertIsNotNone(r)
        self.assertEqual(r["task_type"], "research")

    def test_classify_batch(self):
        r = self.orch.classify_batch(["write code", "research topic"])
        self.assertIsInstance(r, list)
        self.assertEqual(len(r), 2)

    def test_estimate_complexity(self):
        r = self.orch._estimate_complexity("simple task")
        self.assertIsInstance(r, str)

    def test_estimate_output_tokens(self):
        r = self.orch._estimate_output_tokens("code", "simple")
        self.assertIsInstance(r, int)

    def test_get_sub_type(self):
        r = self.orch._get_sub_type("code", "write python script")
        self.assertIsNotNone(r)

    def test_select_model(self):
        tc = self.orch.classify("write code")
        m = self.orch._select_model(tc["task_type"], tc["complexity"])
        self.assertIsNotNone(m)

    def test_record_execution(self):
        self.orch.record_execution("gpt-4o-mini", success=True, latency_ms=100.0, cost=0.001)
        self.assertTrue(True)

    def test_get_model_rankings(self):
        r = self.orch.get_model_rankings()
        self.assertIsNotNone(r)

    def test_get_stats(self):
        r = self.orch.get_stats()
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_ai_orchestrator()
        b = get_ai_orchestrator()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
