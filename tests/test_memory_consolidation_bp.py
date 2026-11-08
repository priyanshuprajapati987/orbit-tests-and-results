"""Unit tests for orbit/orbit/core/memory_consolidation_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.memory_consolidation_bp import memory_consolidation_bp


class TestMemoryConsolidationBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(memory_consolidation_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(memory_consolidation_bp.name, "memory_consolidation")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/memory-consolidation/consolidate", "/api/memory-consolidation/search",
                  "/api/memory-consolidation/extract", "/api/memory-consolidation/merge",
                  "/api/memory-consolidation/prune", "/api/memory-consolidation/stats"]:
            self.assertIn(p, rules)

    def test_consolidate_dict_report(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.consolidate.return_value = {"consolidated": 3}
            r = self.client.post("/api/memory-consolidation/consolidate", json={"memories": ["a", "b"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["consolidated"], 3)
        gm.return_value.consolidate.assert_called_once_with(["a", "b"])

    def test_consolidate_no_body(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.consolidate.return_value = {"consolidated": 0}
            r = self.client.post("/api/memory-consolidation/consolidate")
        gm.return_value.consolidate.assert_called_once_with([])

    def test_search_missing_q_400(self):
        r = self.client.get("/api/memory-consolidation/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_search_success(self):
        with patch("orbit.core.memory_consolidation_bp.search_facts", return_value=["f1", "f2"]):
            r = self.client.get("/api/memory-consolidation/search?q=hello&top_k=5")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["facts"], ["f1", "f2"])
        self.assertEqual(body["count"], 2)

    def test_search_default_top_k(self):
        with patch("orbit.core.memory_consolidation_bp.search_facts", return_value=[]) as sf:
            r = self.client.get("/api/memory-consolidation/search?q=hello")
        sf.assert_called_once_with("hello", top_k=10)

    def test_extract_missing_memories_400(self):
        r = self.client.post("/api/memory-consolidation/extract", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_extract_success(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.extract_facts.return_value = []
            r = self.client.post("/api/memory-consolidation/extract", json={"memories": ["a"], "min_importance": 0.5})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["facts"], [])
        self.assertEqual(r.get_json()["count"], 0)
        gm.return_value.extract_facts.assert_called_once_with(["a"], 0.5)

    def test_extract_default_min_importance(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.extract_facts.return_value = []
            r = self.client.post("/api/memory-consolidation/extract", json={"memories": ["a"]})
        gm.return_value.extract_facts.assert_called_once_with(["a"], 0.3)

    def test_extract_no_body(self):
        r = self.client.post("/api/memory-consolidation/extract")
        self.assertEqual(r.status_code, 400)

    def test_merge(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.merge_duplicates.return_value = 3
            r = self.client.post("/api/memory-consolidation/merge?threshold=0.8")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["merged"], 3)
        gm.return_value.merge_duplicates.assert_called_once_with(0.8)

    def test_merge_default_threshold(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.merge_duplicates.return_value = 0
            r = self.client.post("/api/memory-consolidation/merge")
        gm.return_value.merge_duplicates.assert_called_once_with(0.7)

    def test_prune(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.prune_low_priority.return_value = 2
            r = self.client.post("/api/memory-consolidation/prune", json={"min_importance": 0.2, "max_age_days": 15})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["pruned"], 2)
        gm.return_value.prune_low_priority.assert_called_once_with(min_importance=0.2, max_age_days=15)

    def test_prune_defaults(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.prune_low_priority.return_value = 0
            r = self.client.post("/api/memory-consolidation/prune", json={})
        gm.return_value.prune_low_priority.assert_called_once_with(min_importance=0.15, max_age_days=30)

    def test_prune_no_body(self):
        with patch("orbit.core.memory_consolidation_bp.get_memory_consolidation") as gm:
            gm.return_value.prune_low_priority.return_value = 0
            r = self.client.post("/api/memory-consolidation/prune")
        gm.return_value.prune_low_priority.assert_called_once_with(min_importance=0.15, max_age_days=30)

    def test_stats(self):
        with patch("orbit.core.memory_consolidation_bp.get_consolidation_stats", return_value={"total": 5}):
            r = self.client.get("/api/memory-consolidation/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
