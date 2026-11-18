"""Unit tests for orbit/orbit/core/agi2_bp.py."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.agi2_bp import agi2_bp

CURIOSITY = "orbit.core.curiosity_engine.get_curiosity"
TOM = "orbit.core.theory_of_mind.get_tom"
CAUSAL = "orbit.core.causal_reasoner.get_causal"
COUNTER = "orbit.core.counterfactual_engine.get_counterfactual"
ANALOG = "orbit.core.analogical_thinker.get_analogical"
KNOWLEDGE = "orbit.core.knowledge_graph.get_knowledge"


def _question(text="Why?", topic="x", prio=0.8):
    return SimpleNamespace(question=text, topic=topic, priority=prio)


def _topic(name="py", interest=0.7, mentions=5):
    return SimpleNamespace(topic=name, interest_level=interest,
                           mention_count=mentions)


def _entity(name="E", etype="concept"):
    return SimpleNamespace(name=name, entity_type=etype)


def _relation(s="a", p="rel", o="b"):
    return SimpleNamespace(subject=s, predicate=p, object=o)


class Agi2Base(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(agi2_bp)
        self.client = self.app.test_client()
        self.curiosity = MagicMock()
        self.tom = MagicMock()
        self.causal = MagicMock()
        self.counter = MagicMock()
        self.analog = MagicMock()
        self.knowledge = MagicMock()
        for target, mock in (
            (CURIOSITY, self.curiosity),
            (TOM, self.tom),
            (CAUSAL, self.causal),
            (COUNTER, self.counter),
            (ANALOG, self.analog),
            (KNOWLEDGE, self.knowledge),
        ):
            p = patch(target, return_value=mock)
            p.start()
            self.addCleanup(p.stop)

    def test_blueprint_name(self):
        self.assertEqual(agi2_bp.name, "agi2_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/agi/curiosity/status",
                  "/api/agi/curiosity/questions",
                  "/api/agi/curiosity/explore",
                  "/api/agi/curiosity/topics",
                  "/api/agi/curiosity/questions/generate",
                  "/api/agi/tom/status", "/api/agi/tom/analyze",
                  "/api/agi/tom/hints", "/api/agi/tom/feedback",
                  "/api/agi/causal/status", "/api/agi/causal/analyze",
                  "/api/agi/causal/root-cause", "/api/agi/causal/predict",
                  "/api/agi/counterfactual/status",
                  "/api/agi/counterfactual/analyze",
                  "/api/agi/counterfactual/alternatives",
                  "/api/agi/analogical/status", "/api/agi/analogical/find",
                  "/api/agi/analogical/explain",
                  "/api/agi/analogical/similar",
                  "/api/agi/knowledge/status",
                  "/api/agi/knowledge/entity",
                  "/api/agi/knowledge/relation", "/api/agi/knowledge/path",
                  "/api/agi/knowledge/neighbors",
                  "/api/agi/knowledge/infer"]:
            self.assertIn(p, rules)


class TestCuriosity(Agi2Base):
    def test_status(self):
        self.curiosity.get_stats.return_value = {"questions": 8}
        r = self.client.get("/api/agi/curiosity/status")
        self.assertEqual(r.get_json(), {"questions": 8})

    def test_questions_default_n(self):
        self.curiosity.get_top_questions.return_value = [
            _question("Q1", "math", 0.9)]
        r = self.client.get("/api/agi/curiosity/questions")
        self.assertEqual(r.get_json(),
                         [{"question": "Q1", "topic": "math",
                           "priority": 0.9}])
        self.curiosity.get_top_questions.assert_called_once_with(5)

    def test_questions_custom_n(self):
        self.curiosity.get_top_questions.return_value = []
        self.client.get("/api/agi/curiosity/questions?n=2")
        self.curiosity.get_top_questions.assert_called_once_with(2)

    def test_questions_bad_n_defaults_5(self):
        self.curiosity.get_top_questions.return_value = []
        self.client.get("/api/agi/curiosity/questions?n=abc")
        self.curiosity.get_top_questions.assert_called_once_with(5)

    def test_explore_success(self):
        r = self.client.post("/api/agi/curiosity/explore", json={
            "topic": "space", "finding": "water on mars"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"ok": True,
                          "data": {"topic": "space", "recorded": True}})
        self.curiosity.record_exploration.assert_called_once_with(
            "space", "water on mars", "manual", 0.5)

    def test_explore_full_fields(self):
        self.client.post("/api/agi/curiosity/explore", json={
            "topic": "t", "finding": "f", "source": "sensor",
            "quality": 0.9})
        self.curiosity.record_exploration.assert_called_once_with(
            "t", "f", "sensor", 0.9)

    def test_explore_missing_topic_400(self):
        r = self.client.post("/api/agi/curiosity/explore",
                             json={"finding": "f"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("topic and finding required", r.get_json()["error"])
        self.curiosity.record_exploration.assert_not_called()

    def test_explore_missing_finding_400(self):
        r = self.client.post("/api/agi/curiosity/explore",
                             json={"topic": "t"})
        self.assertEqual(r.status_code, 400)

    def test_explore_no_body_400(self):
        r = self.client.post("/api/agi/curiosity/explore")
        self.assertEqual(r.status_code, 400)

    def test_topics(self):
        self.curiosity.get_top_topics.return_value = [_topic()]
        r = self.client.get("/api/agi/curiosity/topics")
        self.assertEqual(r.get_json(),
                         [{"topic": "py", "interest": 0.7,
                           "mentions": 5}])
        self.curiosity.get_top_topics.assert_called_once_with(10)

    def test_generate_questions(self):
        self.curiosity.generate_questions.return_value = [
            _question("Q?", prio=0.5)]
        r = self.client.post("/api/agi/curiosity/questions/generate",
                             json={"topic": "ai"})
        self.assertEqual(r.get_json(),
                         [{"question": "Q?", "priority": 0.5}])
        self.curiosity.generate_questions.assert_called_once_with(
            "ai", "", 3)

    def test_generate_full_fields(self):
        self.curiosity.generate_questions.return_value = []
        self.client.post("/api/agi/curiosity/questions/generate", json={
            "topic": "ai", "context": "beginner", "n": 5})
        self.curiosity.generate_questions.assert_called_once_with(
            "ai", "beginner", 5)

    def test_generate_missing_topic_400(self):
        r = self.client.post("/api/agi/curiosity/questions/generate",
                             json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("topic required", r.get_json()["error"])


class TestTheoryOfMind(Agi2Base):
    def test_status(self):
        self.tom.get_stats.return_value = {"analyzed": 4}
        r = self.client.get("/api/agi/tom/status")
        self.assertEqual(r.get_json(), {"analyzed": 4})

    def test_analyze(self):
        self.tom.analyze_message.return_value = {"intent": "request"}
        r = self.client.post("/api/agi/tom/analyze",
                             json={"message": "help me"})
        self.assertEqual(r.get_json(), {"intent": "request"})
        self.tom.analyze_message.assert_called_once_with("help me")

    def test_analyze_missing_message_400(self):
        r = self.client.post("/api/agi/tom/analyze", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("message required", r.get_json()["error"])
        self.tom.analyze_message.assert_not_called()

    def test_hints(self):
        self.tom.get_adaptation_hints.return_value = ["be brief"]
        r = self.client.get("/api/agi/tom/hints")
        self.assertEqual(r.get_json(), ["be brief"])

    def test_feedback_default(self):
        r = self.client.post("/api/agi/tom/feedback", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"ok": True, "data": {"satisfaction": 0.5}})
        self.tom.update_after_response.assert_called_once_with(0.5)

    def test_feedback_explicit(self):
        self.client.post("/api/agi/tom/feedback",
                         json={"satisfaction": 0.9})
        self.tom.update_after_response.assert_called_once_with(0.9)


class TestCausal(Agi2Base):
    def test_status(self):
        self.causal.get_stats.return_value = {"links": 12}
        r = self.client.get("/api/agi/causal/status")
        self.assertEqual(r.get_json(), {"links": 12})

    def test_analyze(self):
        self.causal.analyze.return_value = {"causes": ["x"]}
        r = self.client.post("/api/agi/causal/analyze",
                             json={"text": "server crashed"})
        self.assertEqual(r.get_json(), {"causes": ["x"]})
        self.causal.analyze.assert_called_once_with("server crashed")

    def test_analyze_missing_text_400(self):
        r = self.client.post("/api/agi/causal/analyze", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("text required", r.get_json()["error"])

    def test_root_cause(self):
        self.causal.find_root_cause.return_value = {"root": "leak"}
        r = self.client.post("/api/agi/causal/root-cause",
                             json={"symptom": "disk full"})
        self.assertEqual(r.get_json(), {"root": "leak"})
        self.causal.find_root_cause.assert_called_once_with("disk full")

    def test_root_cause_missing_400(self):
        r = self.client.post("/api/agi/causal/root-cause", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("symptom required", r.get_json()["error"])

    def test_predict(self):
        self.causal.predict_effects.return_value = ["e1"]
        r = self.client.post("/api/agi/causal/predict",
                             json={"action": "restart"})
        self.assertEqual(r.get_json(), ["e1"])
        self.causal.predict_effects.assert_called_once_with(
            "restart", 3)

    def test_predict_custom_depth(self):
        self.causal.predict_effects.return_value = []
        self.client.post("/api/agi/causal/predict",
                         json={"action": "a", "depth": 5})
        self.causal.predict_effects.assert_called_once_with("a", 5)

    def test_predict_missing_action_400(self):
        r = self.client.post("/api/agi/causal/predict", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("action required", r.get_json()["error"])


class TestCounterfactual(Agi2Base):
    def test_status(self):
        self.counter.get_stats.return_value = {"analyses": 3}
        r = self.client.get("/api/agi/counterfactual/status")
        self.assertEqual(r.get_json(), {"analyses": 3})

    def test_analyze(self):
        self.counter.analyze.return_value = {"diff": "outcome changed"}
        r = self.client.post("/api/agi/counterfactual/analyze", json={
            "actual": "I stayed", "what_if": "I left"})
        self.assertEqual(r.get_json(), {"diff": "outcome changed"})
        self.counter.analyze.assert_called_once_with("I stayed", "I left")

    def test_analyze_missing_actual_400(self):
        r = self.client.post("/api/agi/counterfactual/analyze",
                             json={"what_if": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("actual and what_if required",
                      r.get_json()["error"])

    def test_analyze_missing_what_if_400(self):
        r = self.client.post("/api/agi/counterfactual/analyze",
                             json={"actual": "x"})
        self.assertEqual(r.status_code, 400)

    def test_alternatives(self):
        self.counter.generate_alternatives.return_value = ["alt1"]
        r = self.client.post("/api/agi/counterfactual/alternatives",
                             json={"event": "rain"})
        self.assertEqual(r.get_json(), ["alt1"])
        self.counter.generate_alternatives.assert_called_once_with(
            "rain", 3)

    def test_alternatives_custom_n(self):
        self.counter.generate_alternatives.return_value = []
        self.client.post("/api/agi/counterfactual/alternatives",
                         json={"event": "e", "n": 9})
        self.counter.generate_alternatives.assert_called_once_with(
            "e", 9)

    def test_alternatives_missing_event_400(self):
        r = self.client.post("/api/agi/counterfactual/alternatives",
                             json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("event required", r.get_json()["error"])


class TestAnalogical(Agi2Base):
    def test_status(self):
        self.analog.get_stats.return_value = {"analogies": 6}
        r = self.client.get("/api/agi/analogical/status")
        self.assertEqual(r.get_json(), {"analogies": 6})

    def test_find(self):
        self.analog.find_analogy.return_value = {"strength": 0.8}
        r = self.client.post("/api/agi/analogical/find", json={
            "source": "brain", "target": "computer"})
        self.assertEqual(r.get_json(), {"strength": 0.8})
        self.analog.find_analogy.assert_called_once_with(
            "brain", "computer")

    def test_find_missing_source_400(self):
        r = self.client.post("/api/agi/analogical/find",
                             json={"target": "t"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("source and target required",
                      r.get_json()["error"])

    def test_find_missing_target_400(self):
        r = self.client.post("/api/agi/analogical/find",
                             json={"source": "s"})
        self.assertEqual(r.status_code, 400)

    def test_explain(self):
        self.analog.explain_by_analogy.return_value = "like pipes"
        r = self.client.post("/api/agi/analogical/explain", json={
            "concept": "internet", "familiar_domain": "plumbing"})
        self.assertEqual(r.get_json(), {"explanation": "like pipes"})
        self.analog.explain_by_analogy.assert_called_once_with(
            "internet", "plumbing")

    def test_explain_missing_concept_400(self):
        r = self.client.post("/api/agi/analogical/explain",
                             json={"familiar_domain": "d"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("concept and familiar_domain required",
                      r.get_json()["error"])

    def test_explain_missing_familiar_400(self):
        r = self.client.post("/api/agi/analogical/explain",
                             json={"concept": "c"})
        self.assertEqual(r.status_code, 400)

    def test_similar(self):
        self.analog.find_similar_problem.return_value = "p2"
        r = self.client.post("/api/agi/analogical/similar",
                             json={"problem": "p1"})
        self.assertEqual(r.get_json(), {"match": "p2"})
        self.analog.find_similar_problem.assert_called_once_with(
            "p1", [])

    def test_similar_with_solutions(self):
        self.analog.find_similar_problem.return_value = None
        self.client.post("/api/agi/analogical/similar", json={
            "problem": "p", "known_solutions": ["s1"]})
        self.analog.find_similar_problem.assert_called_once_with(
            "p", ["s1"])

    def test_similar_missing_problem_400(self):
        r = self.client.post("/api/agi/analogical/similar", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("problem required", r.get_json()["error"])


class TestKnowledge(Agi2Base):
    def test_status(self):
        self.knowledge.get_stats.return_value = {"entities": 20}
        r = self.client.get("/api/agi/knowledge/status")
        self.assertEqual(r.get_json(), {"entities": 20})

    def test_add_entity(self):
        self.knowledge.add_entity.return_value = _entity("Python", "lang")
        r = self.client.post("/api/agi/knowledge/entity",
                             json={"name": "Python"})
        self.assertEqual(r.get_json(), {"name": "Python", "type": "lang"})
        self.knowledge.add_entity.assert_called_once_with(
            "Python", "concept", {}, "")

    def test_add_entity_full(self):
        self.knowledge.add_entity.return_value = _entity()
        self.client.post("/api/agi/knowledge/entity", json={
            "name": "E", "type": "person", "attributes": {"age": 30},
            "description": "d"})
        self.knowledge.add_entity.assert_called_once_with(
            "E", "person", {"age": 30}, "d")

    def test_add_entity_missing_name_400(self):
        r = self.client.post("/api/agi/knowledge/entity", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("name required", r.get_json()["error"])
        self.knowledge.add_entity.assert_not_called()

    def test_add_relation(self):
        self.knowledge.add_relation.return_value = _relation(
            "a", "knows", "b")
        r = self.client.post("/api/agi/knowledge/relation", json={
            "subject": "a", "predicate": "knows", "object": "b"})
        self.assertEqual(r.get_json(),
                         {"subject": "a", "predicate": "knows",
                          "object": "b"})
        self.knowledge.add_relation.assert_called_once_with(
            "a", "knows", "b")

    def test_add_relation_missing_any_400(self):
        r = self.client.post("/api/agi/knowledge/relation", json={
            "subject": "a", "predicate": "knows"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("subject, predicate, object required",
                      r.get_json()["error"])
        self.knowledge.add_relation.assert_not_called()

    def test_path_success(self):
        self.knowledge.find_path.return_value = ["a", "b"]
        r = self.client.get("/api/agi/knowledge/path?from=a&to=b")
        self.assertEqual(r.get_json(), {"path": ["a", "b"]})
        self.knowledge.find_path.assert_called_once_with("a", "b")

    def test_path_missing_from_400(self):
        r = self.client.get("/api/agi/knowledge/path?to=b")
        self.assertEqual(r.status_code, 400)
        self.assertIn("from and to required", r.get_json()["error"])

    def test_path_missing_to_400(self):
        r = self.client.get("/api/agi/knowledge/path?from=a")
        self.assertEqual(r.status_code, 400)

    def test_path_no_params_400(self):
        r = self.client.get("/api/agi/knowledge/path")
        self.assertEqual(r.status_code, 400)

    def test_neighbors(self):
        self.knowledge.get_neighbors.return_value = ["x", "y"]
        r = self.client.get("/api/agi/knowledge/neighbors?entity=a")
        self.assertEqual(r.get_json(), ["x", "y"])
        self.knowledge.get_neighbors.assert_called_once_with("a")

    def test_neighbors_missing_entity_400(self):
        r = self.client.get("/api/agi/knowledge/neighbors")
        self.assertEqual(r.status_code, 400)
        self.assertIn("entity required", r.get_json()["error"])
        self.knowledge.get_neighbors.assert_not_called()

    def test_infer(self):
        self.knowledge.infer_relations.return_value = [{"rel": "new"}]
        r = self.client.get("/api/agi/knowledge/infer")
        self.assertEqual(r.get_json(), [{"rel": "new"}])
        self.knowledge.infer_relations.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
