"""Unit tests for orbit/orbit/core/moa_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.moa_bp import moa_bp


@dataclass
class FakeResult:
    answer: str = "ans"


class TestMoaBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(moa_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(moa_bp.name, "moa")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/moa/reason", "/api/moa/models", "/api/moa/stats"]:
            self.assertIn(p, rules)

    def test_reason_missing_query_400(self):
        r = self.client.post("/api/moa/reason", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_reason_success(self):
        moa = MagicMock()
        moa.query.return_value = FakeResult("ans")
        moa.get_providers.return_value = ["p1"]
        moa.get_history.return_value = []
        with patch("orbit.core.moa_bp.get_moa", return_value=moa):
            r = self.client.post("/api/moa/reason", json={"query": "q", "strategy": "synthesis", "max_agents": 2})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["answer"], "ans")
        moa.query.assert_called_once_with("q", strategy="synthesis")

    def test_reason_no_body(self):
        r = self.client.post("/api/moa/reason")
        self.assertEqual(r.status_code, 400)

    def test_models(self):
        moa = MagicMock()
        moa.get_providers.return_value = ["p1", "p2"]
        moa.get_history.return_value = [1, 2, 3]
        with patch("orbit.core.moa_bp.get_moa", return_value=moa):
            r = self.client.get("/api/moa/models")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["models"], ["p1", "p2"])
        self.assertEqual(body["history_count"], 3)

    def test_stats(self):
        moa = MagicMock()
        moa.get_providers.return_value = ["p1"]
        moa.get_history.return_value = [1]
        with patch("orbit.core.moa_bp.get_moa", return_value=moa):
            r = self.client.get("/api/moa/stats")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["providers"], ["p1"])
        self.assertEqual(body["total_queries"], 1)


if __name__ == "__main__":
    unittest.main()
