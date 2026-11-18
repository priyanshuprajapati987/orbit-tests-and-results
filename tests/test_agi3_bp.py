"""Unit tests for orbit/orbit/core/agi3_bp.py."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.agi3_bp import agi3_bp, _ok, _err

CREATIVITY = "orbit.core.creativity_engine.get_creativity"
ETHICAL = "orbit.core.ethical_reasoner.get_ethical"
TEMPORAL = "orbit.core.temporal_reasoner.get_temporal"
SOCIAL = "orbit.core.social_dynamics.get_social"
NARRATIVE = "orbit.core.narrative_engine.get_narrative"


class Agi3Base(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(agi3_bp)
        self.client = self.app.test_client()
        self.creativity = MagicMock()
        self.ethical = MagicMock()
        self.temporal = MagicMock()
        self.social = MagicMock()
        self.narrative = MagicMock()
        for target, mock in (
            (CREATIVITY, self.creativity),
            (ETHICAL, self.ethical),
            (TEMPORAL, self.temporal),
            (SOCIAL, self.social),
            (NARRATIVE, self.narrative),
        ):
            p = patch(target, return_value=mock)
            p.start()
            self.addCleanup(p.stop)

    def test_blueprint_name(self):
        self.assertEqual(agi3_bp.name, "agi3_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/agi/creativity/status", "/api/agi/creativity/blend",
                  "/api/agi/creativity/metaphor", "/api/agi/creativity/ideas",
                  "/api/agi/ethics/status", "/api/agi/ethics/evaluate",
                  "/api/agi/ethics/check", "/api/agi/temporal/status",
                  "/api/agi/temporal/record", "/api/agi/temporal/predict",
                  "/api/agi/temporal/trend/<event_type>",
                  "/api/agi/social/status", "/api/agi/social/person",
                  "/api/agi/social/interaction", "/api/agi/social/influence",
                  "/api/agi/social/person/<name>",
                  "/api/agi/narrative/status", "/api/agi/narrative/story",
                  "/api/agi/narrative/episode", "/api/agi/narrative/episodes",
                  "/api/agi/narrative/context"]:
            self.assertIn(p, rules)


class TestHelpers(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.client = self.app.test_client()

    def test_ok_plain(self):
        with self.app.test_request_context("/"):
            resp = _ok()
            import json
            data = json.loads(resp.get_data())
        self.assertEqual(data, {"ok": True})

    def test_ok_with_data(self):
        with self.app.test_request_context("/"):
            resp = _ok({"x": 1})
            import json
            data = json.loads(resp.get_data())
        self.assertEqual(data, {"ok": True, "data": {"x": 1}})

    def test_ok_with_kwargs(self):
        with self.app.test_request_context("/"):
            resp = _ok({"x": 1}, extra="yes")
            import json
            data = json.loads(resp.get_data())
        self.assertEqual(data, {"ok": True, "data": {"x": 1},
                                "extra": "yes"})

    def test_err_default_400(self):
        with self.app.test_request_context("/"):
            resp, code = _err("bad input")
            import json
            data = json.loads(resp.get_data())
        self.assertEqual(code, 400)
        self.assertEqual(data, {"ok": False, "error": "bad input"})

    def test_err_custom_code(self):
        with self.app.test_request_context("/"):
            _, code = _err("gone", 410)
        self.assertEqual(code, 410)


class TestCreativity(Agi3Base):
    def test_status(self):
        self.creativity.get_stats.return_value = {"blends": 4}
        r = self.client.get("/api/agi/creativity/status")
        self.assertEqual(r.get_json(), {"blends": 4})

    def test_blend_success(self):
        self.creativity.blend.return_value = {"combo": "a+b"}
        r = self.client.post("/api/agi/creativity/blend",
                             json={"concept_a": "cat", "concept_b": "dog"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"combo": "a+b"})
        self.creativity.blend.assert_called_once_with(
            "cat", "dog", "feature_merge")

    def test_blend_custom_strategy(self):
        self.creativity.blend.return_value = {}
        self.client.post("/api/agi/creativity/blend", json={
            "concept_a": "a", "concept_b": "b", "strategy": "analogy"})
        self.creativity.blend.assert_called_once_with("a", "b", "analogy")

    def test_blend_missing_a_400(self):
        r = self.client.post("/api/agi/creativity/blend",
                             json={"concept_b": "dog"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("concept_a and concept_b required",
                      r.get_json()["error"])
        self.creativity.blend.assert_not_called()

    def test_blend_missing_b_400(self):
        r = self.client.post("/api/agi/creativity/blend",
                             json={"concept_a": "cat"})
        self.assertEqual(r.status_code, 400)

    def test_blend_no_body_400(self):
        r = self.client.post("/api/agi/creativity/blend")
        self.assertEqual(r.status_code, 400)

    def test_blend_engine_exception_500(self):
        self.creativity.blend.side_effect = RuntimeError("no blend")
        r = self.client.post("/api/agi/creativity/blend",
                             json={"concept_a": "a", "concept_b": "b"})
        self.assertEqual(r.status_code, 500)

    def test_metaphor_success(self):
        self.creativity.generate_metaphor.return_value = {"m": "like x"}
        r = self.client.post("/api/agi/creativity/metaphor",
                             json={"concept": "time"})
        self.assertEqual(r.get_json(), {"m": "like x"})
        self.creativity.generate_metaphor.assert_called_once_with(
            "time", "")

    def test_metaphor_with_domain(self):
        self.creativity.generate_metaphor.return_value = {}
        self.client.post("/api/agi/creativity/metaphor", json={
            "concept": "time", "target_domain": "physics"})
        self.creativity.generate_metaphor.assert_called_once_with(
            "time", "physics")

    def test_metaphor_missing_concept_400(self):
        r = self.client.post("/api/agi/creativity/metaphor", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("concept required", r.get_json()["error"])

    def test_ideas_success(self):
        self.creativity.generate_idea.return_value = ["i1", "i2"]
        r = self.client.post("/api/agi/creativity/ideas",
                             json={"seed": "flying car"})
        self.assertEqual(r.get_json(), ["i1", "i2"])
        self.creativity.generate_idea.assert_called_once_with(
            "flying car", 3)

    def test_ideas_custom_n(self):
        self.creativity.generate_idea.return_value = []
        self.client.post("/api/agi/creativity/ideas",
                         json={"seed": "s", "n": 7})
        self.creativity.generate_idea.assert_called_once_with("s", 7)

    def test_ideas_missing_seed_400(self):
        r = self.client.post("/api/agi/creativity/ideas", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("seed required", r.get_json()["error"])


class TestEthics(Agi3Base):
    def test_status(self):
        self.ethical.get_stats.return_value = {"evaluated": 6}
        r = self.client.get("/api/agi/ethics/status")
        self.assertEqual(r.get_json(), {"evaluated": 6})

    def test_evaluate_success(self):
        self.ethical.evaluate.return_value = {"verdict": "ok"}
        r = self.client.post("/api/agi/ethics/evaluate",
                             json={"action": "help user"})
        self.assertEqual(r.get_json(), {"verdict": "ok"})
        self.ethical.evaluate.assert_called_once_with("help user", "")

    def test_evaluate_with_context(self):
        self.ethical.evaluate.return_value = {}
        self.client.post("/api/agi/ethics/evaluate", json={
            "action": "a", "context": "emergency"})
        self.ethical.evaluate.assert_called_once_with("a", "emergency")

    def test_evaluate_missing_action_400(self):
        r = self.client.post("/api/agi/ethics/evaluate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("action required", r.get_json()["error"])
        self.ethical.evaluate.assert_not_called()

    def test_check_success(self):
        self.ethical.check_principles.return_value = {"violations": 0}
        r = self.client.post("/api/agi/ethics/check",
                             json={"text": "be honest"})
        self.assertEqual(r.get_json(), {"violations": 0})
        self.ethical.check_principles.assert_called_once_with("be honest")

    def test_check_missing_text_400(self):
        r = self.client.post("/api/agi/ethics/check", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("text required", r.get_json()["error"])

    def test_check_no_body_400(self):
        r = self.client.post("/api/agi/ethics/check")
        self.assertEqual(r.status_code, 400)


class TestTemporal(Agi3Base):
    def test_status(self):
        self.temporal.get_stats.return_value = {"events": 12}
        r = self.client.get("/api/agi/temporal/status")
        self.assertEqual(r.get_json(), {"events": 12})

    def test_record_success(self):
        r = self.client.post("/api/agi/temporal/record",
                             json={"event_type": "login"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"ok": True,
                          "data": {"event_type": "login", "recorded": True}})
        self.temporal.record_event.assert_called_once_with(
            "login", {}, 0)

    def test_record_full_fields(self):
        self.client.post("/api/agi/temporal/record", json={
            "event_type": "task_done", "attributes": {"k": "v"},
            "duration_ms": 250})
        self.temporal.record_event.assert_called_once_with(
            "task_done", {"k": "v"}, 250)

    def test_record_missing_event_type_400(self):
        r = self.client.post("/api/agi/temporal/record", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("event_type required", r.get_json()["error"])
        self.temporal.record_event.assert_not_called()

    def test_predict_with_events(self):
        self.temporal.predict_next.return_value = [{"next": "login"}]
        r = self.client.post("/api/agi/temporal/predict",
                             json={"recent_events": ["a", "b"]})
        self.assertEqual(r.get_json(), [{"next": "login"}])
        self.temporal.predict_next.assert_called_once_with(["a", "b"])

    def test_predict_no_body_calls_with_empty(self):
        # no validation on this endpoint: engine always called
        self.temporal.predict_next.return_value = []
        r = self.client.post("/api/agi/temporal/predict")
        self.assertEqual(r.status_code, 200)
        self.temporal.predict_next.assert_called_once_with([])

    def test_trend_default_hours(self):
        self.temporal.get_trend.return_value = {"points": []}
        r = self.client.get("/api/agi/temporal/trend/login")
        self.assertEqual(r.get_json(), {"points": []})
        self.temporal.get_trend.assert_called_once_with("login", 24)

    def test_trend_custom_hours(self):
        self.temporal.get_trend.return_value = {}
        self.client.get("/api/agi/temporal/trend/login?hours=6")
        self.temporal.get_trend.assert_called_once_with("login", 6)

    def test_trend_bad_hours_defaults_24(self):
        self.temporal.get_trend.return_value = {}
        self.client.get("/api/agi/temporal/trend/login?hours=abc")
        self.temporal.get_trend.assert_called_once_with("login", 24)


class TestSocial(Agi3Base):
    def test_status(self):
        self.social.get_stats.return_value = {"people": 3}
        r = self.client.get("/api/agi/social/status")
        self.assertEqual(r.get_json(), {"people": 3})

    def test_add_person(self):
        self.social.add_person.return_value = SimpleNamespace(
            name="Alice", trust_level=0.6)
        r = self.client.post("/api/agi/social/person",
                             json={"name": "Alice"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"name": "Alice", "trust": 0.6})
        self.social.add_person.assert_called_once_with("Alice", {})

    def test_add_person_with_attributes(self):
        self.social.add_person.return_value = SimpleNamespace(
            name="Bob", trust_level=0.5)
        self.client.post("/api/agi/social/person", json={
            "name": "Bob", "attributes": {"role": "dev"}})
        self.social.add_person.assert_called_once_with(
            "Bob", {"role": "dev"})

    def test_add_person_missing_name_400(self):
        r = self.client.post("/api/agi/social/person", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("name required", r.get_json()["error"])
        self.social.add_person.assert_not_called()

    def test_interaction_success(self):
        r = self.client.post("/api/agi/social/interaction",
                             json={"person_a": "Alice", "person_b": "Bob"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"ok": True, "data": {"recorded": True}})
        self.social.record_interaction.assert_called_once_with(
            "Alice", "Bob", "chat", 0.5)

    def test_interaction_full_fields(self):
        self.client.post("/api/agi/social/interaction", json={
            "person_a": "a", "person_b": "b",
            "type": "conflict", "quality": 0.1})
        self.social.record_interaction.assert_called_once_with(
            "a", "b", "conflict", 0.1)

    def test_interaction_missing_a_400(self):
        r = self.client.post("/api/agi/social/interaction",
                             json={"person_b": "b"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("person_a and person_b required",
                      r.get_json()["error"])

    def test_interaction_missing_b_400(self):
        r = self.client.post("/api/agi/social/interaction",
                             json={"person_a": "a"})
        self.assertEqual(r.status_code, 400)

    def test_influence(self):
        self.social.get_influence_network.return_value = {"edges": 2}
        r = self.client.get("/api/agi/social/influence")
        self.assertEqual(r.get_json(), {"edges": 2})

    def test_person_context(self):
        self.social.get_person_context.return_value = {"trust": 0.4}
        r = self.client.get("/api/agi/social/person/Alice")
        self.assertEqual(r.get_json(), {"trust": 0.4})
        self.social.get_person_context.assert_called_once_with("Alice")


class TestNarrative(Agi3Base):
    def test_status(self):
        self.narrative.get_stats.return_value = {"episodes": 9}
        r = self.client.get("/api/agi/narrative/status")
        self.assertEqual(r.get_json(), {"episodes": 9})

    def test_story_defaults(self):
        self.narrative.generate_story.return_value = {"title": "T"}
        r = self.client.post("/api/agi/narrative/story", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"title": "T"})
        self.narrative.generate_story.assert_called_once_with(
            protagonist="ORBIT", setting="", conflict="",
            genre="hero_journey", tone="inspirational")

    def test_story_full_fields(self):
        self.narrative.generate_story.return_value = {}
        self.client.post("/api/agi/narrative/story", json={
            "protagonist": "Kai", "setting": "Tokyo",
            "conflict": "rival", "genre": "noir", "tone": "dark"})
        self.narrative.generate_story.assert_called_once_with(
            protagonist="Kai", setting="Tokyo", conflict="rival",
            genre="noir", tone="dark")

    def test_episode_success(self):
        self.narrative.record_episode.return_value = {"ep": 3}
        r = self.client.post("/api/agi/narrative/episode",
                             json={"title": "Ep 3", "extra": "x"})
        self.assertEqual(r.get_json(), {"ep": 3})
        # full body passed through as context
        self.narrative.record_episode.assert_called_once_with(
            "Ep 3", {"title": "Ep 3", "extra": "x"})

    def test_episode_missing_title_400(self):
        r = self.client.post("/api/agi/narrative/episode", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("title required", r.get_json()["error"])
        self.narrative.record_episode.assert_not_called()

    def test_episodes_default_n(self):
        self.narrative.get_recent_episodes.return_value = ["e1"]
        r = self.client.get("/api/agi/narrative/episodes")
        self.assertEqual(r.get_json(), ["e1"])
        self.narrative.get_recent_episodes.assert_called_once_with(5)

    def test_episodes_custom_n(self):
        self.narrative.get_recent_episodes.return_value = []
        self.client.get("/api/agi/narrative/episodes?n=2")
        self.narrative.get_recent_episodes.assert_called_once_with(2)

    def test_episodes_bad_n_defaults_5(self):
        self.narrative.get_recent_episodes.return_value = []
        self.client.get("/api/agi/narrative/episodes?n=abc")
        self.narrative.get_recent_episodes.assert_called_once_with(5)

    def test_context(self):
        self.narrative.get_narrative_context.return_value = {"act": 2}
        r = self.client.get("/api/agi/narrative/context")
        self.assertEqual(r.get_json(), {"context": {"act": 2}})


if __name__ == "__main__":
    unittest.main()
