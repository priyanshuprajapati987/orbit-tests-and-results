"""Unit tests for orbit/orbit/core/prefetch_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.prefetch_bp import prefetch_bp


class TestPrefetchBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(prefetch_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(prefetch_bp.name, "prefetch")

    def test_url_prefix(self):
        self.assertEqual(prefetch_bp.url_prefix, "/api/prefetch")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/prefetch/run", rules)
        self.assertIn("/api/prefetch/get", rules)

    def test_run(self):
        with patch("orbit.core.prefetch_bp.get_prefetch") as gp:
            gp.return_value.run.return_value = {"prefetched": 2}
            r = self.client.post("/api/prefetch/run", json={"topics": ["a", "b"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["prefetched"], 2)
        gp.return_value.run.assert_called_once_with(["a", "b"])

    def test_run_no_body(self):
        with patch("orbit.core.prefetch_bp.get_prefetch") as gp:
            gp.return_value.run.return_value = {"prefetched": 0}
            r = self.client.post("/api/prefetch/run")
        gp.return_value.run.assert_called_once_with([])

    def test_get(self):
        with patch("orbit.core.prefetch_bp.get_prefetch") as gp:
            gp.return_value.get.return_value = "brief text"
            r = self.client.get("/api/prefetch/get?topic=ai")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["topic"], "ai")
        self.assertEqual(r.get_json()["brief"], "brief text")
        gp.return_value.get.assert_called_once_with("ai")

    def test_get_default_topic(self):
        with patch("orbit.core.prefetch_bp.get_prefetch") as gp:
            gp.return_value.get.return_value = None
            r = self.client.get("/api/prefetch/get")
        gp.return_value.get.assert_called_once_with("")


if __name__ == "__main__":
    unittest.main()
