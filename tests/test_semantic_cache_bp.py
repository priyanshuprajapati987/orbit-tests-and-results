"""Unit tests for orbit/orbit/core/semantic_cache_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.semantic_cache_bp import semantic_cache_bp


class TestSemanticCacheBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(semantic_cache_bp)
        self.client = self.app.test_client()
        self.fake_sc = MagicMock()
        sys.modules["orbit.orbit.core.semantic_cache"] = self.fake_sc

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.semantic_cache", None)

    def test_blueprint_name(self):
        self.assertEqual(semantic_cache_bp.name, "semantic_cache")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/semantic-cache/lookup", "/api/semantic-cache/store",
                  "/api/semantic-cache/invalidate", "/api/semantic-cache/clear",
                  "/api/semantic-cache/stats", "/api/semantic-cache/top"]:
            self.assertIn(p, rules)

    def test_lookup_missing_query_400(self):
        r = self.client.post("/api/semantic-cache/lookup", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_lookup_hit(self):
        entry = MagicMock()
        entry.query = "q"
        entry.response = "r"
        entry.provider = "p"
        entry.model = "m"
        entry.hit_count = 3
        self.fake_sc.get_semantic_cache.return_value.lookup.return_value = entry
        r = self.client.post("/api/semantic-cache/lookup", json={"query": "q"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["hit"])
        self.assertEqual(body["query"], "q")
        self.assertEqual(body["response"], "r")
        self.assertEqual(body["provider"], "p")
        self.assertEqual(body["model"], "m")
        self.assertEqual(body["hits"], 3)
        self.fake_sc.get_semantic_cache.return_value.lookup.assert_called_once_with("q")

    def test_lookup_miss(self):
        self.fake_sc.get_semantic_cache.return_value.lookup.return_value = None
        r = self.client.post("/api/semantic-cache/lookup", json={"query": "q"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertFalse(body["hit"])
        self.assertEqual(body["query"], "q")

    def test_lookup_no_body(self):
        r = self.client.post("/api/semantic-cache/lookup")
        self.assertEqual(r.status_code, 400)

    def test_store_missing_fields_400(self):
        r = self.client.post("/api/semantic-cache/store", json={"query": "q"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_store_success(self):
        entry = MagicMock()
        entry.query = "q"
        self.fake_sc.get_semantic_cache.return_value.store.return_value = entry
        r = self.client.post("/api/semantic-cache/store", json={
            "query": "q", "response": "r", "provider": "p", "model": "m",
            "latency_ms": 10.5, "tokens": 5
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "stored")
        self.assertEqual(r.get_json()["query"], "q")
        self.fake_sc.get_semantic_cache.return_value.store.assert_called_once_with(
            query="q", response="r", provider="p", model="m", latency_ms=10.5, tokens=5
        )

    def test_store_defaults(self):
        entry = MagicMock()
        entry.query = "q"
        self.fake_sc.get_semantic_cache.return_value.store.return_value = entry
        r = self.client.post("/api/semantic-cache/store", json={"query": "q", "response": "r"})
        self.fake_sc.get_semantic_cache.return_value.store.assert_called_once_with(
            query="q", response="r", provider="", model="", latency_ms=0, tokens=0
        )

    def test_store_no_body(self):
        r = self.client.post("/api/semantic-cache/store")
        self.assertEqual(r.status_code, 400)

    def test_invalidate_missing_query_400(self):
        r = self.client.post("/api/semantic-cache/invalidate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_invalidate_success(self):
        self.fake_sc.get_semantic_cache.return_value.invalidate.return_value = 2
        r = self.client.post("/api/semantic-cache/invalidate", json={"query": "q"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["removed"], 2)
        self.assertEqual(r.get_json()["query"], "q")
        self.fake_sc.get_semantic_cache.return_value.invalidate.assert_called_once_with("q")

    def test_invalidate_no_body(self):
        r = self.client.post("/api/semantic-cache/invalidate")
        self.assertEqual(r.status_code, 400)

    def test_clear(self):
        self.fake_sc.get_semantic_cache.return_value.clear.return_value = 5
        r = self.client.post("/api/semantic-cache/clear")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cleared"], 5)

    def test_stats(self):
        self.fake_sc.get_semantic_cache.return_value.get_stats.return_value = {"hits": 3}
        r = self.client.get("/api/semantic-cache/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["hits"], 3)

    def test_top(self):
        self.fake_sc.get_semantic_cache.return_value.get_top_queries.return_value = ["q1"]
        r = self.client.get("/api/semantic-cache/top?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["queries"], ["q1"])
        self.fake_sc.get_semantic_cache.return_value.get_top_queries.assert_called_once_with(5)

    def test_top_default(self):
        self.fake_sc.get_semantic_cache.return_value.get_top_queries.return_value = []
        r = self.client.get("/api/semantic-cache/top")
        self.fake_sc.get_semantic_cache.return_value.get_top_queries.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
