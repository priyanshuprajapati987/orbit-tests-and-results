"""Unit tests for orbit/orbit/core/hybrid_memory_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.hybrid_memory_bp import hybrid_memory_bp


class TestHybridMemoryBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(hybrid_memory_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(hybrid_memory_bp.name, "hybrid_memory")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/hybrid-memory/search", "/api/hybrid-memory/store",
                  "/api/hybrid-memory/stats", "/api/hybrid-memory/entities",
                  "/api/hybrid-memory/temporal", "/api/hybrid-memory/graph"]:
            self.assertIn(p, rules)

    def test_search_missing_q(self):
        r = self.client.get("/api/hybrid-memory/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_search_success(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value.search.return_value = ["r1", "r2"]
            r = self.client.get("/api/hybrid-memory/search?q=hi&limit=5&level=session")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["results"], ["r1", "r2"])
        self.assertEqual(body["count"], 2)
        gm.return_value.search.assert_called_once_with("hi", top_k=5, level="session")

    def test_search_default_level(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value.search.return_value = []
            r = self.client.get("/api/hybrid-memory/search?q=hi")
        gm.return_value.search.assert_called_once_with("hi", top_k=10, level=None)

    def test_store_missing_content_400(self):
        r = self.client.post("/api/hybrid-memory/store", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_store_success(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value.add.return_value = "id123"
            r = self.client.post("/api/hybrid-memory/store", json={
                "content": "hello", "type": "note", "level": "long", "source": "agent", "metadata": {"k": "v"}
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["id"], "id123")
        gm.return_value.add.assert_called_once_with("hello", memory_type="note", level="long", source="agent", metadata={"k": "v"})

    def test_store_defaults(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value.add.return_value = "id1"
            r = self.client.post("/api/hybrid-memory/store", json={"content": "hello"})
        gm.return_value.add.assert_called_once_with("hello", memory_type="conversation", level="session", source="user", metadata={})

    def test_store_no_body(self):
        r = self.client.post("/api/hybrid-memory/store")
        self.assertEqual(r.status_code, 400)

    def test_stats(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/hybrid-memory/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_entities(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value._entity_idx = {"a": 1, "b": 2}
            r = self.client.get("/api/hybrid-memory/entities")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["entities"], ["a", "b"])

    def test_temporal(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value.get_temporal_context.return_value = ["m1"]
            r = self.client.get("/api/hybrid-memory/temporal?hours=12")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["memories"], ["m1"])
        self.assertEqual(r.get_json()["count"], 1)
        gm.return_value.get_temporal_context.assert_called_once_with(hours=12)

    def test_temporal_default(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value.get_temporal_context.return_value = []
            r = self.client.get("/api/hybrid-memory/temporal")
        gm.return_value.get_temporal_context.assert_called_once_with(hours=24)

    def test_graph(self):
        with patch("orbit.core.hybrid_memory_bp.get_hybrid_memory") as gm:
            gm.return_value.get_entity_graph.return_value = {"nodes": 2}
            r = self.client.get("/api/hybrid-memory/graph")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["graph"], {"nodes": 2})
        self.assertEqual(body["nodes"], 1)


if __name__ == "__main__":
    unittest.main()
