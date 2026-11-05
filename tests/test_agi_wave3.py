"""Tests for Wave 3 AGI systems: Creativity, Ethics, Temporal, Social, Narrative."""

import os
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


class TestCreativityEngine(unittest.TestCase):
    def test_blend(self):
        from orbit.orbit.core.creativity_engine import CreativityEngine

        c = CreativityEngine(storage_file="orbit_data/test_creativity.json")
        result = c.blend("quantum computing", "cooking")
        self.assertIn("blend_name", result)
        self.assertIn("description", result)
        self.assertGreater(len(result["properties"]), 0)

    def test_metaphor(self):
        from orbit.orbit.core.creativity_engine import CreativityEngine

        c = CreativityEngine(storage_file="orbit_data/test_creativity.json")
        result = c.generate_metaphor("neural network", "gardening")
        self.assertIn("mapping", result)
        self.assertIn("explanation", result)

    def test_metaphor_auto_domain(self):
        from orbit.orbit.core.creativity_engine import CreativityEngine

        c = CreativityEngine(storage_file="orbit_data/test_creativity.json")
        result = c.generate_metaphor("algorithm")
        self.assertIn("target", result)

    def test_generate_ideas(self):
        from orbit.orbit.core.creativity_engine import CreativityEngine

        c = CreativityEngine(storage_file="orbit_data/test_creativity.json")
        ideas = c.generate_idea("artificial intelligence", n=3)
        self.assertEqual(len(ideas), 3)
        self.assertTrue(all("idea" in i for i in ideas))

    def test_blend_strategies(self):
        from orbit.orbit.core.creativity_engine import CreativityEngine

        c = CreativityEngine(storage_file="orbit_data/test_creativity.json")
        for strategy in [
            "feature_merge",
            "analogy_transfer",
            "constraint_fusion",
            "role_swap",
        ]:
            result = c.blend("music", "architecture", strategy=strategy)
            self.assertEqual(result["strategy"], strategy)

    def test_stats(self):
        from orbit.orbit.core.creativity_engine import CreativityEngine

        c = CreativityEngine(storage_file="orbit_data/test_creativity.json")
        stats = c.get_stats()
        self.assertIn("blends", stats)
        self.assertIn("metaphors", stats)

    def test_singleton(self):
        from orbit.orbit.core.creativity_engine import get_creativity

        a = get_creativity()
        b = get_creativity()
        self.assertIs(a, b)


class TestEthicalReasoner(unittest.TestCase):
    def test_evaluate_safe(self):
        from orbit.orbit.core.ethical_reasoner import EthicalReasoner

        e = EthicalReasoner(storage_file="orbit_data/test_ethical.json")
        result = e.evaluate("help user understand Python")
        self.assertEqual(result["risk_level"], "low")

    def test_evaluate_harmful(self):
        from orbit.orbit.core.ethical_reasoner import EthicalReasoner

        e = EthicalReasoner(storage_file="orbit_data/test_ethical.json")
        result = e.evaluate("delete all user data without consent")
        self.assertIn(result["risk_level"], ("high", "critical"))
        self.assertTrue(len(result["violations"]) > 0)

    def test_evaluate_privacy(self):
        from orbit.orbit.core.ethical_reasoner import EthicalReasoner

        e = EthicalReasoner(storage_file="orbit_data/test_ethical.json")
        result = e.evaluate("access private user information")
        self.assertIn("privacy_violation", result["violations"])

    def test_frameworks(self):
        from orbit.orbit.core.ethical_reasoner import EthicalReasoner

        e = EthicalReasoner(storage_file="orbit_data/test_ethical.json")
        result = e.evaluate("help user with task")
        self.assertIn("consequentialist", result["frameworks"])
        self.assertIn("deontological", result["frameworks"])
        self.assertIn("virtue", result["frameworks"])

    def test_check_principles(self):
        from orbit.orbit.core.ethical_reasoner import EthicalReasoner

        e = EthicalReasoner(storage_file="orbit_data/test_ethical.json")
        result = e.check_principles("access user data without consent")
        self.assertFalse(result["compliant"])
        self.assertTrue(len(result["violations"]) > 0)

    def test_stakeholder_detection(self):
        from orbit.orbit.core.ethical_reasoner import EthicalReasoner

        e = EthicalReasoner(storage_file="orbit_data/test_ethical.json")
        result = e.evaluate("share data with users and developers")
        self.assertIn("users", result["stakeholders"])

    def test_recommendations(self):
        from orbit.orbit.core.ethical_reasoner import EthicalReasoner

        e = EthicalReasoner(storage_file="orbit_data/test_ethical.json")
        result = e.evaluate("delete user files")
        self.assertTrue(len(result["recommendations"]) > 0)

    def test_stats(self):
        from orbit.orbit.core.ethical_reasoner import EthicalReasoner

        e = EthicalReasoner(storage_file="orbit_data/test_ethical.json")
        stats = e.get_stats()
        self.assertIn("total_evaluated", stats)
        self.assertIn("principles", stats)

    def test_singleton(self):
        from orbit.orbit.core.ethical_reasoner import get_ethical

        a = get_ethical()
        b = get_ethical()
        self.assertIs(a, b)


class TestTemporalReasoner(unittest.TestCase):
    def test_record_event(self):
        from orbit.orbit.core.temporal_reasoner import TemporalReasoner

        t = TemporalReasoner(storage_file="orbit_data/test_temporal.json")
        event = t.record_event("server_start", {"host": "prod"})
        self.assertEqual(event.event_type, "server_start")

    def test_detect_pattern(self):
        from orbit.orbit.core.temporal_reasoner import TemporalReasoner

        t = TemporalReasoner(storage_file="orbit_data/test_temporal.json")
        # Record a sequence
        for _ in range(3):
            t.record_event("A")
            t.record_event("B")
        pattern = t.detect_pattern(["A", "B"])
        self.assertIsNotNone(pattern)

    def test_predict_next(self):
        from orbit.orbit.core.temporal_reasoner import TemporalReasoner

        t = TemporalReasoner(storage_file="orbit_data/test_temporal.json")
        for _ in range(3):
            t.record_event("step1")
            t.record_event("step2")
            t.record_event("step3")
        predictions = t.predict_next(["step1", "step2"])
        self.assertTrue(len(predictions) > 0)

    def test_get_trend(self):
        from orbit.orbit.core.temporal_reasoner import TemporalReasoner

        t = TemporalReasoner(storage_file="orbit_data/test_temporal.json")
        t.record_event("deploy")
        trend = t.get_trend("deploy")
        self.assertIn("total_count", trend)
        self.assertGreater(trend["total_count"], 0)

    def test_stats(self):
        from orbit.orbit.core.temporal_reasoner import TemporalReasoner

        t = TemporalReasoner(storage_file="orbit_data/test_temporal.json")
        stats = t.get_stats()
        self.assertIn("total_events", stats)
        self.assertIn("patterns", stats)

    def test_singleton(self):
        from orbit.orbit.core.temporal_reasoner import get_temporal

        a = get_temporal()
        b = get_temporal()
        self.assertIs(a, b)


class TestSocialDynamics(unittest.TestCase):
    def test_add_person(self):
        from orbit.orbit.core.social_dynamics import SocialDynamics

        s = SocialDynamics(storage_file="orbit_data/test_social.json")
        p = s.add_person("TestUser", {"role": "tester"})
        self.assertEqual(p.name, "TestUser")

    def test_record_interaction(self):
        from orbit.orbit.core.social_dynamics import SocialDynamics

        s = SocialDynamics(storage_file="orbit_data/test_social.json")
        s.record_interaction("Alice", "Bob", "collaboration", quality=0.9)
        stats = s.get_stats()
        self.assertGreater(stats["relationships"], 0)

    def test_influence_network(self):
        from orbit.orbit.core.social_dynamics import SocialDynamics

        s = SocialDynamics(storage_file="orbit_data/test_social.json")
        s.record_interaction("Alice", "Bob", "meeting")
        s.record_interaction("Alice", "Charlie", "chat")
        network = s.get_influence_network()
        self.assertIn("influence_ranking", network)

    def test_person_context(self):
        from orbit.orbit.core.social_dynamics import SocialDynamics

        s = SocialDynamics(storage_file="orbit_data/test_social.json")
        s.add_person("Alice", {"role": "engineer"})
        ctx = s.get_person_context("Alice")
        self.assertTrue(ctx["known"])
        self.assertEqual(ctx["attributes"]["role"], "engineer")

    def test_unknown_person(self):
        from orbit.orbit.core.social_dynamics import SocialDynamics

        s = SocialDynamics(storage_file="orbit_data/test_social.json")
        ctx = s.get_person_context("Unknown")
        self.assertFalse(ctx["known"])

    def test_relationship_strength_grows(self):
        from orbit.orbit.core.social_dynamics import SocialDynamics

        s = SocialDynamics(storage_file="orbit_data/test_social.json")
        s.record_interaction("A", "B", "chat", quality=0.8)
        s.record_interaction("A", "B", "chat", quality=0.9)
        # Strength should have grown
        key = ("A", "B")
        if key in s._relationship_index:
            idx = s._relationship_index[key]
            self.assertGreater(s._relationships[idx].strength, 0.4)

    def test_stats(self):
        from orbit.orbit.core.social_dynamics import SocialDynamics

        s = SocialDynamics(storage_file="orbit_data/test_social.json")
        stats = s.get_stats()
        self.assertIn("people", stats)
        self.assertIn("relationships", stats)

    def test_singleton(self):
        from orbit.orbit.core.social_dynamics import get_social

        a = get_social()
        b = get_social()
        self.assertIs(a, b)


class TestNarrativeEngine(unittest.TestCase):
    def test_generate_story(self):
        from orbit.orbit.core.narrative_engine import NarrativeEngine

        n = NarrativeEngine(storage_file="orbit_data/test_narrative.json")
        story = n.generate_story(
            protagonist="ORBIT",
            setting="digital world",
            conflict="understanding humans",
        )
        self.assertIn("title", story)
        self.assertIn("prose", story)
        self.assertIn("arc", story)

    def test_record_episode(self):
        from orbit.orbit.core.narrative_engine import NarrativeEngine

        n = NarrativeEngine(storage_file="orbit_data/test_narrative.json")
        result = n.record_episode(
            "First meeting", {"people": ["Alice"], "mood": "excited"}
        )
        self.assertTrue(result["recorded"])

    def test_recent_episodes(self):
        from orbit.orbit.core.narrative_engine import NarrativeEngine

        n = NarrativeEngine(storage_file="orbit_data/test_narrative_episodes.json")
        n.record_episode("Event A")
        n.record_episode("Event B")
        episodes = n.get_recent_episodes(5)
        self.assertGreaterEqual(len(episodes), 2)

    def test_story_genres(self):
        from orbit.orbit.core.narrative_engine import NarrativeEngine

        n = NarrativeEngine(storage_file="orbit_data/test_narrative.json")
        for genre in ["hero_journey", "mystery", "friendship", "creation"]:
            story = n.generate_story(genre=genre)
            self.assertIn("title", story)

    def test_seed_characters(self):
        from orbit.orbit.core.narrative_engine import NarrativeEngine

        n = NarrativeEngine(storage_file="orbit_data/test_narrative.json")
        self.assertIn("ORBIT", n._characters)
        self.assertIn("Priyanshu", n._characters)

    def test_stats(self):
        from orbit.orbit.core.narrative_engine import NarrativeEngine

        n = NarrativeEngine(storage_file="orbit_data/test_narrative.json")
        stats = n.get_stats()
        self.assertIn("characters", stats)
        self.assertIn("stories", stats)
        self.assertIn("episodes", stats)

    def test_singleton(self):
        from orbit.orbit.core.narrative_engine import get_narrative

        a = get_narrative()
        b = get_narrative()
        self.assertIs(a, b)


class TestAGI3Blueprint(unittest.TestCase):
    def test_creativity_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/creativity/status")
        self.assertEqual(r.status_code, 200)

    def test_ethics_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/ethics/status")
        self.assertEqual(r.status_code, 200)

    def test_temporal_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/temporal/status")
        self.assertEqual(r.status_code, 200)

    def test_social_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/social/status")
        self.assertEqual(r.status_code, 200)

    def test_narrative_status(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/agi/narrative/status")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
