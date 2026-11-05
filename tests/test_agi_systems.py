"""Tests for all 5 AGI systems: SelfReflection, WorldModel, GoalAutonomy, MemoryConsolidator, MetaCognition."""

import os
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


class TestSelfReflection(unittest.TestCase):
    def test_singleton(self):
        from orbit.orbit.core.self_reflection import get_reflection_engine

        r1 = get_reflection_engine()
        r2 = get_reflection_engine()
        self.assertIs(r1, r2)

    def test_reflect_basic(self):
        from orbit.orbit.core.self_reflection import get_reflection_engine

        engine = get_reflection_engine()
        improved, critique = engine.reflect(
            "What is 2+2?", "The answer is 4.", "reasoning"
        )
        self.assertIsInstance(improved, str)
        self.assertIsInstance(critique, str)
        self.assertGreater(len(critique), 0)

    def test_reflect_returns_original_when_good(self):
        from orbit.orbit.core.self_reflection import get_reflection_engine

        engine = get_reflection_engine()
        response = "The capital of France is Paris. Confidence: high."
        improved, _critique = engine.reflect("Capital of France?", response, "factual")
        # Good response should stay mostly the same
        self.assertIn("Paris", improved)

    def test_heuristic_score(self):
        from orbit.orbit.core.self_reflection import get_reflection_engine

        engine = get_reflection_engine()
        scores = engine._heuristic_score(
            "What is 2+2?", "The answer is 4.", "reasoning"
        )
        self.assertIn("completeness", scores)
        self.assertIn("honesty", scores)
        self.assertGreater(scores["completeness"], 0)

    def test_stats(self):
        from orbit.orbit.core.self_reflection import get_reflection_engine

        engine = get_reflection_engine()
        stats = engine.get_stats()
        self.assertIn("total_reflected", stats)
        self.assertIn("improvement_rate", stats)

    def test_weak_areas(self):
        from orbit.orbit.core.self_reflection import get_reflection_engine

        engine = get_reflection_engine()
        areas = engine.get_weak_areas()
        self.assertIsInstance(areas, list)

    def test_convenience_function(self):
        from orbit.orbit.core.self_reflection import reflect_on_response

        improved, critique = reflect_on_response(
            "test query", "test response", "general"
        )
        self.assertIsInstance(improved, str)
        self.assertIsInstance(critique, str)


class TestWorldModel(unittest.TestCase):
    def test_singleton(self):
        from orbit.orbit.core.world_model import get_world_model

        w1 = get_world_model()
        w2 = get_world_model()
        self.assertIs(w1, w2)

    def test_add_entity(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        e = wm.add_entity("TestProject_999", "project", {"status": "active"})
        self.assertEqual(e.name, "TestProject_999")
        self.assertEqual(e.type, "project")

    def test_get_entity(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        wm.add_entity("TestEntity_999", "tool")
        e = wm.get_entity("TestEntity_999")
        self.assertIsNotNone(e)

    def test_add_relation(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        r = wm.add_relation("Source_999", "Target_999", "works_on")
        self.assertEqual(r.source, "Source_999")
        self.assertEqual(r.relation_type, "works_on")

    def test_get_entity_relations(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        wm.add_relation("RelA_999", "RelB_999", "uses")
        rels = wm.get_entity_relations("RelA_999")
        self.assertGreater(len(rels), 0)

    def test_add_goal(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        g = wm.add_goal("Test goal 999", priority="high")
        self.assertEqual(g.description, "Test goal 999")
        self.assertEqual(g.priority, "high")

    def test_get_goals_summary(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        summary = wm.get_goals_summary()
        self.assertIsInstance(summary, str)

    def test_add_event(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        wm.add_event("Test event 999", entities=["TestEntity_999"])
        events = wm.get_recent_events(hours=1)
        self.assertGreater(len(events), 0)

    def test_extract_from_conversation(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        result = wm.extract_from_conversation(
            "I need to finish the API project",
            "Sure, let me help with the API project.",
        )
        self.assertIn("entities", result)
        self.assertIn("goals", result)

    def test_stats(self):
        from orbit.orbit.core.world_model import get_world_model

        stats = get_world_model().get_stats()
        self.assertIn("entities", stats)
        self.assertIn("relations", stats)
        self.assertIn("goals", stats)

    def test_get_context_for_query(self):
        from orbit.orbit.core.world_model import get_world_model

        wm = get_world_model()
        wm.add_entity("Python", "technology")
        ctx = wm.get_context_for_query("python code")
        self.assertIn("Python", ctx)


class TestGoalAutonomy(unittest.TestCase):
    def test_singleton(self):
        from orbit.orbit.core.goal_autonomy import get_goal_engine

        g1 = get_goal_engine()
        g2 = get_goal_engine()
        self.assertIs(g1, g2)

    def test_infer_explicit_goals(self):
        from orbit.orbit.core.goal_autonomy import get_goal_engine

        engine = get_goal_engine()
        goals = engine.infer_goals("I need to deploy the API by Friday")
        self.assertGreater(len(goals), 0)
        self.assertGreater(goals[0].confidence, 0.5)

    def test_infer_inferred_goals(self):
        from orbit.orbit.core.goal_autonomy import get_goal_engine

        engine = get_goal_engine()
        goals = engine.infer_goals("I'm working on the frontend build")
        self.assertGreater(len(goals), 0)

    def test_decompose_goal(self):
        from orbit.orbit.core.goal_autonomy import get_goal_engine

        engine = get_goal_engine()
        goals = engine.infer_goals("I need to deploy the app")
        if goals:
            self.assertIsInstance(goals[0].sub_tasks, list)

    def test_proactive_suggestions(self):
        from orbit.orbit.core.goal_autonomy import get_goal_engine

        engine = get_goal_engine()
        suggestions = engine.get_proactive_suggestions()
        self.assertIsInstance(suggestions, list)

    def test_get_goals(self):
        from orbit.orbit.core.goal_autonomy import get_goal_engine

        engine = get_goal_engine()
        goals = engine.get_goals()
        self.assertIsInstance(goals, list)

    def test_stats(self):
        from orbit.orbit.core.goal_autonomy import get_goal_engine

        stats = get_goal_engine().get_stats()
        self.assertIn("total_goals", stats)
        self.assertIn("active", stats)

    def test_get_summary(self):
        from orbit.orbit.core.goal_autonomy import get_goal_engine

        summary = get_goal_engine().get_summary()
        self.assertIsInstance(summary, str)


class TestMemoryConsolidator(unittest.TestCase):
    def test_singleton(self):
        from orbit.orbit.core.memory_consolidator import get_consolidator

        c1 = get_consolidator()
        c2 = get_consolidator()
        self.assertIs(c1, c2)

    def test_add_memory(self):
        from orbit.orbit.core.memory_consolidator import get_consolidator

        c = get_consolidator()
        m = c.add_memory("Test memory content 999", "conversation", 0.7)
        self.assertEqual(m.content, "Test memory content 999")
        self.assertEqual(m.importance, 0.7)

    def test_recall(self):
        from orbit.orbit.core.memory_consolidator import get_consolidator

        c = get_consolidator()
        c.add_memory("Quantum computing uses qubits", "fact", 0.8)
        memories = c.recall("quantum computing")
        self.assertIsInstance(memories, list)

    def test_consolidate(self):
        from orbit.orbit.core.memory_consolidator import get_consolidator

        c = get_consolidator()
        # Add some memories to trigger consolidation
        for i in range(6):
            c.add_memory(f"Consolidation test memory {i} 999", "conversation", 0.5)
        # Reset cooldown so consolidation actually runs
        c._last_consolidation = 0
        result = c.consolidate()
        self.assertTrue(hasattr(result, "memories_before"))

    def test_insights(self):
        from orbit.orbit.core.memory_consolidator import get_consolidator

        c = get_consolidator()
        insights = c.get_insights()
        self.assertIsInstance(insights, list)

    def test_stats(self):
        from orbit.orbit.core.memory_consolidator import get_consolidator

        stats = get_consolidator().get_stats()
        self.assertIn("total_memories", stats)
        self.assertIn("total_insights", stats)
        self.assertIn("consolidation_count", stats)


class TestMetaCognition(unittest.TestCase):
    def test_singleton(self):
        from orbit.orbit.core.meta_cognition import get_meta_cognition

        m1 = get_meta_cognition()
        m2 = get_meta_cognition()
        self.assertIs(m1, m2)

    def test_record_response(self):
        from orbit.orbit.core.meta_cognition import get_meta_cognition

        meta = get_meta_cognition()
        meta.record_response("reasoning", confidence=0.8, latency_ms=500, success=True)
        stats = meta.get_stats()
        self.assertGreater(stats["total_queries"], 0)

    def test_record_failure(self):
        from orbit.orbit.core.meta_cognition import get_meta_cognition

        meta = get_meta_cognition()
        meta.record_response(
            "factual",
            confidence=0.1,
            latency_ms=2000,
            success=False,
            failure_reason="hallucination",
        )
        gaps = meta.get_knowledge_gaps()
        self.assertIsInstance(gaps, list)

    def test_get_strategy_advice(self):
        from orbit.orbit.core.meta_cognition import get_meta_cognition

        meta = get_meta_cognition()
        advice = meta.get_strategy_advice("reasoning")
        self.assertIn("strategy", advice)
        self.assertIn("confidence", advice)
        self.assertIn("advice", advice)

    def test_self_awareness(self):
        from orbit.orbit.core.meta_cognition import get_meta_cognition

        meta = get_meta_cognition()
        awareness = meta.get_self_awareness()
        self.assertIn("global_confidence", awareness)
        self.assertIn("total_queries", awareness)
        self.assertIn("strong_categories", awareness)
        self.assertIn("weak_categories", awareness)

    def test_reflect(self):
        from orbit.orbit.core.meta_cognition import get_meta_cognition

        meta = get_meta_cognition()
        r = meta.reflect("reasoning", "The answer is 4.", 0.8)
        self.assertIn("what_went_well", r.__dict__)
        self.assertIn("improvement", r.__dict__)

    def test_stats(self):
        from orbit.orbit.core.meta_cognition import get_meta_cognition

        stats = get_meta_cognition().get_stats()
        self.assertIn("total_queries", stats)
        self.assertIn("global_confidence", stats)
        self.assertIn("hallucination_count", stats)


class TestAGIBlueprint(unittest.TestCase):
    def test_agi_status_endpoint(self):
        from orbit.orbit.server import create_app

        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/agi/status")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertIn("reflection", data)
            self.assertIn("world_model", data)
            self.assertIn("goals", data)
            self.assertIn("consolidation", data)
            self.assertIn("meta_cognition", data)

    def test_reflection_endpoints(self):
        from orbit.orbit.server import create_app

        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/agi/reflection/stats")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/reflection/recent")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/reflection/weak-areas")
            self.assertEqual(resp.status_code, 200)

    def test_world_endpoints(self):
        from orbit.orbit.server import create_app

        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/agi/world/stats")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/world/entities")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/world/goals")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/world/timeline")
            self.assertEqual(resp.status_code, 200)

    def test_goals_endpoints(self):
        from orbit.orbit.server import create_app

        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/agi/goals/active")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/goals/blocked")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/goals/suggestions")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/goals/stats")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/goals/summary")
            self.assertEqual(resp.status_code, 200)

    def test_consolidation_endpoints(self):
        from orbit.orbit.server import create_app

        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/agi/consolidation/stats")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/consolidation/insights")
            self.assertEqual(resp.status_code, 200)

    def test_meta_endpoints(self):
        from orbit.orbit.server import create_app

        app = create_app()
        with app.test_client() as client:
            resp = client.get("/api/agi/meta/stats")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/meta/self-awareness")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/meta/gaps")
            self.assertEqual(resp.status_code, 200)
            resp = client.get("/api/agi/meta/strategy/reasoning")
            self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
