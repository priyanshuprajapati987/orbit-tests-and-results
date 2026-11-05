"""Tests for Batch 4 Overkill Features: Semantic Cache, Prompt Optimizer, Summarizer, Evaluator, Webhooks."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSemanticCache(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.semantic_cache import get_semantic_cache

        self.assertTrue(callable(get_semantic_cache))

    def test_store_and_lookup(self):
        from orbit.orbit.core.semantic_cache import SemanticCache

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            sc = SemanticCache(storage_file=path)
            sc.store("hello world", "hi there")
            hit = sc.lookup("hello world")
            self.assertIsNotNone(hit)
            self.assertEqual(hit.response, "hi there")
        finally:
            os.unlink(path)

    def test_semantic_similarity(self):
        from orbit.orbit.core.semantic_cache import SemanticCache

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            sc = SemanticCache(storage_file=path, similarity_threshold=0.5)
            sc.store("what is machine learning", "ML is a subset of AI")
            hit = sc.lookup("what is machine learning exactly")
            self.assertIsNotNone(hit)
        finally:
            os.unlink(path)

    def test_miss_on_different(self):
        from orbit.orbit.core.semantic_cache import SemanticCache

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            sc = SemanticCache(storage_file=path)
            sc.store("hello world", "response")
            hit = sc.lookup("quantum physics entanglement")
            self.assertIsNone(hit)
        finally:
            os.unlink(path)

    def test_invalidate(self):
        from orbit.orbit.core.semantic_cache import SemanticCache

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            sc = SemanticCache(storage_file=path)
            sc.store("test", "response")
            self.assertTrue(sc.invalidate("test"))
            self.assertIsNone(sc.lookup("test"))
        finally:
            os.unlink(path)

    def test_clear(self):
        from orbit.orbit.core.semantic_cache import SemanticCache

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            sc = SemanticCache(storage_file=path)
            sc.store("a", "1")
            sc.store("b", "2")
            self.assertEqual(sc.clear(), 2)
            self.assertEqual(sc.get_stats()["total_entries"], 0)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.semantic_cache import SemanticCache

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            sc = SemanticCache(storage_file=path)
            sc.store("x", "y")
            sc.lookup("x")
            sc.lookup("z")
            stats = sc.get_stats()
            self.assertEqual(stats["hits"], 1)
            self.assertEqual(stats["misses"], 1)
        finally:
            os.unlink(path)


class TestPromptOptimizer(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.prompt_optimizer import get_optimizer

        self.assertTrue(callable(get_optimizer))

    def test_analyze_prompt(self):
        from orbit.orbit.core.prompt_optimizer import PromptOptimizer

        with tempfile.TemporaryDirectory() as td:
            po = PromptOptimizer(data_dir=Path(td))
            analysis = po.analyze("Write a Python function to sort a list")
            self.assertIsNotNone(analysis)
            self.assertGreater(analysis.overall_score, 0)
            self.assertIn(analysis.task_type, ["code", "reasoning", "creative", "research", "summary", "analysis", "data", "general"])

    def test_optimize(self):
        from orbit.orbit.core.prompt_optimizer import PromptOptimizer

        with tempfile.TemporaryDirectory() as td:
            po = PromptOptimizer(data_dir=Path(td))
            result = po.optimize("Write a simple function")
            self.assertIsNotNone(result.optimized)
            self.assertGreater(result.overall_score, 0)
            self.assertTrue(result.template_applied)

    def test_detect_task_type(self):
        from orbit.orbit.core.prompt_optimizer import PromptOptimizer

        with tempfile.TemporaryDirectory() as td:
            po = PromptOptimizer(data_dir=Path(td))
            task_type, confidence = po.detect_task_type("write a python function to sort data")
            self.assertEqual(task_type, "code")
            self.assertGreater(confidence, 0)

    def test_get_templates(self):
        from orbit.orbit.core.prompt_optimizer import PromptOptimizer

        with tempfile.TemporaryDirectory() as td:
            po = PromptOptimizer(data_dir=Path(td))
            templates = po.get_templates()
            self.assertIsInstance(templates, dict)
            self.assertIn("general", templates)

    def test_stats(self):
        from orbit.orbit.core.prompt_optimizer import PromptOptimizer

        with tempfile.TemporaryDirectory() as td:
            po = PromptOptimizer(data_dir=Path(td))
            po.optimize("test prompt")
            stats = po.get_stats()
            self.assertEqual(stats["total_optimizations"], 1)


class TestConversationSummarizer(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.conversation_summarizer import (
            get_conversation_summarizer,
        )

        self.assertTrue(callable(get_conversation_summarizer))

    def test_summarize(self):
        from orbit.orbit.core.conversation_summarizer import ConversationSummarizer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cs = ConversationSummarizer(storage_file=path, keep_recent=2)
            turns = [
                {
                    "role": "user",
                    "content": "What is artificial intelligence and how does it work in practice?",
                },
                {
                    "role": "assistant",
                    "content": "AI is a field of computer science that creates intelligent machines capable of learning.",
                },
                {
                    "role": "user",
                    "content": "Tell me about machine learning algorithms and their importance for businesses.",
                },
                {
                    "role": "assistant",
                    "content": "Machine learning is a subset of AI that enables systems to learn from data patterns.",
                },
                {
                    "role": "user",
                    "content": "How do neural networks process information in deep learning?",
                },
                {
                    "role": "assistant",
                    "content": "Neural networks are inspired by biological brains and process data through layers.",
                },
                {
                    "role": "user",
                    "content": "What are the best programming languages for AI development today?",
                },
                {
                    "role": "assistant",
                    "content": "Python is the most popular, with R and Julia also used in AI research.",
                },
            ]
            result = cs.summarize_conversation("conv1", turns)
            self.assertGreater(result.total_turns, 0)
        finally:
            os.unlink(path)

    def test_compressed_context(self):
        from orbit.orbit.core.conversation_summarizer import ConversationSummarizer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cs = ConversationSummarizer(storage_file=path)
            turns = [
                {"role": "user", "content": f"Message {i} about topic {i % 3}"}
                for i in range(30)
            ]
            cs.summarize_conversation("c1", turns)
            ctx = cs.get_compressed_context("c1")
            self.assertTrue(len(ctx) > 0)
        finally:
            os.unlink(path)

    def test_topics(self):
        from orbit.orbit.core.conversation_summarizer import ConversationSummarizer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cs = ConversationSummarizer(storage_file=path, keep_recent=2)
            turns = [
                {
                    "role": "user",
                    "content": f"Message about AI machine learning deep learning neural networks topic {i}",
                }
                for i in range(12)
            ]
            cs.summarize_conversation("c1", turns)
            topics = cs.get_topics("c1")
            self.assertGreater(len(topics), 0)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.conversation_summarizer import ConversationSummarizer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cs = ConversationSummarizer(storage_file=path)
            cs.summarize_conversation("c1", [{"role": "user", "content": "test"}])
            stats = cs.get_stats()
            self.assertEqual(stats["total_conversations"], 1)
        finally:
            os.unlink(path)


class TestResponseEvaluator(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.response_evaluator import (
            get_response_evaluator,
        )

        self.assertTrue(callable(get_response_evaluator))

    def test_evaluate(self):
        from orbit.orbit.core.response_evaluator import ResponseEvaluator

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ev = ResponseEvaluator(storage_file=path)
            result = ev.evaluate(
                "What is AI?",
                "AI is artificial intelligence.",
                context="AI is a field of computer science.",
            )
            self.assertGreater(result.overall_score, 0)
            self.assertIn("relevance", result.scores)
        finally:
            os.unlink(path)

    def test_hallucination_detection(self):
        from orbit.orbit.core.response_evaluator import ResponseEvaluator

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ev = ResponseEvaluator(storage_file=path)
            result = ev.evaluate(
                "What is 2+2?",
                "The moon is made of cheese and cats can fly.",
                context="2+2 equals 4.",
            )
            self.assertGreater(len(result.flags), 0)
        finally:
            os.unlink(path)

    def test_agent_stats(self):
        from orbit.orbit.core.response_evaluator import ResponseEvaluator

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ev = ResponseEvaluator(storage_file=path)
            ev.evaluate("q1", "a1", agent_id="COD")
            ev.evaluate("q2", "a2", agent_id="COD")
            stats = ev.get_agent_stats("COD")
            self.assertEqual(stats["evaluations"], 2)
        finally:
            os.unlink(path)

    def test_recent_and_lowest(self):
        from orbit.orbit.core.response_evaluator import ResponseEvaluator

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ev = ResponseEvaluator(storage_file=path)
            ev.evaluate("q", "good response")
            recent = ev.get_recent()
            lowest = ev.get_lowest()
            self.assertEqual(len(recent), 1)
            self.assertEqual(len(lowest), 1)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.response_evaluator import ResponseEvaluator

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ev = ResponseEvaluator(storage_file=path)
            ev.evaluate("q", "a")
            stats = ev.get_stats()
            self.assertEqual(stats["total"], 1)
        finally:
            os.unlink(path)


class TestWebhookSystem(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.webhook_system import get_webhook_system

        self.assertTrue(callable(get_webhook_system))

    def test_register_and_list(self):
        from orbit.orbit.core.webhook_system import WebhookSystem

        with tempfile.TemporaryDirectory() as td:
            ws = WebhookSystem(data_dir=Path(td))
            sub = ws.register("test_hook", "http://example.com", ["task.completed"])
            self.assertIsNotNone(sub.webhook_id)
            subs = ws.list_webhooks()
            self.assertEqual(len(subs), 1)

    def test_unregister(self):
        from orbit.orbit.core.webhook_system import WebhookSystem

        with tempfile.TemporaryDirectory() as td:
            ws = WebhookSystem(data_dir=Path(td))
            sub = ws.register("test_hook", "http://example.com", ["test"])
            self.assertTrue(ws.unregister(sub.webhook_id))
            self.assertEqual(len(ws.list_webhooks()), 0)

    def test_receive_event(self):
        from orbit.orbit.core.webhook_system import WebhookSystem

        with tempfile.TemporaryDirectory() as td:
            ws = WebhookSystem(data_dir=Path(td))
            ws.register("test_hook", "http://example.com/hook", ["task.completed"])
            dispatched = ws.receive_event("task.completed", {"task": "test"})
            self.assertEqual(len(dispatched), 1)

    def test_events(self):
        from orbit.orbit.core.webhook_system import WebhookSystem

        with tempfile.TemporaryDirectory() as td:
            ws = WebhookSystem(data_dir=Path(td))
            ws.register("test_hook", "http://example.com", ["*"])
            ws.receive_event("test.event", {})
            log = ws.get_events()
            self.assertEqual(len(log), 1)

    def test_stats(self):
        from orbit.orbit.core.webhook_system import WebhookSystem

        with tempfile.TemporaryDirectory() as td:
            ws = WebhookSystem(data_dir=Path(td))
            ws.register("test_hook", "http://example.com", ["test"])
            stats = ws.get_stats()
            self.assertEqual(stats["total_webhooks"], 1)


class TestBatch4Blueprints(unittest.TestCase):
    def test_all_registered(self):
        from orbit.orbit.server import create_app

        app = create_app()
        names = list(app.blueprints)
        for bp in [
            "semantic_cache",
            "prompt_optimizer_bp",
            "conversation_summarizer",
            "response_evaluator",
            "webhook_system_bp",
        ]:
            self.assertIn(bp, names, f"Blueprint '{bp}' missing")


if __name__ == "__main__":
    unittest.main()
