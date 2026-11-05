"""Tests for Batch 2 Overkill Features: RAG, Cost Optimizer, Agent Debate, Tool Analytics."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestRAGEngine(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.rag_engine import get_rag_engine

        self.assertTrue(callable(get_rag_engine))

    def test_ingest_and_search(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        engine = RAGEngine()
        engine._docs.clear()
        result = engine.ingest(
            "Python is a programming language. It is used for AI and web development.",
            source="test.txt",
        )
        self.assertIn("doc_ids", result)
        self.assertGreater(len(result["doc_ids"]), 0)
        results = engine.query("Python AI")
        self.assertGreater(len(results), 0)
        self.assertIn("Python", results[0].content)

    def test_chunk_markdown(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        engine = RAGEngine()
        engine._docs.clear()
        md = "# Title\nSome content\n## Section\nMore content here"
        result = engine.ingest(md)
        self.assertIn("doc_ids", result)
        self.assertGreater(len(result["doc_ids"]), 0)

    def test_get_context(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        engine = RAGEngine()
        engine._docs.clear()
        engine.ingest("Machine learning is a subset of AI.", source="ml.txt")
        results = engine.query("machine learning")
        self.assertGreater(len(results), 0)
        ctx = " ".join(r.content for r in results)
        self.assertIn("Machine learning", ctx)

    def test_delete_document(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        engine = RAGEngine()
        engine._docs.clear()
        result = engine.ingest("Delete me")
        doc_id = result["doc_ids"][0]
        ok = engine.delete(doc_id)
        self.assertTrue(ok)
        self.assertEqual(len(engine.get_documents()), 0)

    def test_stats(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        engine = RAGEngine()
        engine._docs.clear()
        engine.ingest("Doc one", source="a.txt")
        engine.ingest("Doc two", source="b.txt")
        stats = engine.get_status()
        self.assertEqual(stats["documents"], 2)
        self.assertEqual(stats["chunks"], 2)


class TestCostOptimizer(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.cost_optimizer import get_cost_optimizer

        self.assertTrue(callable(get_cost_optimizer))

    def test_record_usage(self):
        from orbit.orbit.core.cost_optimizer import get_cost_optimizer

        opt = get_cost_optimizer()
        rec = opt.record_call("gpt-4o-mini", 1000, 500, task_type="chat")
        self.assertIn("cost_usd", rec)
        self.assertIn("daily_total", rec)

    def test_recommend(self):
        from orbit.orbit.core.cost_optimizer import get_cost_optimizer

        opt = get_cost_optimizer()
        recs = opt.get_recommendations()
        self.assertIsInstance(recs, list)

    def test_budget(self):
        from orbit.orbit.core.cost_optimizer import get_cost_optimizer

        opt = get_cost_optimizer()
        budget = opt.get_budget_status()
        self.assertIn("daily_limit", budget)
        self.assertIn("today_spent", budget)
        opt.set_budget(5.0)
        budget2 = opt.get_budget_status()
        self.assertEqual(budget2["daily_limit"], 5.0)

    def test_forecast(self):
        from orbit.orbit.core.cost_optimizer import get_cost_optimizer

        opt = get_cost_optimizer()
        result = opt.optimize_prompt(
            "Please help me write a simple Python function to add two numbers"
        )
        self.assertIn("original_tokens", result)
        self.assertIn("optimized_tokens", result)
        self.assertGreater(result["original_tokens"], 0)

    def test_stats(self):
        from orbit.orbit.core.cost_optimizer import get_cost_optimizer

        opt = get_cost_optimizer()
        opt.record_call("gpt-4o-mini", 500, 200, task_type="code")
        opt.record_call("ollama", 100, 50, task_type="chat")
        stats = opt.get_stats()
        self.assertGreater(stats["total_calls"], 0)
        self.assertIn("by_model", stats)


class TestAgentDebate(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.agent_debate import get_debate

        self.assertTrue(callable(get_debate))

    def test_basic_debate(self):
        from orbit.orbit.core.agent_debate import AgentDebate

        debate = AgentDebate(max_rounds=2, max_agents=2)
        debate.register_agent(
            "a1", "Alice", lambda p: {"argument": "AI is great", "confidence": 0.8}
        )
        debate.register_agent(
            "a2", "Bob", lambda p: {"argument": "AI is risky", "confidence": 0.7}
        )
        debate.register_judge(
            lambda p: {
                "winner": "Alice",
                "argument": "Balanced view",
                "confidence": 0.75,
            }
        )
        result = debate.debate("Is AI beneficial?")
        self.assertEqual(result.total_rounds, 2)
        self.assertEqual(result.winner, "Alice")
        self.assertGreater(result.final_confidence, 0)

    def test_debate_with_stances(self):
        from orbit.orbit.core.agent_debate import AgentDebate

        debate = AgentDebate(max_rounds=1)
        debate.register_agent("a1", "Pro", lambda p: "For argument")
        debate.register_agent("a2", "Con", lambda p: "Against argument")
        result = debate.debate("Test?", positions=["for", "against"])
        self.assertEqual(result.total_rounds, 1)

    def test_debate_no_agents(self):
        from orbit.orbit.core.agent_debate import AgentDebate

        debate = AgentDebate()
        result = debate.debate("Test?")
        self.assertIn("No agents", result.consensus)

    def test_debate_history(self):
        from orbit.orbit.core.agent_debate import AgentDebate

        debate = AgentDebate(max_rounds=1)
        debate.register_agent("a1", "A", lambda p: "arg")
        debate.debate("Q1?")
        debate.debate("Q2?")
        history = debate.get_history()
        self.assertEqual(len(history), 2)

    def test_stats(self):
        from orbit.orbit.core.agent_debate import AgentDebate

        debate = AgentDebate(max_rounds=1)
        debate.register_agent("a1", "A", lambda p: "arg")
        debate.register_agent("a2", "B", lambda p: "arg")
        debate.register_judge(
            lambda p: {"winner": "A", "argument": "x", "confidence": 0.6}
        )
        debate.debate("Q?")
        stats = debate.get_stats()
        self.assertEqual(stats["total_debates"], 1)
        self.assertEqual(stats["registered_agents"], 2)
        self.assertTrue(stats["has_judge"])


class TestToolAnalytics(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.tool_analytics import get_tool_analytics

        self.assertTrue(callable(get_tool_analytics))

    def test_record_and_stats(self):
        from orbit.orbit.core.tool_analytics import ToolAnalytics

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ta = ToolAnalytics(storage_file=path)
            ta.record("web_search", action="search", success=True, latency_ms=150)
            ta.record("web_search", action="search", success=True, latency_ms=200)
            ta.record(
                "web_search",
                action="search",
                success=False,
                error="Timeout",
                latency_ms=5000,
            )
            stats = ta.get_tool_stats("web_search")
            self.assertEqual(stats["total_calls"], 3)
            self.assertEqual(stats["successes"], 2)
            self.assertEqual(stats["failures"], 1)
            self.assertAlmostEqual(stats["success_rate"], 66.7, delta=0.1)
            self.assertIn("timeout", stats["error_breakdown"])
        finally:
            os.unlink(path)

    def test_health_score(self):
        from orbit.orbit.core.tool_analytics import ToolAnalytics

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ta = ToolAnalytics(storage_file=path)
            for _ in range(10):
                ta.record("good_tool", success=True, latency_ms=50)
            stats = ta.get_tool_stats("good_tool")
            self.assertAlmostEqual(stats["health_score"], 99.8, delta=0.5)
        finally:
            os.unlink(path)

    def test_error_categorization(self):
        from orbit.orbit.core.tool_analytics import ToolAnalytics

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ta = ToolAnalytics(storage_file=path)
            ta.record("t1", success=False, error="Connection refused")
            ta.record("t1", success=False, error="Rate limit exceeded")
            ta.record("t1", success=False, error="Permission denied")
            ta.record("t1", success=False, error="Syntax error in output")
            stats = ta.get_tool_stats("t1")
            cats = stats["error_breakdown"]
            self.assertIn("network", cats)
            self.assertIn("rate_limit", cats)
            self.assertIn("permission", cats)
            self.assertIn("parsing", cats)
        finally:
            os.unlink(path)

    def test_trend(self):
        from orbit.orbit.core.tool_analytics import ToolAnalytics

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ta = ToolAnalytics(storage_file=path)
            ta.record("t1", success=True, latency_ms=100)
            trend = ta.get_trend("t1", hours=24)
            self.assertEqual(trend["calls"], 1)
            self.assertEqual(trend["successes"], 1)
        finally:
            os.unlink(path)

    def test_all_stats(self):
        from orbit.orbit.core.tool_analytics import ToolAnalytics

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ta = ToolAnalytics(storage_file=path)
            ta.record("tool_a", success=True, latency_ms=100)
            ta.record("tool_b", success=True, latency_ms=200)
            stats = ta.get_all_stats()
            self.assertEqual(stats["total_invocations"], 2)
            self.assertEqual(stats["tool_count"], 2)
            self.assertIn("tool_a", stats["tools"])
        finally:
            os.unlink(path)


class TestBatch2Blueprints(unittest.TestCase):
    def test_server_imports_all_blueprints(self):
        from orbit.orbit.server import create_app

        app = create_app()
        names = list(app.blueprints)
        for bp in [
            "rag_bp",
            "cost_optimizer",
            "agent_debate",
            "tool_analytics",
            "skill_learning",
            "hybrid_memory",
            "smart_browser",
            "task_fanout",
            "moa",
            "streaming_tts",
            "marketplace_v2",
        ]:
            self.assertIn(bp, names, f"Blueprint '{bp}' missing")


if __name__ == "__main__":
    unittest.main()
