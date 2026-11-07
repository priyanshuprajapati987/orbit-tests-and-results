"""Unit tests for orbit/orbit/core/initiative_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.initiative_bp import initiative_bp


class TestInitiativeBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(initiative_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(initiative_bp.name, "initiative")

    def test_url_prefix(self):
        self.assertEqual(initiative_bp.url_prefix, "/api/initiative")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/initiative/run", "/api/initiative/log", "/api/initiative/undo"]:
            self.assertIn(p, rules)

    def test_run_missing_message_400(self):
        r = self.client.post("/api/initiative/run", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_run_no_action(self):
        with patch("orbit.core.initiative_bp.get_initiative_engine") as gi:
            gi.return_value.run.return_value = None
            r = self.client.post("/api/initiative/run", json={"message": "hi"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["ok"])
        self.assertEqual(r.get_json()["reason"], "no safe initiative detected")

    def test_run_action(self):
        with patch("orbit.core.initiative_bp.get_initiative_engine") as gi:
            gi.return_value.run.return_value = {"id": "a1"}
            r = self.client.post("/api/initiative/run", json={"message": "hi"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["action"], {"id": "a1"})
        gi.return_value.run.assert_called_once_with("hi")

    def test_run_no_body(self):
        r = self.client.post("/api/initiative/run")
        self.assertEqual(r.status_code, 400)

    def test_log(self):
        with patch("orbit.core.initiative_bp.get_initiative_engine") as gi:
            gi.return_value.log.return_value = [{"id": "a1"}]
            r = self.client.get("/api/initiative/log?limit=10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["log"], [{"id": "a1"}])
        gi.return_value.log.assert_called_once_with(limit=10)

    def test_log_default(self):
        with patch("orbit.core.initiative_bp.get_initiative_engine") as gi:
            gi.return_value.log.return_value = []
            r = self.client.get("/api/initiative/log")
        gi.return_value.log.assert_called_once_with(limit=50)

    def test_undo_missing_id_400(self):
        r = self.client.post("/api/initiative/undo", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_undo_success(self):
        with patch("orbit.core.initiative_bp.get_initiative_engine") as gi:
            gi.return_value.undo.return_value = {"undone": True}
            r = self.client.post("/api/initiative/undo", json={"id": "a1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["undone"], True)
        gi.return_value.undo.assert_called_once_with("a1")

    def test_undo_no_body(self):
        r = self.client.post("/api/initiative/undo")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
