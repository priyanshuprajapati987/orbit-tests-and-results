"""Unit tests for orbit/orbit/core/agi_bp.py."""

import os
import sys
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.agi_bp import agi_bp

REFLECT = "orbit.core.self_reflection.get_reflection_engine"
WORLD = "orbit.core.world_model.get_world_model"
GOALS = "orbit.core.goal_autonomy.get_goal_engine"
CONSOL = "orbit.core.memory_consolidation.get_memory_consolidation"
META = "orbit.core.meta_cognition.get_meta_cognition"


def _entity(name="E", etype="concept", imp=0.6, mentions=3, attrs=None):
    return SimpleNamespace(name=name, type=etype, importance=imp,
                           mention_count=mentions,
                           attributes=attrs or {"k": "v"})


def _relation(source="a", target="b", rel_type="related_to"):
    return SimpleNamespace(source=source, target=target,
                           relation_type=rel_type)


def _goal(desc="G", prio="high", status="active", conf=0.9,
          progress=0.5, sub_tasks=None, blockers=None, source="user"):
    return SimpleNamespace(description=desc, priority=prio,
                           status=status, confidence=conf,
                           progress=progress,
                           sub_tasks=sub_tasks or [],
                           blockers=blockers or [], source=source)


def _event(desc="ev", entities=None, etype="update", ts=1700000000.0):
    return SimpleNamespace(description=desc, entities=entities or ["x"],
                           event_type=etype, timestamp=ts)


def _memory(content="m", category="fact", imp=0.7, strength=0.8):
    return SimpleNamespace(content=content, category=category,
                           importance=imp, strength=strength)


def _reflect_result(qtype="general", well="clarity", wrong="length",
                    improvement="be concise"):
    return SimpleNamespace(query_type=qtype, what_went_well=well,
                           what_went_wrong=wrong, improvement=improvement)


@dataclass
class FakeReport:
    ran: bool = True
    merged: int = 3


class AgiBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(agi_bp)
        self.client = self.app.test_client()
        self.reflection = MagicMock()
        self.world = MagicMock()
        self.goals = MagicMock()
        self.consol = MagicMock()
        self.meta = MagicMock()
        for target, mock in (
            (REFLECT, self.reflection),
            (WORLD, self.world),
            (GOALS, self.goals),
            (CONSOL, self.consol),
            (META, self.meta),
        ):
            p = patch(target, return_value=mock)
            p.start()
            self.addCleanup(p.stop)

    def test_blueprint_name(self):
        self.assertEqual(agi_bp.name, "agi_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/agi/status", "/api/agi/reflection/stats",
                  "/api/agi/reflection/recent",
                  "/api/agi/reflection/reflect",
                  "/api/agi/reflection/weak-areas",
                  "/api/agi/world/stats", "/api/agi/world/entities",
                  "/api/agi/world/entity", "/api/agi/world/relation",
                  "/api/agi/world/goals", "/api/agi/world/goal",
                  "/api/agi/world/timeline", "/api/agi/world/traverse",
                  "/api/agi/goals/active", "/api/agi/goals/blocked",
                  "/api/agi/goals/suggestions", "/api/agi/goals/infer",
                  "/api/agi/goals/stats", "/api/agi/goals/summary",
                  "/api/agi/consolidation/stats",
                  "/api/agi/consolidation/run",
                  "/api/agi/consolidation/insights",
                  "/api/agi/consolidation/recall",
                  "/api/agi/meta/stats",
                  "/api/agi/meta/self-awareness", "/api/agi/meta/gaps",
                  "/api/agi/meta/strategy/<category>",
                  "/api/agi/meta/reflect"]:
            self.assertIn(p, rules)


class TestCombinedStatus(AgiBpBase):
    def test_status_all_ok(self):
        self.reflection.get_stats.return_value = {"r": 1}
        self.world.get_stats.return_value = {"w": 2}
        self.goals.get_stats.return_value = {"g": 3}
        self.consol.get_stats.return_value = {"c": 4}
        self.meta.get_stats.return_value = {"m": 5}
        r = self.client.get("/api/agi/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {
            "reflection": {"r": 1},
            "world_model": {"w": 2},
            "goals": {"g": 3},
            "consolidation": {"c": 4},
            "meta_cognition": {"m": 5},
        })

    def test_status_engine_failure_500(self):
        # no try/except: first failing engine raises -> 500
        self.reflection.get_stats.side_effect = RuntimeError("down")
        r = self.client.get("/api/agi/status")
        self.assertEqual(r.status_code, 500)


class TestReflection(AgiBpBase):
    def test_stats(self):
        self.reflection.get_stats.return_value = {"total": 9}
        r = self.client.get("/api/agi/reflection/stats")
        self.assertEqual(r.get_json(), {"total": 9})

    def test_recent_default_limit(self):
        self.reflection.get_reflections.return_value = ["r1"]
        r = self.client.get("/api/agi/reflection/recent")
        self.assertEqual(r.get_json(), ["r1"])
        self.reflection.get_reflections.assert_called_once_with(10)

    def test_recent_custom_limit(self):
        self.reflection.get_reflections.return_value = []
        self.client.get("/api/agi/reflection/recent?limit=3")
        self.reflection.get_reflections.assert_called_once_with(3)

    def test_recent_bad_limit_defaults_10(self):
        self.reflection.get_reflections.return_value = []
        self.client.get("/api/agi/reflection/recent?limit=abc")
        self.reflection.get_reflections.assert_called_once_with(10)

    def test_reflect_success(self):
        self.reflection.reflect.return_value = ("better", "fix typo")
        r = self.client.post("/api/agi/reflection/reflect", json={
            "query": "q", "response": "r"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"improved": "better", "critique": "fix typo"})
        self.reflection.reflect.assert_called_once_with(
            "q", "r", "general")

    def test_reflect_with_category(self):
        self.reflection.reflect.return_value = ("i", "c")
        self.client.post("/api/agi/reflection/reflect", json={
            "query": "q", "response": "r", "category": "coding"})
        self.reflection.reflect.assert_called_once_with(
            "q", "r", "coding")

    def test_reflect_missing_query_400(self):
        r = self.client.post("/api/agi/reflection/reflect",
                             json={"response": "r"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"],
                         "query and response required")
        self.reflection.reflect.assert_not_called()

    def test_reflect_missing_response_400(self):
        r = self.client.post("/api/agi/reflection/reflect",
                             json={"query": "q"})
        self.assertEqual(r.status_code, 400)

    def test_reflect_no_body_400(self):
        r = self.client.post("/api/agi/reflection/reflect")
        self.assertEqual(r.status_code, 400)

    def test_weak_areas(self):
        self.reflection.get_weak_areas.return_value = ["math"]
        r = self.client.get("/api/agi/reflection/weak-areas")
        self.assertEqual(r.get_json(), ["math"])


class TestWorld(AgiBpBase):
    def test_stats(self):
        self.world.get_stats.return_value = {"entities": 30}
        r = self.client.get("/api/agi/world/stats")
        self.assertEqual(r.get_json(), {"entities": 30})

    def test_entities_default(self):
        self.world.get_top_entities.return_value = [_entity()]
        r = self.client.get("/api/agi/world/entities")
        self.assertEqual(r.get_json(), [{
            "name": "E", "type": "concept", "importance": 0.6,
            "mention_count": 3, "attributes": {"k": "v"}}])
        self.world.get_top_entities.assert_called_once_with(20)
        self.world.search_entities.assert_not_called()

    def test_entities_with_type_filter(self):
        self.world.search_entities.return_value = []
        r = self.client.get("/api/agi/world/entities?type=person&limit=5")
        self.assertEqual(r.get_json(), [])
        self.world.search_entities.assert_called_once_with(
            "", entity_type="person", limit=5)
        self.world.get_top_entities.assert_not_called()

    def test_entities_custom_limit(self):
        self.world.get_top_entities.return_value = []
        self.client.get("/api/agi/world/entities?limit=7")
        self.world.get_top_entities.assert_called_once_with(7)

    def test_add_entity(self):
        self.world.add_entity.return_value = _entity("Python", "lang")
        r = self.client.post("/api/agi/world/entity",
                             json={"name": "Python", "type": "lang"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"name": "Python", "type": "lang"})
        self.world.add_entity.assert_called_once_with(
            "Python", "lang", {})

    def test_add_entity_defaults(self):
        self.world.add_entity.return_value = _entity()
        self.client.post("/api/agi/world/entity", json={"name": "X"})
        self.world.add_entity.assert_called_once_with(
            "X", "concept", {})

    def test_add_entity_missing_name_400(self):
        r = self.client.post("/api/agi/world/entity", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "name required")
        self.world.add_entity.assert_not_called()

    def test_add_relation(self):
        self.world.add_relation.return_value = _relation(
            "a", "b", "causes")
        r = self.client.post("/api/agi/world/relation", json={
            "source": "a", "target": "b", "type": "causes"})
        self.assertEqual(r.get_json(),
                         {"source": "a", "target": "b", "type": "causes"})
        self.world.add_relation.assert_called_once_with("a", "b", "causes")

    def test_add_relation_defaults(self):
        self.world.add_relation.return_value = _relation()
        self.client.post("/api/agi/world/relation", json={
            "source": "a", "target": "b"})
        self.world.add_relation.assert_called_once_with(
            "a", "b", "related_to")

    def test_add_relation_missing_target_400(self):
        r = self.client.post("/api/agi/world/relation",
                             json={"source": "a"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"],
                         "source and target required")

    def test_world_goals_summary(self):
        self.world.get_goals_summary.return_value = {"active": 4}
        r = self.client.get("/api/agi/world/goals")
        self.assertEqual(r.get_json(), {"active": 4})

    def test_add_goal(self):
        self.world.add_goal.return_value = _goal("Ship it", "high",
                                                 "active")
        r = self.client.post("/api/agi/world/goal",
                             json={"description": "Ship it"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"description": "Ship it", "priority": "high",
                          "status": "active"})
        self.world.add_goal.assert_called_once_with(
            "Ship it", priority="medium", deadline=None,
            related_entities=[])

    def test_add_goal_full_fields(self):
        self.world.add_goal.return_value = _goal()
        self.client.post("/api/agi/world/goal", json={
            "description": "d", "priority": "low",
            "deadline": "2026-12-31", "related_entities": ["x"]})
        self.world.add_goal.assert_called_once_with(
            "d", priority="low", deadline="2026-12-31",
            related_entities=["x"])

    def test_add_goal_missing_description_400(self):
        r = self.client.post("/api/agi/world/goal", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "description required")
        self.world.add_goal.assert_not_called()

    def test_timeline_default_hours(self):
        self.world.get_recent_events.return_value = [_event()]
        r = self.client.get("/api/agi/world/timeline")
        self.assertEqual(r.get_json(), [{
            "description": "ev", "entities": ["x"],
            "type": "update", "timestamp": 1700000000.0}])
        self.world.get_recent_events.assert_called_once_with(hours=24)

    def test_timeline_custom_hours(self):
        self.world.get_recent_events.return_value = []
        self.client.get("/api/agi/world/timeline?hours=6")
        self.world.get_recent_events.assert_called_once_with(hours=6)

    def test_traverse_success(self):
        self.world.traverse.return_value = {"nodes": ["a", "b"]}
        r = self.client.get("/api/agi/world/traverse?entity=a")
        self.assertEqual(r.get_json(), {"nodes": ["a", "b"]})
        self.world.traverse.assert_called_once_with("a", depth=2)

    def test_traverse_custom_depth(self):
        self.world.traverse.return_value = {}
        self.client.get("/api/agi/world/traverse?entity=a&depth=5")
        self.world.traverse.assert_called_once_with("a", depth=5)

    def test_traverse_missing_entity_400(self):
        r = self.client.get("/api/agi/world/traverse")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "entity required")
        self.world.traverse.assert_not_called()


class TestGoals(AgiBpBase):
    def test_active(self):
        self.goals.get_goals.return_value = [
            _goal("G1", sub_tasks=["s1"])]
        r = self.client.get("/api/agi/goals/active")
        self.assertEqual(r.get_json(), [{
            "description": "G1", "confidence": 0.9, "priority": "high",
            "progress": 0.5, "sub_tasks": ["s1"], "blockers": []}])
        self.goals.get_goals.assert_called_once_with(status="active")

    def test_blocked(self):
        self.goals.get_goals.return_value = [
            _goal("G2", blockers=["no api key"])]
        r = self.client.get("/api/agi/goals/blocked")
        self.assertEqual(r.get_json(), [{
            "description": "G2", "blockers": ["no api key"],
            "priority": "high"}])
        self.goals.get_goals.assert_called_once_with(status="blocked")

    def test_suggestions(self):
        self.goals.get_proactive_suggestions.return_value = ["do x"]
        r = self.client.get("/api/agi/goals/suggestions")
        self.assertEqual(r.get_json(), ["do x"])

    def test_infer(self):
        self.goals.infer_goals.return_value = [_goal("inferred")]
        r = self.client.post("/api/agi/goals/infer",
                             json={"text": "I want to learn python"})
        self.assertEqual(r.get_json(), [{
            "description": "inferred", "confidence": 0.9,
            "source": "user", "sub_tasks": []}])
        self.goals.infer_goals.assert_called_once_with(
            "I want to learn python")

    def test_infer_missing_text_400(self):
        r = self.client.post("/api/agi/goals/infer", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "text required")
        self.goals.infer_goals.assert_not_called()

    def test_stats(self):
        self.goals.get_stats.return_value = {"active": 3}
        r = self.client.get("/api/agi/goals/stats")
        self.assertEqual(r.get_json(), {"active": 3})

    def test_summary(self):
        self.goals.get_summary.return_value = {"total": 10}
        r = self.client.get("/api/agi/goals/summary")
        self.assertEqual(r.get_json(), {"summary": {"total": 10}})


class TestConsolidation(AgiBpBase):
    def test_stats(self):
        self.consol.get_stats.return_value = {"runs": 2}
        r = self.client.get("/api/agi/consolidation/stats")
        self.assertEqual(r.get_json(), {"runs": 2})

    def test_run_dict_result(self):
        self.consol.consolidate.return_value = {"merged": 5}
        r = self.client.post("/api/agi/consolidation/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"merged": 5})

    def test_run_dataclass_result(self):
        # non-dict results go through dataclasses.asdict()
        self.consol.consolidate.return_value = FakeReport(ran=True,
                                                          merged=7)
        r = self.client.post("/api/agi/consolidation/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ran": True, "merged": 7})

    def test_run_exception_500(self):
        self.consol.consolidate.side_effect = RuntimeError("cons fail")
        r = self.client.post("/api/agi/consolidation/run")
        self.assertEqual(r.status_code, 500)

    def test_insights_default_limit(self):
        self.consol.get_insights.return_value = ["i1"]
        r = self.client.get("/api/agi/consolidation/insights")
        self.assertEqual(r.get_json(), ["i1"])
        self.consol.get_insights.assert_called_once_with(10)

    def test_insights_custom_limit(self):
        self.consol.get_insights.return_value = []
        self.client.get("/api/agi/consolidation/insights?limit=4")
        self.consol.get_insights.assert_called_once_with(4)

    def test_recall_success(self):
        self.consol.recall.return_value = [_memory()]
        r = self.client.get("/api/agi/consolidation/recall?q=python")
        self.assertEqual(r.get_json(), [{
            "content": "m", "category": "fact",
            "importance": 0.7, "strength": 0.8}])
        self.consol.recall.assert_called_once_with("python")

    def test_recall_missing_q_400(self):
        r = self.client.get("/api/agi/consolidation/recall")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "q required")
        self.consol.recall.assert_not_called()

    def test_recall_blank_q_400(self):
        r = self.client.get("/api/agi/consolidation/recall?q=")
        self.assertEqual(r.status_code, 400)


class TestMeta(AgiBpBase):
    def test_stats(self):
        self.meta.get_stats.return_value = {"cycles": 4}
        r = self.client.get("/api/agi/meta/stats")
        self.assertEqual(r.get_json(), {"cycles": 4})

    def test_self_awareness(self):
        self.meta.get_self_awareness.return_value = {"weakness": "speed"}
        r = self.client.get("/api/agi/meta/self-awareness")
        self.assertEqual(r.get_json(), {"weakness": "speed"})

    def test_gaps(self):
        self.meta.get_knowledge_gaps.return_value = ["quantum"]
        r = self.client.get("/api/agi/meta/gaps")
        self.assertEqual(r.get_json(), ["quantum"])

    def test_strategy(self):
        self.meta.get_strategy_advice.return_value = {"tip": "plan"}
        r = self.client.get("/api/agi/meta/strategy/coding")
        self.assertEqual(r.get_json(), {"tip": "plan"})
        self.meta.get_strategy_advice.assert_called_once_with("coding")

    def test_reflect_defaults(self):
        self.meta.reflect.return_value = _reflect_result()
        r = self.client.post("/api/agi/meta/reflect", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {
            "query_type": "general",
            "what_went_well": "clarity",
            "what_went_wrong": "length",
            "improvement": "be concise"})
        self.meta.reflect.assert_called_once_with(
            "general", "", 0.5)

    def test_reflect_full_fields(self):
        self.meta.reflect.return_value = _reflect_result(
            "coding", "logic", "off-by-one", "add tests")
        self.client.post("/api/agi/meta/reflect", json={
            "query_type": "coding", "response": "r", "quality": 0.9})
        self.meta.reflect.assert_called_once_with(
            "coding", "r", 0.9)

    def test_reflect_exception_500(self):
        self.meta.reflect.side_effect = RuntimeError("meta fail")
        r = self.client.post("/api/agi/meta/reflect", json={})
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
