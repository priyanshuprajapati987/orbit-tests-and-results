"""Unit tests for orbit/orbit/core/memory_graph_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.memory_graph_bp import memory_graph_bp


class TestMemoryGraphBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(memory_graph_bp)
        self.client = self.app.test_client()
        self.fake_mg = MagicMock()
        sys.modules["orbit.orbit.core.memory_graph"] = self.fake_mg

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.memory_graph", None)

    def test_blueprint_name(self):
        self.assertEqual(memory_graph_bp.name, "memory_graph")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/memory-graph/ingest", "/api/memory-graph/entity", "/api/memory-graph/relation",
                  "/api/memory-graph/neighbors/<entity>", "/api/memory-graph/path",
                  "/api/memory-graph/communities", "/api/memory-graph/stats"]:
            self.assertIn(p, rules)

    def test_ingest_missing_text_400(self):
        r = self.client.post("/api/memory-graph/ingest", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_ingest_success(self):
        self.fake_mg.get_memory_graph.return_value.ingest_text.return_value = {"ingested": 2}
        r = self.client.post("/api/memory-graph/ingest", json={"text": "hi", "source": "user"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["ingested"], 2)
        self.fake_mg.get_memory_graph.return_value.ingest_text.assert_called_once_with("hi", source="user")

    def test_ingest_no_body(self):
        r = self.client.post("/api/memory-graph/ingest")
        self.assertEqual(r.status_code, 400)

    def test_add_entity_missing_name_400(self):
        r = self.client.post("/api/memory-graph/entity", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_entity_success(self):
        e = MagicMock()
        e.entity_id = "e1"
        e.name = "Alice"
        e.entity_type = "PERSON"
        self.fake_mg.get_memory_graph.return_value.add_entity.return_value = e
        r = self.client.post("/api/memory-graph/entity", json={"name": "Alice", "type": "PERSON", "properties": {"k": "v"}})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["entity_id"], "e1")
        self.assertEqual(body["name"], "Alice")
        self.assertEqual(body["type"], "PERSON")
        self.fake_mg.get_memory_graph.return_value.add_entity.assert_called_once_with("Alice", "PERSON", {"k": "v"})

    def test_add_entity_defaults(self):
        e = MagicMock()
        e.entity_id = "e2"
        e.name = "x"
        e.entity_type = "CONCEPT"
        self.fake_mg.get_memory_graph.return_value.add_entity.return_value = e
        r = self.client.post("/api/memory-graph/entity", json={"name": "x"})
        self.fake_mg.get_memory_graph.return_value.add_entity.assert_called_once_with("x", "CONCEPT", None)

    def test_add_entity_no_body(self):
        r = self.client.post("/api/memory-graph/entity")
        self.assertEqual(r.status_code, 400)

    def test_add_relation_missing_fields_400(self):
        r = self.client.post("/api/memory-graph/relation", json={"source": "a"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_relation_success(self):
        rel = MagicMock()
        rel.source_id = "s"
        rel.target_id = "t"
        rel.relation_type = "knows"
        self.fake_mg.get_memory_graph.return_value.add_relation.return_value = rel
        r = self.client.post("/api/memory-graph/relation", json={"source": "a", "target": "b", "relation_type": "knows", "weight": 0.5})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["source"], "s")
        self.assertEqual(body["target"], "t")
        self.assertEqual(body["relation"], "knows")
        self.fake_mg.get_memory_graph.return_value.add_relation.assert_called_once_with("a", "b", "knows", weight=0.5)

    def test_add_relation_default_weight(self):
        rel = MagicMock()
        rel.source_id = "s"
        rel.target_id = "t"
        rel.relation_type = "r"
        self.fake_mg.get_memory_graph.return_value.add_relation.return_value = rel
        r = self.client.post("/api/memory-graph/relation", json={"source": "a", "target": "b", "relation_type": "r"})
        self.fake_mg.get_memory_graph.return_value.add_relation.assert_called_once_with("a", "b", "r", weight=1.0)

    def test_add_relation_no_body(self):
        r = self.client.post("/api/memory-graph/relation")
        self.assertEqual(r.status_code, 400)

    def test_neighbors(self):
        self.fake_mg.get_memory_graph.return_value.neighbors.return_value = ["n1"]
        r = self.client.get("/api/memory-graph/neighbors/Alice?direction=out&rel_type=knows")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["entity"], "Alice")
        self.assertEqual(r.get_json()["neighbors"], ["n1"])
        self.fake_mg.get_memory_graph.return_value.neighbors.assert_called_once_with("Alice", "out", "knows")

    def test_neighbors_defaults(self):
        self.fake_mg.get_memory_graph.return_value.neighbors.return_value = []
        r = self.client.get("/api/memory-graph/neighbors/Alice")
        self.fake_mg.get_memory_graph.return_value.neighbors.assert_called_once_with("Alice", "both", None)

    def test_path_missing_params_400(self):
        r = self.client.get("/api/memory-graph/path")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_path_success(self):
        self.fake_mg.get_memory_graph.return_value.find_path.return_value = ["a", "b"]
        r = self.client.get("/api/memory-graph/path?source=a&target=b")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["source"], "a")
        self.assertEqual(body["target"], "b")
        self.assertEqual(body["path"], ["a", "b"])
        self.assertTrue(body["found"])
        self.fake_mg.get_memory_graph.return_value.find_path.assert_called_once_with("a", "b")

    def test_path_not_found(self):
        self.fake_mg.get_memory_graph.return_value.find_path.return_value = []
        r = self.client.get("/api/memory-graph/path?source=a&target=b")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["found"])

    def test_communities(self):
        self.fake_mg.get_memory_graph.return_value.communities.return_value = [["a", "b"]]
        r = self.client.get("/api/memory-graph/communities")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["communities"], [["a", "b"]])

    def test_stats(self):
        self.fake_mg.get_memory_graph.return_value.get_stats.return_value = {"nodes": 5}
        r = self.client.get("/api/memory-graph/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["nodes"], 5)


if __name__ == "__main__":
    unittest.main()
