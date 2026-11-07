"""Unit tests for orbit/orbit/core/macro_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.macro_bp import macro_bp


class TestMacroBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(macro_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(macro_bp.name, "macro")

    def test_url_prefix(self):
        self.assertEqual(macro_bp.url_prefix, "/api/macro")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/macro/record", "/api/macro/list", "/api/macro/replay"]:
            self.assertIn(p, rules)

    def test_record_success(self):
        with patch("orbit.core.macro_bp.get_macro_learner") as gm:
            gm.return_value.record.return_value = {"ok": True, "name": "m1"}
            r = self.client.post("/api/macro/record", json={"name": "m1", "steps": [1, 2]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        gm.return_value.record.assert_called_once_with("m1", [1, 2])

    def test_record_failure(self):
        with patch("orbit.core.macro_bp.get_macro_learner") as gm:
            gm.return_value.record.return_value = {"ok": False, "error": "dup"}
            r = self.client.post("/api/macro/record", json={"name": "m1", "steps": []})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()["ok"])

    def test_record_no_body(self):
        with patch("orbit.core.macro_bp.get_macro_learner") as gm:
            gm.return_value.record.return_value = {"ok": False, "error": "no name"}
            r = self.client.post("/api/macro/record")
        self.assertEqual(r.status_code, 400)

    def test_list(self):
        with patch("orbit.core.macro_bp.get_macro_learner") as gm:
            gm.return_value.list_macros.return_value = ["m1", "m2"]
            r = self.client.get("/api/macro/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), ["m1", "m2"])

    def test_replay_success(self):
        with patch("orbit.core.macro_bp.get_macro_learner") as gm:
            gm.return_value.replay_plan.return_value = {"ok": True, "replayed": "m1"}
            r = self.client.post("/api/macro/replay", json={"name": "m1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        gm.return_value.replay_plan.assert_called_once_with("m1")

    def test_replay_failure_404(self):
        with patch("orbit.core.macro_bp.get_macro_learner") as gm:
            gm.return_value.replay_plan.return_value = {"ok": False, "error": "not found"}
            r = self.client.post("/api/macro/replay", json={"name": "m1"})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["ok"])

    def test_replay_no_body(self):
        with patch("orbit.core.macro_bp.get_macro_learner") as gm:
            gm.return_value.replay_plan.return_value = {"ok": False, "error": "no name"}
            r = self.client.post("/api/macro/replay")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
