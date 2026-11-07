"""Unit tests for orbit/orbit/core/adaptive_rate_limiter_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.adaptive_rate_limiter_bp import adaptive_rate_limiter_bp


class TestAdaptiveRateLimiterBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(adaptive_rate_limiter_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(adaptive_rate_limiter_bp.name, "adaptive_rate_limiter_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/rate-limiter/status", "/api/rate-limiter/check/<provider>",
                  "/api/rate-limiter/set", "/api/rate-limiter/reset/<provider>",
                  "/api/rate-limiter/health"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.adaptive_rate_limiter_bp.get_adaptive_limiter") as gl:
            gl.return_value.get_status.return_value = {"providers": 2}
            r = self.client.get("/api/rate-limiter/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["providers"], 2)

    def test_check(self):
        with patch("orbit.core.adaptive_rate_limiter_bp.get_adaptive_limiter") as gl:
            gl.return_value.can_proceed.return_value = {"allowed": True}
            r = self.client.get("/api/rate-limiter/check/openai")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["allowed"])
        gl.return_value.can_proceed.assert_called_once_with("openai")

    def test_set_missing_provider_400(self):
        r = self.client.post("/api/rate-limiter/set", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_set_success(self):
        with patch("orbit.core.adaptive_rate_limiter_bp.get_adaptive_limiter") as gl:
            r = self.client.post("/api/rate-limiter/set", json={"provider": "openai", "rate": 30})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["provider"], "openai")
        self.assertEqual(r.get_json()["rate"], 30)
        gl.return_value.set_rate.assert_called_once_with("openai", 30)

    def test_set_default_rate(self):
        with patch("orbit.core.adaptive_rate_limiter_bp.get_adaptive_limiter") as gl:
            r = self.client.post("/api/rate-limiter/set", json={"provider": "openai"})
        gl.return_value.set_rate.assert_called_once_with("openai", 60)

    def test_set_no_body(self):
        r = self.client.post("/api/rate-limiter/set")
        self.assertEqual(r.status_code, 400)

    def test_reset(self):
        with patch("orbit.core.adaptive_rate_limiter_bp.get_adaptive_limiter") as gl:
            r = self.client.post("/api/rate-limiter/reset/openai")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["provider"], "openai")
        self.assertEqual(r.get_json()["status"], "reset")
        gl.return_value.reset_provider.assert_called_once_with("openai")

    def test_health_missing_provider_400(self):
        r = self.client.post("/api/rate-limiter/health", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_health_success(self):
        with patch("orbit.core.adaptive_rate_limiter_bp.get_adaptive_limiter") as gl:
            r = self.client.post("/api/rate-limiter/health", json={"provider": "openai", "latency_ms": 120, "success": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "recorded")
        gl.return_value.record_request.assert_called_once_with("openai", False, 120)

    def test_health_defaults(self):
        with patch("orbit.core.adaptive_rate_limiter_bp.get_adaptive_limiter") as gl:
            r = self.client.post("/api/rate-limiter/health", json={"provider": "openai"})
        gl.return_value.record_request.assert_called_once_with("openai", True, 0)

    def test_health_no_body(self):
        r = self.client.post("/api/rate-limiter/health")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
