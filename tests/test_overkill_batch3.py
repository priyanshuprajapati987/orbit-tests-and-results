"""Tests for Batch 3 Overkill Features: Self-Improvement, Memory Consolidation, Request Tracing."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSelfImprovement(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.self_improvement import (
            get_self_improvement,
        )

        self.assertTrue(callable(get_self_improvement))

    def test_add_feedback(self):
        from orbit.orbit.core.self_improvement import SelfImprovement

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            si = SelfImprovement(storage_file=path)
            fb = si.add_feedback(
                "COD", "code_gen", "write a function", "def f(): pass", 0.85, "Good"
            )
            self.assertEqual(fb.agent_id, "COD")
            self.assertEqual(fb.rating, "positive")
        finally:
            os.unlink(path)

    def test_create_plan(self):
        from orbit.orbit.core.self_improvement import SelfImprovement

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            si = SelfImprovement(storage_file=path)
            plan = si.create_plan(
                "COD", "Improve code quality", ["strategy1", "strategy2"]
            )
            self.assertEqual(plan.agent_id, "COD")
            self.assertEqual(plan.status, "active")
        finally:
            os.unlink(path)

    def test_score_trend(self):
        from orbit.orbit.core.self_improvement import SelfImprovement

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            si = SelfImprovement(storage_file=path)
            for i in range(10):
                si.add_feedback("RES", "research", "", "", 0.5 + i * 0.05)
            trend = si.get_agent_score_trend("RES")
            self.assertEqual(trend["data_points"], 10)
            self.assertGreater(trend["avg_score"], 0)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.self_improvement import SelfImprovement

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            si = SelfImprovement(storage_file=path)
            si.add_feedback("A", "", "", "", 0.8)
            si.add_feedback("B", "", "", "", 0.3)
            stats = si.get_stats()
            self.assertEqual(stats["total_feedback"], 2)
            self.assertEqual(stats["by_rating"]["positive"], 1)
            self.assertEqual(stats["by_rating"]["negative"], 1)
        finally:
            os.unlink(path)


class TestMemoryConsolidation(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.memory_consolidation import (
            get_memory_consolidation,
        )

        self.assertTrue(callable(get_memory_consolidation))

    def test_extract_facts(self):
        from orbit.orbit.core.memory_consolidation import MemoryConsolidation

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mc = MemoryConsolidation(storage_file=path)
            memories = [
                {"id": "m1", "content": "User prefers dark mode in all applications."},
                {"id": "m2", "content": "Always use VS Code for programming tasks."},
            ]
            facts = mc.extract_facts(memories)
            self.assertGreater(len(facts), 0)
            self.assertTrue(
                any("dark mode" in f.fact or "VS Code" in f.fact for f in facts)
            )
        finally:
            os.unlink(path)

    def test_merge_duplicates(self):
        from orbit.orbit.core.memory_consolidation import MemoryConsolidation

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mc = MemoryConsolidation(storage_file=path)
            mc.extract_facts(
                [
                    {
                        "id": "m1",
                        "content": "User prefers dark mode in the applications always.",
                    },
                    {
                        "id": "m2",
                        "content": "User prefers dark mode in the applications always and more.",
                    },
                ]
            )
            merged = mc.merge_duplicates(similarity_threshold=0.5)
            self.assertGreaterEqual(merged, 0)
        finally:
            os.unlink(path)

    def test_consolidate(self):
        from orbit.orbit.core.memory_consolidation import MemoryConsolidation

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mc = MemoryConsolidation(storage_file=path)
            memories = [
                {"id": "m1", "content": "Important meeting tomorrow at 3pm."},
                {"id": "m2", "content": "User prefers concise responses always."},
            ]
            report = mc.consolidate(memories)
            self.assertGreater(report.facts_extracted, 0)
        finally:
            os.unlink(path)

    def test_search_facts(self):
        from orbit.orbit.core.memory_consolidation import MemoryConsolidation

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mc = MemoryConsolidation(storage_file=path)
            mc.extract_facts(
                [
                    {
                        "id": "m1",
                        "content": "User always prefers dark mode in applications.",
                    }
                ]
            )
            results = mc.search_facts("dark mode")
            self.assertGreater(len(results), 0)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.memory_consolidation import MemoryConsolidation

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mc = MemoryConsolidation(storage_file=path)
            mc.extract_facts(
                [{"id": "m1", "content": "Important deadline Friday must complete."}]
            )
            stats = mc.get_stats()
            self.assertEqual(stats["total_facts"], 1)
        finally:
            os.unlink(path)


class TestRequestTracing(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.request_tracing import get_tracer

        self.assertTrue(callable(get_tracer))

    def test_start_and_end_trace(self):
        from orbit.orbit.core.request_tracing import RequestTracer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            tracer = RequestTracer(storage_file=path)
            trace_id = tracer.start_trace("Hello world", "QUEEN")
            self.assertIsNotNone(trace_id)
            span_id = tracer.start_span(trace_id, "llm_call", "router")
            self.assertIsNotNone(span_id)
            tracer.end_span(trace_id, span_id, status="ok")
            tracer.end_trace(trace_id, status="ok", result="Response")
            trace = tracer.get_trace(trace_id)
            self.assertIsNotNone(trace)
            self.assertEqual(trace["status"], "ok")
            self.assertGreater(len(trace["spans"]), 0)
        finally:
            os.unlink(path)

    def test_search_traces(self):
        from orbit.orbit.core.request_tracing import RequestTracer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            tracer = RequestTracer(storage_file=path)
            tid = tracer.start_trace("Research AI news", "RES")
            tracer.end_trace(tid, status="ok")
            results = tracer.search_traces(query="AI")
            self.assertEqual(len(results), 1)
        finally:
            os.unlink(path)

    def test_error_traces(self):
        from orbit.orbit.core.request_tracing import RequestTracer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            tracer = RequestTracer(storage_file=path)
            tid = tracer.start_trace("fail task")
            tracer.end_trace(tid, status="error", error="Something went wrong")
            errors = tracer.get_error_traces()
            self.assertEqual(len(errors), 1)
        finally:
            os.unlink(path)

    def test_slowest(self):
        from orbit.orbit.core.request_tracing import RequestTracer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            tracer = RequestTracer(storage_file=path)
            tid = tracer.start_trace("slow task")
            import time

            time.sleep(0.01)
            tracer.end_trace(tid, status="ok")
            slow = tracer.get_slowest(5)
            self.assertGreater(len(slow), 0)
            self.assertGreater(slow[0]["total_duration_ms"], 0)
        finally:
            os.unlink(path)

    def test_stats(self):
        from orbit.orbit.core.request_tracing import RequestTracer

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            tracer = RequestTracer(storage_file=path)
            tid = tracer.start_trace("test", "COD")
            tracer.end_trace(tid, status="ok")
            stats = tracer.get_stats()
            self.assertEqual(stats["total_traces"], 1)
            self.assertIn("COD", stats["by_agent"])
        finally:
            os.unlink(path)


class TestBatch3Blueprints(unittest.TestCase):
    def test_all_blueprints_registered(self):
        from orbit.orbit.server import create_app

        app = create_app()
        names = list(app.blueprints)
        for bp in [
            "workflow",
            "self_improvement",
            "memory_consolidation",
            "request_tracing",
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
