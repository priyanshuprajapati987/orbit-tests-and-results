"""Unit tests for orbit/orbit/core/context_menu_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.context_menu_bp import context_menu_bp


class TestContextMenuBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(context_menu_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(context_menu_bp.name, "context_menu")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/context/actions", rules)
        self.assertIn("/api/context/execute", rules)

    def test_get_actions(self):
        with patch("orbit.core.context_menu_bp.get_context_menu") as gc:
            gc.return_value.get_actions.return_value = ["copy", "paste"]
            r = self.client.get("/api/context/actions?type=code")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["actions"], ["copy", "paste"])
        self.assertEqual(body["context_type"], "code")
        gc.return_value.get_actions.assert_called_once_with("code")

    def test_get_actions_default_type(self):
        with patch("orbit.core.context_menu_bp.get_context_menu") as gc:
            gc.return_value.get_actions.return_value = []
            r = self.client.get("/api/context/actions")
        gc.return_value.get_actions.assert_called_once_with("text")

    def test_get_actions_exception_500(self):
        with patch("orbit.core.context_menu_bp.get_context_menu", side_effect=RuntimeError("boom")):
            r = self.client.get("/api/context/actions")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_execute_action(self):
        with patch("orbit.core.context_menu_bp.get_context_menu") as gc:
            gc.return_value.execute_action.return_value = {"result": "done"}
            r = self.client.post("/api/context/execute", json={"action_id": "a1", "content": "hi", "context": "code"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result"], "done")
        gc.return_value.execute_action.assert_called_once_with(action_id="a1", content="hi", context="code")

    def test_execute_action_defaults(self):
        with patch("orbit.core.context_menu_bp.get_context_menu") as gc:
            gc.return_value.execute_action.return_value = {"result": "ok"}
            r = self.client.post("/api/context/execute", json={})
        gc.return_value.execute_action.assert_called_once_with(action_id="", content="", context="text")

    def test_execute_action_exception_500(self):
        with patch("orbit.core.context_menu_bp.get_context_menu", side_effect=RuntimeError("boom")):
            r = self.client.post("/api/context/execute", json={})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
