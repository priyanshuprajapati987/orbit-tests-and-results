"""Unit tests for orbit/orbit/core/domain_mastery_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.domain_mastery_bp import domain_mastery_bp


class DomainMasteryBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(domain_mastery_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(domain_mastery_bp.name, "domain_mastery_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/domain-mastery/domains",
                  "/api/domain-mastery/domains/<domain_name>",
                  "/api/domain-mastery/domains/<domain_name>/progress",
                  "/api/domain-mastery/domains/<domain_name>/next-action",
                  "/api/domain-mastery/domains/<domain_name>/knowledge",
                  "/api/domain-mastery/domains/<domain_name>/practice",
                  "/api/domain-mastery/domains/<domain_name>/benchmarks",
                  "/api/domain-mastery/domains/<domain_name>/insights",
                  "/api/domain-mastery/reset"]:
            self.assertIn(p, rules)


class TestDomainsList(DomainMasteryBpBase):
    def test_list(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.get_domains.return_value = [{"name": "python"}]
            r = self.client.get("/api/domain-mastery/domains")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["domains"], [{"name": "python"}])

    def test_list_empty(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.get_domains.return_value = []
            r = self.client.get("/api/domain-mastery/domains")
        self.assertEqual(r.get_json()["domains"], [])


class TestDomainCreate(DomainMasteryBpBase):
    def test_create_defaults(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.register_domain.return_value = {"name": "python"}
            r = self.client.post("/api/domain-mastery/domains", json={"name": "python"})
        self.assertEqual(r.status_code, 200)
        gm.return_value.register_domain.assert_called_once_with(
            name="python", description="", tags=None)

    def test_create_all_fields(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.register_domain.return_value = {"name": "py"}
            r = self.client.post("/api/domain-mastery/domains", json={
                "name": "py", "description": "D", "tags": ["a", "b"]})
        gm.return_value.register_domain.assert_called_once_with(
            name="py", description="D", tags=["a", "b"])

    def test_create_no_body(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.register_domain.return_value = {"name": ""}
            r = self.client.post("/api/domain-mastery/domains")
        self.assertEqual(r.status_code, 200)
        gm.return_value.register_domain.assert_called_once_with(
            name="", description="", tags=None)


class TestDomainDetail(DomainMasteryBpBase):
    def test_found(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.get_domain.return_value = {"name": "python"}
            r = self.client.get("/api/domain-mastery/domains/python")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["name"], "python")

    def test_not_found_404(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.get_domain.return_value = None
            r = self.client.get("/api/domain-mastery/domains/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "domain not found")


class TestDomainProgress(DomainMasteryBpBase):
    def test_found(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.get_phase_progress.return_value = {"phase": 2}
            r = self.client.get("/api/domain-mastery/domains/python/progress")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["phase"], 2)

    def test_not_found_404(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.get_phase_progress.return_value = None
            r = self.client.get("/api/domain-mastery/domains/nope/progress")
        self.assertEqual(r.status_code, 404)


class TestNextAction(DomainMasteryBpBase):
    def test_found(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.suggest_next_action.return_value = "read docs"
            r = self.client.get("/api/domain-mastery/domains/python/next-action")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "read docs")

    def test_none_404(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.suggest_next_action.return_value = None
            r = self.client.get("/api/domain-mastery/domains/nope/next-action")
        self.assertEqual(r.status_code, 404)


class TestKnowledgeAdd(DomainMasteryBpBase):
    def test_add_defaults(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_knowledge.return_value = {"id": "k1"}
            r = self.client.post("/api/domain-mastery/domains/python/knowledge",
                                 json={"title": "T"})
        self.assertEqual(r.status_code, 200)
        gm.return_value.add_knowledge.assert_called_once_with(
            domain_name="python", title="T", source="",
            content_type="article", summary="", tags=None)

    def test_add_all_fields(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_knowledge.return_value = {"id": "k1"}
            r = self.client.post("/api/domain-mastery/domains/python/knowledge", json={
                "title": "T", "source": "S", "content_type": "video",
                "summary": "sum", "tags": ["x"]})
        gm.return_value.add_knowledge.assert_called_once_with(
            domain_name="python", title="T", source="S",
            content_type="video", summary="sum", tags=["x"])

    def test_domain_not_found_404(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_knowledge.return_value = None
            r = self.client.post("/api/domain-mastery/domains/nope/knowledge",
                                 json={"title": "T"})
        self.assertEqual(r.status_code, 404)


class TestPracticeAdd(DomainMasteryBpBase):
    def test_add_defaults(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_practice.return_value = {"id": "p1"}
            r = self.client.post("/api/domain-mastery/domains/python/practice",
                                 json={"score": 85, "latency_ms": 120})
        self.assertEqual(r.status_code, 200)
        gm.return_value.add_practice.assert_called_once_with(
            domain_name="python", task="", score=85.0, latency_ms=120.0,
            notes="", agent="system")

    def test_add_string_numbers_coerced(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_practice.return_value = {"id": "p1"}
            r = self.client.post("/api/domain-mastery/domains/python/practice",
                                 json={"score": "90.5", "latency_ms": "10",
                                       "task": "T", "notes": "N", "agent": "bot"})
        gm.return_value.add_practice.assert_called_once_with(
            domain_name="python", task="T", score=90.5, latency_ms=10.0,
            notes="N", agent="bot")

    def test_bad_score_400(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            r = self.client.post("/api/domain-mastery/domains/python/practice",
                                 json={"score": "abc", "latency_ms": 1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("must be numbers", r.get_json()["error"])
        gm.return_value.add_practice.assert_not_called()

    def test_none_score_400(self):
        r = self.client.post("/api/domain-mastery/domains/python/practice",
                             json={"score": None, "latency_ms": 1})
        self.assertEqual(r.status_code, 400)

    def test_domain_not_found_404(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_practice.return_value = None
            r = self.client.post("/api/domain-mastery/domains/nope/practice",
                                 json={"score": 1, "latency_ms": 1})
        self.assertEqual(r.status_code, 404)


class TestBenchmarkAdd(DomainMasteryBpBase):
    def test_add_defaults(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_benchmark.return_value = {"id": "b1"}
            r = self.client.post("/api/domain-mastery/domains/python/benchmarks",
                                 json={"score": 70})
        self.assertEqual(r.status_code, 200)
        gm.return_value.add_benchmark.assert_called_once_with(
            domain_name="python", benchmark_name="", score=70.0,
            expert_score=100.0, metrics=None)

    def test_add_all_fields(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_benchmark.return_value = {"id": "b1"}
            r = self.client.post("/api/domain-mastery/domains/python/benchmarks", json={
                "benchmark_name": "BM", "score": "80", "expert_score": "95",
                "metrics": {"acc": 0.9}})
        gm.return_value.add_benchmark.assert_called_once_with(
            domain_name="python", benchmark_name="BM", score=80.0,
            expert_score=95.0, metrics={"acc": 0.9})

    def test_bad_score_400(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            r = self.client.post("/api/domain-mastery/domains/python/benchmarks",
                                 json={"score": "abc"})
        self.assertEqual(r.status_code, 400)
        gm.return_value.add_benchmark.assert_not_called()

    def test_bad_expert_score_400(self):
        r = self.client.post("/api/domain-mastery/domains/python/benchmarks",
                             json={"score": 1, "expert_score": "xx"})
        self.assertEqual(r.status_code, 400)

    def test_domain_not_found_404(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_benchmark.return_value = None
            r = self.client.post("/api/domain-mastery/domains/nope/benchmarks",
                                 json={"score": 1})
        self.assertEqual(r.status_code, 404)


class TestInsightAdd(DomainMasteryBpBase):
    def test_add_defaults(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_insight.return_value = {"id": "i1"}
            r = self.client.post("/api/domain-mastery/domains/python/insights",
                                 json={"title": "T"})
        self.assertEqual(r.status_code, 200)
        gm.return_value.add_insight.assert_called_once_with(
            domain_name="python", title="T", content="",
            category="pattern", tags=None)

    def test_add_all_fields(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_insight.return_value = {"id": "i1"}
            r = self.client.post("/api/domain-mastery/domains/python/insights", json={
                "title": "T", "content": "C", "category": "trap", "tags": ["z"]})
        gm.return_value.add_insight.assert_called_once_with(
            domain_name="python", title="T", content="C",
            category="trap", tags=["z"])

    def test_domain_not_found_404(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.add_insight.return_value = None
            r = self.client.post("/api/domain-mastery/domains/nope/insights",
                                 json={"title": "T"})
        self.assertEqual(r.status_code, 404)


class TestDomainDeleteReset(DomainMasteryBpBase):
    def test_delete_ok(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.delete_domain.return_value = True
            r = self.client.delete("/api/domain-mastery/domains/python")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        gm.return_value.delete_domain.assert_called_once_with("python")

    def test_delete_missing(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            gm.return_value.delete_domain.return_value = False
            r = self.client.delete("/api/domain-mastery/domains/nope")
        self.assertFalse(r.get_json()["success"])

    def test_reset(self):
        with patch("orbit.core.domain_mastery_bp.get_domain_mastery") as gm:
            r = self.client.post("/api/domain-mastery/reset")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        gm.return_value.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
