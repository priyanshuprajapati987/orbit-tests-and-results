"""Unit tests for orbit/orbit/core/smart_cache_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.smart_cache_bp import smart_cache_bp


class TestSmartCacheBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(smart_cache_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(smart_cache_bp.name, "smart_cache_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/smart-cache/status", "/api/smart-cache/entries", "/api/smart-cache/invalidate",
                  "/api/smart-cache/get", "/api/smart-cache/set"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            gc.return_value.get_stats.return_value = {"hits": 5}
            r = self.client.get("/api/smart-cache/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["hits"], 5)

    def test_entries(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            gc.return_value.get_entries.return_value = [{"q": "hi"}]
            r = self.client.get("/api/smart-cache/entries?limit=10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["entries"], [{"q": "hi"}])
        gc.return_value.get_entries.assert_called_once_with(10)

    def test_entries_default(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            gc.return_value.get_entries.return_value = []
            r = self.client.get("/api/smart-cache/entries")
        gc.return_value.get_entries.assert_called_once_with(50)

    def test_invalidate(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            r = self.client.post("/api/smart-cache/invalidate", json={"category": "code"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "invalidated")
        self.assertEqual(r.get_json()["category"], "code")
        gc.return_value.invalidate.assert_called_once_with("code")

    def test_invalidate_default(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            r = self.client.post("/api/smart-cache/invalidate", json={})
        gc.return_value.invalidate.assert_called_once_with(None)

    def test_invalidate_no_body(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            r = self.client.post("/api/smart-cache/invalidate")
        gc.return_value.invalidate.assert_called_once_with(None)

    def test_get_missing_query_400(self):
        r = self.client.post("/api/smart-cache/get", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_get_hit(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            gc.return_value.get.return_value = "cached response"
            r = self.client.post("/api/smart-cache/get", json={"query": "q", "category": "code"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["hit"])
        self.assertEqual(body["response"], "cached response")
        gc.return_value.get.assert_called_once_with("q", "code")

    def test_get_miss(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            gc.return_value.get.return_value = None
            r = self.client.post("/api/smart-cache/get", json={"query": "q"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertFalse(body["hit"])
        self.assertIsNone(body["response"])

    def test_get_default_category(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            gc.return_value.get.return_value = None
            r = self.client.post("/api/smart-cache/get", json={"query": "q"})
        gc.return_value.get.assert_called_once_with("q", "general")

    def test_get_no_body(self):
        r = self.client.post("/api/smart-cache/get")
        self.assertEqual(r.status_code, 400)

    def test_set_missing_fields_400(self):
        r = self.client.post("/api/smart-cache/set", json={"query": "q"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_set_success(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            r = self.client.post("/api/smart-cache/set", json={
                "query": "q", "response": "r", "category": "code",
                "tokens_in": 10, "tokens_out": 5
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "stored")
        gc.return_value.set.assert_called_once_with(query="q", response="r", category="code", tokens_in=10, tokens_out=5)

    def test_set_defaults(self):
        with patch("orbit.core.smart_cache_bp.get_smart_cache") as gc:
            r = self.client.post("/api/smart-cache/set", json={"query": "q", "response": "r"})
        gc.return_value.set.assert_called_once_with(query="q", response="r", category="general", tokens_in=0, tokens_out=0)

    def test_set_no_body(self):
        r = self.client.post("/api/smart-cache/set")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
