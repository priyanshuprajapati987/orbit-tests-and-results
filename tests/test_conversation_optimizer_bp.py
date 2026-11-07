"""Unit tests for orbit/orbit/core/conversation_optimizer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.conversation_optimizer_bp import optimizer_bp


class TestConversationOptimizerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(optimizer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(optimizer_bp.name, "conversation_optimizer")

    def test_url_prefix(self):
        self.assertEqual(optimizer_bp.url_prefix, "/api/optimizer")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/optimizer/status", "/api/optimizer/cache/clear", "/api/optimizer/latency", "/api/optimizer/reset"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.conversation_optimizer_bp.get_conversation_optimizer") as go:
            go.return_value.get_stats.return_value = {"hits": 5}
            r = self.client.get("/api/optimizer/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["hits"], 5)

    def test_clear_cache(self):
        with patch("orbit.core.conversation_optimizer_bp.get_conversation_optimizer") as go:
            r = self.client.post("/api/optimizer/cache/clear")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        go.return_value._cache.clear.assert_called_once()

    def test_latency_default(self):
        with patch("orbit.core.conversation_optimizer_bp.get_conversation_optimizer") as go:
            go.return_value.get_latency_stats.return_value = {"avg": 1.2}
            r = self.client.get("/api/optimizer/latency")
        self.assertEqual(r.status_code, 200)
        go.return_value.get_latency_stats.assert_called_once_with(None)

    def test_latency_with_type(self):
        with patch("orbit.core.conversation_optimizer_bp.get_conversation_optimizer") as go:
            go.return_value.get_latency_stats.return_value = {"avg": 0.5}
            r = self.client.get("/api/optimizer/latency?type=chat")
        go.return_value.get_latency_stats.assert_called_once_with("chat")

    def test_reset(self):
        with patch("orbit.core.conversation_optimizer_bp.get_conversation_optimizer") as go:
            r = self.client.post("/api/optimizer/reset")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        go.return_value.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
