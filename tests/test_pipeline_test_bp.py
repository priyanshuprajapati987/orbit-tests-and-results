"""Unit tests for orbit/orbit/core/pipeline_test_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.pipeline_test_bp import pipeline_bp


class TestPipelineTestBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(pipeline_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(pipeline_bp.name, "pipeline")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/pipeline/test", rules)
        self.assertIn("/api/pipeline/history", rules)

    def test_pipeline_test(self):
        with patch("orbit.core.pipeline_test_bp.get_tester") as gt:
            gt.return_value.run_full_test.return_value = [{"name": "t1", "pass": True}]
            r = self.client.get("/api/pipeline/test")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["results"], [{"name": "t1", "pass": True}])

    def test_pipeline_history(self):
        with patch("orbit.core.pipeline_test_bp.get_tester") as gt:
            gt.return_value.get_history.return_value = [{"name": "t1"}, {"name": "t2"}]
            r = self.client.get("/api/pipeline/history")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["tests"]), 2)


if __name__ == "__main__":
    unittest.main()
