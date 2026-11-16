"""Unit tests for orbit/orbit/core/multi_tier_memory_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.multi_tier_memory_bp import multi_tier_memory_bp


class TestMultiTierMemoryBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(multi_tier_memory_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(multi_tier_memory_bp.name, "multi_tier_memory")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/multi-tier-memory/stats", "/api/multi-tier-memory/store",
                  "/api/multi-tier-memory/retrieve", "/api/multi-tier-memory/search",
                  "/api/multi-tier-memory/promote", "/api/multi-tier-memory/demote",
                  "/api/multi-tier-memory/consolidate", "/api/multi-tier-memory/reset",
                  "/api/multi-tier-memory/tiers"]:
            self.assertIn(p, rules)

    def test_stats(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.stats.return_value = {"total": 5}
            r = self.client.get("/api/multi-tier-memory/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_store_missing_key_400(self):
        r = self.client.post("/api/multi-tier-memory/store", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_store_success(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.store.return_value = "session"
            r = self.client.post("/api/multi-tier-memory/store", json={
                "key": "k", "value": "v", "importance": 0.8, "tier": "long", "source": "agent", "metadata": {"m": 1}
            })
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["key"], "k")
        self.assertEqual(body["tier"], "session")
        gm.return_value.store.assert_called_once_with("k", "v", tier="long", importance=0.8, source="agent", metadata={"m": 1})

    def test_store_defaults(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.store.return_value = "session"
            r = self.client.post("/api/multi-tier-memory/store", json={"key": "k", "value": "v"})
        gm.return_value.store.assert_called_once_with("k", "v", tier=None, importance=0.5, source="user", metadata={})

    def test_store_no_body(self):
        r = self.client.post("/api/multi-tier-memory/store")
        self.assertEqual(r.status_code, 400)

    def test_retrieve_missing_key_400(self):
        r = self.client.get("/api/multi-tier-memory/retrieve")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_retrieve_found(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.retrieve.return_value = ("value", "long")
            r = self.client.get("/api/multi-tier-memory/retrieve?key=k&cascade=false")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["found"])
        self.assertEqual(body["value"], "value")
        self.assertEqual(body["tier"], "long")
        gm.return_value.retrieve.assert_called_once_with("k", cascade=False)

    def test_retrieve_not_found_404(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.retrieve.return_value = (None, "session")
            r = self.client.get("/api/multi-tier-memory/retrieve?key=k")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["found"])
        self.assertEqual(r.get_json()["tier"], "session")

    def test_retrieve_cascade_default(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.retrieve.return_value = ("v", "session")
            r = self.client.get("/api/multi-tier-memory/retrieve?key=k")
        gm.return_value.retrieve.assert_called_once_with("k", cascade=True)

    def test_search_missing_q_400(self):
        r = self.client.get("/api/multi-tier-memory/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_search_success(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.search.return_value = ["r1"]
            r = self.client.get("/api/multi-tier-memory/search?q=hi&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], ["r1"])
        self.assertEqual(r.get_json()["count"], 1)
        gm.return_value.search.assert_called_once_with("hi", limit=5)

    def test_search_default_limit(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.search.return_value = []
            r = self.client.get("/api/multi-tier-memory/search?q=hi")
        gm.return_value.search.assert_called_once_with("hi", limit=10)

    def test_promote_missing_key_400(self):
        r = self.client.post("/api/multi-tier-memory/promote", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_promote_success(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.promote.return_value = True
            r = self.client.post("/api/multi-tier-memory/promote", json={"key": "k"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertTrue(r.get_json()["promoted"])
        gm.return_value.promote.assert_called_once_with("k")

    def test_promote_not_found(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.promote.return_value = False
            r = self.client.post("/api/multi-tier-memory/promote", json={"key": "k"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "not_found")
        self.assertFalse(r.get_json()["promoted"])

    def test_promote_no_body(self):
        r = self.client.post("/api/multi-tier-memory/promote")
        self.assertEqual(r.status_code, 400)

    def test_demote_missing_key_400(self):
        r = self.client.post("/api/multi-tier-memory/demote", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_demote_success(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.demote.return_value = True
            r = self.client.post("/api/multi-tier-memory/demote", json={"key": "k"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertTrue(r.get_json()["demoted"])
        gm.return_value.demote.assert_called_once_with("k")

    def test_demote_not_found(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.demote.return_value = False
            r = self.client.post("/api/multi-tier-memory/demote", json={"key": "k"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "not_found")
        self.assertFalse(r.get_json()["demoted"])

    def test_demote_no_body(self):
        r = self.client.post("/api/multi-tier-memory/demote")
        self.assertEqual(r.status_code, 400)

    def test_consolidate(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.consolidate.return_value = {"merged": 2}
            r = self.client.post("/api/multi-tier-memory/consolidate")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["result"], {"merged": 2})

    def test_reset(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            r = self.client.post("/api/multi-tier-memory/reset", json={"tier": "long"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["reset_tier"], "long")
        gm.return_value.reset.assert_called_once_with(tier="long")

    def test_reset_default(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            r = self.client.post("/api/multi-tier-memory/reset", json={})
        gm.return_value.reset.assert_called_once_with(tier=None)

    def test_reset_no_body(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            r = self.client.post("/api/multi-tier-memory/reset")
        gm.return_value.reset.assert_called_once_with(tier=None)

    def test_tiers(self):
        with patch("orbit.core.multi_tier_memory_bp.get_multi_tier_memory") as gm:
            gm.return_value.get_tier_names.return_value = ["session", "long"]
            r = self.client.get("/api/multi-tier-memory/tiers")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), ["session", "long"])


if __name__ == "__main__":
    unittest.main()
