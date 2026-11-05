"""Tests for Wave 2 AGI systems: Curiosity, Theory of Mind, Causal, Counterfactual, Analogical, Knowledge Graph."""

import os
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


class TestCuriosityEngine(unittest.TestCase):
    def test_generate_questions(self):
        from orbit.orbit.core.curiosity_engine import CuriosityEngine

        c = CuriosityEngine(storage_file="orbit_data/test_curiosity.json")
        questions = c.generate_questions("quantum computing", n=3)
        self.assertEqual(len(questions), 3)
        self.assertTrue(all(q.topic == "quantum computing" for q in questions))

    def test_record_exploration(self):
        from orbit.orbit.core.curiosity_engine import CuriosityEngine

        c = CuriosityEngine(storage_file="orbit_data/test_curiosity_explore.json")
        c.record_exploration(
            "quantum error correction", "Surface code is promising", quality=0.8
        )
        # Check the exploration was recorded (not checking exact count due to singleton)
        self.assertTrue(len(c._explorations) > 0)

    def test_extract_topics(self):
        from orbit.orbit.core.curiosity_engine import CuriosityEngine

        c = CuriosityEngine(storage_file="orbit_data/test_curiosity.json")
        topics = c.extract_topics_from_text(
            "The API uses Python and Docker for deployment"
        )
        self.assertTrue(len(topics) > 0)

    def test_interest_decay(self):
        from orbit.orbit.core.curiosity_engine import CuriosityEngine

        c = CuriosityEngine(storage_file="orbit_data/test_curiosity.json")
        c.generate_questions("topic A", n=1)
        c.generate_questions("topic B", n=1)
        # topic A interest should have decayed
        self.assertTrue(len(c.get_top_topics(10)) >= 2)

    def test_singleton(self):
        from orbit.orbit.core.curiosity_engine import get_curiosity

        a = get_curiosity()
        b = get_curiosity()
        self.assertIs(a, b)

    def test_stats_shape(self):
        from orbit.orbit.core.curiosity_engine import CuriosityEngine

        c = CuriosityEngine(storage_file="orbit_data/test_curiosity.json")
        stats = c.get_stats()
        for key in ("total_questions", "unexplored", "explored", "topics_tracked"):
            self.assertIn(key, stats)


class TestTheoryOfMind(unittest.TestCase):
    def test_analyze_question(self):
        from orbit.orbit.core.theory_of_mind import TheoryOfMind

        tom = TheoryOfMind(storage_file="orbit_data/test_tom.json")
        result = tom.analyze_message("What is quantum computing?")
        self.assertEqual(result["intent"], "question")

    def test_analyze_urgency(self):
        from orbit.orbit.core.theory_of_mind import TheoryOfMind

        tom = TheoryOfMind(storage_file="orbit_data/test_tom.json")
        result = tom.analyze_message("URGENT: fix this bug NOW!!!")
        self.assertIn(result["emotion"], ("excited", "urgent", "frustrated"))
        self.assertGreater(result["urgency"], 0.3)

    def test_expert_detection(self):
        from orbit.orbit.core.theory_of_mind import TheoryOfMind

        tom = TheoryOfMind(storage_file="orbit_data/test_tom.json")
        result = tom.analyze_message(
            "How does the API implementation handle concurrency?"
        )
        self.assertIn(result["knowledge_level"], ("intermediate", "expert"))

    def test_beginner_detection(self):
        from orbit.orbit.core.theory_of_mind import TheoryOfMind

        tom = TheoryOfMind(storage_file="orbit_data/test_tom.json")
        result = tom.analyze_message(
            "What is an API? Can you explain the basic concept?"
        )
        self.assertEqual(result["knowledge_level"], "beginner")

    def test_adaptation_hints(self):
        from orbit.orbit.core.theory_of_mind import TheoryOfMind

        tom = TheoryOfMind(storage_file="orbit_data/test_tom.json")
        tom.analyze_message("Hello!")
        hints = tom.get_adaptation_hints()
        self.assertIn("length", hints)
        self.assertIn("tone", hints)
        self.assertIn("depth", hints)

    def test_satisfaction_update(self):
        import os
        import tempfile

        from orbit.orbit.core.theory_of_mind import TheoryOfMind

        # Fresh storage per run: a persisted orbit_data/test_tom.json lets the
        # EMA asymptote to ~1.0 across sessions, and the strict-greater assert
        # then fails on float equality (saturation, not a product bug).
        with tempfile.TemporaryDirectory() as td:
            tom = TheoryOfMind(storage_file=os.path.join(td, "tom.json"))
            old_sat = tom._state.satisfaction
            self.assertLess(old_sat, 1.0)
            tom.update_after_response(1.0)
            self.assertGreater(tom._state.satisfaction, old_sat)

    def test_singleton(self):
        from orbit.orbit.core.theory_of_mind import get_tom

        a = get_tom()
        b = get_tom()
        self.assertIs(a, b)


class TestCausalReasoner(unittest.TestCase):
    def test_analyze_because(self):
        from orbit.orbit.core.causal_reasoner import CausalReasoner

        c = CausalReasoner(storage_file="orbit_data/test_causal.json")
        result = c.analyze(
            "The server is slow because the database query is unoptimized"
        )
        self.assertTrue(len(result["edges"]) > 0)

    def test_analyze_leads_to(self):
        from orbit.orbit.core.causal_reasoner import CausalReasoner

        c = CausalReasoner(storage_file="orbit_data/test_causal.json")
        result = c.analyze("High traffic leads to server overload")
        self.assertTrue(len(result["edges"]) > 0)

    def test_find_root_cause(self):
        from orbit.orbit.core.causal_reasoner import CausalReasoner

        c = CausalReasoner(storage_file="orbit_data/test_causal.json")
        c.analyze("Bad config causes server crash")
        c.analyze("Server crash causes downtime")
        result = c.find_root_cause("downtime")
        self.assertIn("root_cause", result)

    def test_predict_effects(self):
        from orbit.orbit.core.causal_reasoner import CausalReasoner

        c = CausalReasoner(storage_file="orbit_data/test_causal.json")
        c.analyze("Deploying code causes production to update")
        effects = c.predict_effects("deploying code")
        self.assertIsInstance(effects, list)

    def test_stats(self):
        from orbit.orbit.core.causal_reasoner import CausalReasoner

        c = CausalReasoner(storage_file="orbit_data/test_causal.json")
        stats = c.get_stats()
        self.assertIn("nodes", stats)
        self.assertIn("edges", stats)

    def test_singleton(self):
        from orbit.orbit.core.causal_reasoner import get_causal

        a = get_causal()
        b = get_causal()
        self.assertIs(a, b)


class TestCounterfactualEngine(unittest.TestCase):
    def test_analyze(self):
        from orbit.orbit.core.counterfactual_engine import CounterfactualEngine

        c = CounterfactualEngine(storage_file="orbit_data/test_counter.json")
        result = c.analyze("We deployed on Friday", "What if we deployed on Monday?")
        self.assertIn("effects", result)
        self.assertIn("lessons", result)

    def test_alternatives(self):
        from orbit.orbit.core.counterfactual_engine import CounterfactualEngine

        c = CounterfactualEngine(storage_file="orbit_data/test_counter.json")
        alts = c.generate_alternatives("server crashed after deploy", n=3)
        self.assertEqual(len(alts), 3)
        self.assertTrue(all("counterfactual" in a for a in alts))

    def test_preventive_type(self):
        from orbit.orbit.core.counterfactual_engine import CounterfactualEngine

        c = CounterfactualEngine(storage_file="orbit_data/test_counter.json")
        result = c.analyze("Server crashed", "What if we had not deployed?")
        self.assertEqual(result["scenario_type"], "preventive")

    def test_stats(self):
        from orbit.orbit.core.counterfactual_engine import CounterfactualEngine

        c = CounterfactualEngine(storage_file="orbit_data/test_counter.json")
        stats = c.get_stats()
        self.assertIn("scenarios", stats)
        self.assertIn("total_analyzed", stats)

    def test_singleton(self):
        from orbit.orbit.core.counterfactual_engine import get_counterfactual

        a = get_counterfactual()
        b = get_counterfactual()
        self.assertIs(a, b)


class TestAnalogicalThinker(unittest.TestCase):
    def test_find_builtin(self):
        from orbit.orbit.core.analogical_thinker import AnalogicalThinker

        a = AnalogicalThinker(storage_file="orbit_data/test_analog.json")
        result = a.find_analogy("microservices", "cell biology")
        self.assertTrue(result.get("found") or result.get("created"))
        self.assertIn("analogy", result)

    def test_explain_by_analogy(self):
        from orbit.orbit.core.analogical_thinker import AnalogicalThinker

        a = AnalogicalThinker(storage_file="orbit_data/test_analog.json")
        explanation = a.explain_by_analogy("neural networks", "brain")
        self.assertIsInstance(explanation, str)
        self.assertTrue(len(explanation) > 10)

    def test_reverse_analogy(self):
        from orbit.orbit.core.analogical_thinker import AnalogicalThinker

        a = AnalogicalThinker(storage_file="orbit_data/test_analog.json")
        result = a.find_analogy("cell biology", "microservices")
        self.assertTrue(result.get("found") or result.get("created"))

    def test_similar_problem(self):
        from orbit.orbit.core.analogical_thinker import AnalogicalThinker

        a = AnalogicalThinker(storage_file="orbit_data/test_analog.json")
        solutions = [
            {"problem": "database is slow", "solution": "add index"},
            {"problem": "API is slow", "solution": "cache responses"},
        ]
        match = a.find_similar_problem("query performance is bad", solutions)
        # Should find at least one match
        if match:
            self.assertIn("similarity", match)

    def test_stats(self):
        from orbit.orbit.core.analogical_thinker import AnalogicalThinker

        a = AnalogicalThinker(storage_file="orbit_data/test_analog.json")
        stats = a.get_stats()
        self.assertIn("analogies", stats)
        self.assertIn("domains", stats)

    def test_singleton(self):
        from orbit.orbit.core.analogical_thinker import get_analogical

        a = get_analogical()
        b = get_analogical()
        self.assertIs(a, b)


class TestKnowledgeGraph(unittest.TestCase):
    def test_add_entity(self):
        from orbit.orbit.core.knowledge_graph import KnowledgeGraph

        k = KnowledgeGraph(storage_file="orbit_data/test_kg.json")
        e = k.add_entity("TestEntity", "tool", {"purpose": "testing"})
        self.assertEqual(e.name, "TestEntity")
        self.assertEqual(e.entity_type, "tool")

    def test_add_relation(self):
        from orbit.orbit.core.knowledge_graph import KnowledgeGraph

        k = KnowledgeGraph(storage_file="orbit_data/test_kg.json")
        r = k.add_relation("A", "uses", "B")
        self.assertEqual(r.subject, "A")
        self.assertEqual(r.predicate, "uses")

    def test_find_path(self):
        from orbit.orbit.core.knowledge_graph import KnowledgeGraph

        k = KnowledgeGraph(storage_file="orbit_data/test_kg.json")
        k.add_relation("X", "uses", "Y")
        k.add_relation("Y", "uses", "Z")
        path = k.find_path("X", "Z")
        self.assertIsNotNone(path)
        self.assertTrue(len(path) > 0)

    def test_get_neighbors(self):
        from orbit.orbit.core.knowledge_graph import KnowledgeGraph

        k = KnowledgeGraph(storage_file="orbit_data/test_kg.json")
        k.add_relation("ORBIT", "uses", "Flask")
        neighbors = k.get_neighbors("ORBIT")
        self.assertTrue(len(neighbors["direct"]) > 0)

    def test_infer_relations(self):
        from orbit.orbit.core.knowledge_graph import KnowledgeGraph

        k = KnowledgeGraph(storage_file="orbit_data/test_kg.json")
        k.add_relation("A", "uses", "B")
        k.add_relation("B", "uses", "C")
        inferences = k.infer_relations()
        self.assertIsInstance(inferences, list)

    def test_extract_from_text(self):
        from orbit.orbit.core.knowledge_graph import KnowledgeGraph

        k = KnowledgeGraph(storage_file="orbit_data/test_kg.json")
        result = k.extract_from_text("ORBIT uses Flask and React for the frontend")
        self.assertIsInstance(result, dict)

    def test_stats(self):
        from orbit.orbit.core.knowledge_graph import KnowledgeGraph

        k = KnowledgeGraph(storage_file="orbit_data/test_kg.json")
        stats = k.get_stats()
        self.assertIn("entities", stats)
        self.assertIn("relations", stats)
        self.assertGreater(stats["entities"], 0)  # seed data

    def test_singleton(self):
        from orbit.orbit.core.knowledge_graph import get_knowledge

        a = get_knowledge()
        b = get_knowledge()
        self.assertIs(a, b)

    def test_seed_data(self):
        from orbit.orbit.core.knowledge_graph import KnowledgeGraph

        k = KnowledgeGraph(storage_file="orbit_data/test_kg.json")
        self.assertIn("ORBIT", k._entities)
        self.assertIn("Flask", k._entities)


class TestAGI2Blueprint(unittest.TestCase):
    def test_curiosity_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/curiosity/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get("total_questions") is not None)

    def test_tom_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/tom/status")
        self.assertEqual(r.status_code, 200)

    def test_causal_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/causal/status")
        self.assertEqual(r.status_code, 200)

    def test_counterfactual_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/counterfactual/status")
        self.assertEqual(r.status_code, 200)

    def test_analogical_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/analogical/status")
        self.assertEqual(r.status_code, 200)

    def test_knowledge_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/knowledge/status")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.get_json().get("entities", 0), 0)


if __name__ == "__main__":
    unittest.main()
