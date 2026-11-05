"""
Tests for ORBIT Overkill Features (Day 4).
Skill Learning, Hybrid Memory, Smart Browser, Task Fan-Out,
Mixture of Agents, Streaming TTS, Skills Marketplace V2.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSkillLearning(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.skill_learning import (
            find_skills,
            get_skill_dashboard,
            get_skill_learner,
            get_skill_store,
        )

        self.assertTrue(callable(get_skill_learner))
        self.assertTrue(callable(get_skill_store))
        self.assertTrue(callable(find_skills))
        self.assertTrue(callable(get_skill_dashboard))

    def test_store_add_and_get(self):
        from orbit.orbit.core.skill_learning import Skill, SkillStore

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = SkillStore(path)
            skill = Skill(
                name="test_skill", description="A test skill", category="testing"
            )
            added = store.add(skill)
            self.assertEqual(added.name, "test_skill")
            retrieved = store.get(added.id)
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.name, "test_skill")
        finally:
            os.unlink(path)

    def test_store_search(self):
        from orbit.orbit.core.skill_learning import Skill, SkillStore

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = SkillStore(path)
            store.add(
                Skill(
                    name="web_search",
                    description="Search the web",
                    tags=["search", "web"],
                )
            )
            store.add(Skill(name="file_read", description="Read a file", tags=["file"]))
            results = store.search("search")
            self.assertGreater(len(results), 0)
            self.assertEqual(results[0].name, "web_search")
        finally:
            os.unlink(path)

    def test_store_stats(self):
        from orbit.orbit.core.skill_learning import Skill, SkillStore

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            store = SkillStore(path)
            store.add(Skill(name="s1", description="d1"))
            store.add(Skill(name="s2", description="d2"))
            stats = store.get_stats()
            self.assertEqual(stats["total_skills"], 2)
        finally:
            os.unlink(path)

    def test_record_task(self):
        from orbit.orbit.core.skill_learning import SkillLearner

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            learner = SkillLearner(store_path=path)
            trace = learner.record_task(
                task_id="t1",
                description="Search the web for AI news",
                steps=[{"action": "search web"}, {"action": "read page"}],
                result="Found 5 articles",
                success=True,
                duration_ms=1500,
            )
            self.assertEqual(trace.task_id, "t1")
            self.assertTrue(trace.success)
            dashboard = learner.get_dashboard()
            self.assertEqual(dashboard["traces_recorded"], 1)
        finally:
            os.unlink(path)

    def test_extractor_repeated_patterns(self):
        from orbit.orbit.core.skill_learning import SkillExtractor, SkillTrace

        extractor = SkillExtractor()
        traces = [
            SkillTrace(
                task_id=f"t{i}",
                steps=[{"action": "search web"}, {"action": "read page"}],
                success=True,
            )
            for i in range(5)
        ]
        patterns = extractor.detect_repeated_patterns(traces, min_occurrences=3)
        self.assertGreater(len(patterns), 0)
        self.assertGreaterEqual(patterns[0]["occurrences"], 3)


class TestHybridMemory(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.hybrid_memory import get_hybrid_memory

        self.assertTrue(callable(get_hybrid_memory))

    def test_add_and_search(self):
        from orbit.orbit.core.hybrid_memory import HybridMemory

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mem = HybridMemory(storage_file=path)
            entry_id = mem.add("I love Python programming", source="user")
            self.assertIsInstance(entry_id, str)
            results = mem.search("Python")
            self.assertGreater(len(results), 0)
            self.assertIn("Python", results[0]["content"])
        finally:
            os.unlink(path)

    def test_entity_extraction(self):
        from orbit.orbit.core.hybrid_memory import _extract_entities

        entities = _extract_entities(
            "Contact me at test@example.com or visit https://example.com"
        )
        self.assertGreater(len(entities), 0)

    def test_stats(self):
        from orbit.orbit.core.hybrid_memory import HybridMemory

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mem = HybridMemory(storage_file=path)
            mem.add("Test memory 1")
            mem.add("Test memory 2")
            stats = mem.get_stats()
            self.assertEqual(stats["total_memories"], 2)
        finally:
            os.unlink(path)

    def test_temporal_context(self):
        from orbit.orbit.core.hybrid_memory import HybridMemory

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mem = HybridMemory(storage_file=path)
            mem.add("Recent memory")
            ctx = mem.get_temporal_context(hours=24)
            self.assertGreater(len(ctx), 0)
        finally:
            os.unlink(path)

    def test_entity_graph(self):
        from orbit.orbit.core.hybrid_memory import HybridMemory

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mem = HybridMemory(storage_file=path)
            mem.add("Email test@example.com about project")
            mem.add("Call 555-1234 about project")
            graph = mem.get_entity_graph()
            self.assertIsInstance(graph, dict)
        finally:
            os.unlink(path)


class TestSmartBrowser(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.tools.smart_browser import _PLAYWRIGHT_AVAILABLE, SmartBrowser

        sb = SmartBrowser()
        # Don't assume playwright is/isn't installed in the test env —
        # assert the availability flag is consistent with the module state.
        self.assertEqual(sb.is_available(), _PLAYWRIGHT_AVAILABLE)

    def test_plan_steps(self):
        from orbit.orbit.tools.smart_browser import SmartBrowser

        sb = SmartBrowser()
        steps = sb._plan_steps("Go to google.com and search for AI")
        self.assertGreater(len(steps), 0)
        self.assertEqual(steps[0]["action"], "navigate")


class TestTaskFanOut(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.task_fanout import get_fanout

        self.assertTrue(callable(get_fanout))

    def test_execute(self):
        from orbit.orbit.core.task_fanout import TaskFanOut

        fanout = TaskFanOut(max_workers=3)
        result = fanout.execute(
            goal="Test parallel execution",
            tasks=[
                {"description": "Task 1", "fn": lambda: "result1", "args": ()},
                {"description": "Task 2", "fn": lambda: "result2", "args": ()},
            ],
        )
        self.assertEqual(result.success_count, 2)
        self.assertEqual(result.failure_count, 0)
        self.assertEqual(len(result.subtasks), 2)

    def test_execute_with_failure(self):
        from orbit.orbit.core.task_fanout import TaskFanOut

        def fail_fn():
            raise RuntimeError("fail")

        fanout = TaskFanOut()
        result = fanout.execute(
            goal="Test failure handling",
            tasks=[
                {"description": "Success task", "fn": lambda: "ok", "args": ()},
                {"description": "Fail task", "fn": fail_fn, "args": ()},
            ],
        )
        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.failure_count, 1)


class TestMixtureOfAgents(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.mixture_of_agents import get_moa

        self.assertTrue(callable(get_moa))

    def test_register_and_query(self):
        from orbit.orbit.core.mixture_of_agents import MixtureOfAgents

        moa = MixtureOfAgents()
        moa.register_provider("model_a", lambda p: f"Answer A: {p}")
        moa.register_provider("model_b", lambda p: f"Answer B: {p}")
        result = moa.query("What is 2+2?", strategy="synthesis")
        self.assertEqual(result.query, "What is 2+2?")
        self.assertEqual(len(result.responses), 2)
        self.assertTrue(len(result.final_answer) > 0)

    def test_voting_strategy(self):
        from orbit.orbit.core.mixture_of_agents import MixtureOfAgents

        moa = MixtureOfAgents()
        moa.register_provider("m1", lambda p: "4")
        moa.register_provider("m2", lambda p: "4")
        moa.register_provider("m3", lambda p: "5")
        result = moa.query("What is 2+2?", strategy="voting")
        self.assertEqual(len(result.responses), 3)

    def test_providers_list(self):
        from orbit.orbit.core.mixture_of_agents import MixtureOfAgents

        moa = MixtureOfAgents()
        moa.register_provider("test_model", lambda p: "ok")
        providers = moa.get_providers()
        self.assertIn("test_model", providers)


class TestStreamingTTS(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.streaming_tts import get_streaming_tts

        self.assertTrue(callable(get_streaming_tts))

    def test_engines_detection(self):
        from orbit.orbit.streaming_tts import StreamingTTS

        tts = StreamingTTS()
        engines = tts.list_engines()
        self.assertIsInstance(engines, dict)
        self.assertIn("edge_tts", engines)


class TestSkillsMarketplaceV2(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.skills_marketplace_v2 import (
            get_marketplace,
        )

        self.assertTrue(callable(get_marketplace))

    def test_publish_and_search(self):
        from orbit.orbit.core.skills_marketplace_v2 import SkillsMarketplace

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mp = SkillsMarketplace(storage_file=path)
            skill_id = mp.publish("Test Skill", "A test skill", {"code": "print('hi')"})
            self.assertIsNotNone(skill_id)
            results = mp.search("Test")
            self.assertGreater(len(results), 0)
        finally:
            os.unlink(path)

    def test_featured_skills(self):
        from orbit.orbit.core.skills_marketplace_v2 import SkillsMarketplace

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mp = SkillsMarketplace(storage_file=path)
            featured = mp.get_featured()
            self.assertIsInstance(featured, list)
        finally:
            os.unlink(path)

    def test_hubs(self):
        from orbit.orbit.core.skills_marketplace_v2 import SkillsMarketplace

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            mp = SkillsMarketplace(storage_file=path)
            hubs = mp.get_hubs()
            self.assertGreater(len(hubs), 0)
        finally:
            os.unlink(path)


class TestBlueprintRegistration(unittest.TestCase):
    def test_server_imports_new_blueprints(self):
        from orbit.orbit.server import create_app

        app = create_app()
        blueprint_names = [name for name in app.blueprints]
        expected = [
            "skill_learning",
            "hybrid_memory",
            "smart_browser",
            "task_fanout",
            "moa",
            "streaming_tts",
            "marketplace_v2",
        ]
        for bp in expected:
            self.assertIn(bp, blueprint_names, f"Blueprint '{bp}' not registered")


if __name__ == "__main__":
    unittest.main()
