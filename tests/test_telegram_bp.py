"""Unit tests for orbit/orbit/core/telegram_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.telegram_bp import telegram_bp


class TestTelegramBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(telegram_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(telegram_bp.name, "telegram_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/telegram/status", "/api/telegram/start", "/api/telegram/stop",
                  "/api/telegram/history", "/api/telegram/send", "/api/telegram/users"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            gb.return_value.get_status.return_value = {"running": True}
            r = self.client.get("/api/telegram/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["running"])

    def test_start(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            gb.return_value.start.return_value = {"started": True}
            r = self.client.post("/api/telegram/start")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["started"])

    def test_stop(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            gb.return_value.stop.return_value = {"stopped": True}
            r = self.client.post("/api/telegram/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["stopped"])

    def test_history(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            gb.return_value.get_history.return_value = ["m1"]
            r = self.client.get("/api/telegram/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["history"], ["m1"])
        gb.return_value.get_history.assert_called_once_with(5)

    def test_history_default(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            gb.return_value.get_history.return_value = []
            r = self.client.get("/api/telegram/history")
        gb.return_value.get_history.assert_called_once_with(50)

    def test_send_missing_fields_400(self):
        r = self.client.post("/api/telegram/send", json={"text": "hi"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_send_success(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            gb.return_value.send_message.return_value = True
            r = self.client.post("/api/telegram/send", json={"chat_id": 123, "text": "hi"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["sent"])
        gb.return_value.send_message.assert_called_once_with(123, "hi")

    def test_send_bad_chat_id(self):
        r = self.client.post("/api/telegram/send", json={"chat_id": "abc", "text": "hi"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_send_no_body(self):
        r = self.client.post("/api/telegram/send")
        self.assertEqual(r.status_code, 400)

    def test_set_users_success(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            r = self.client.post("/api/telegram/users", json={"user_ids": ["1", "2"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["updated"], True)
        self.assertEqual(r.get_json()["count"], 2)
        gb.return_value.set_allowed_users.assert_called_once_with([1, 2])

    def test_set_users_bad_ids(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            gb.return_value.set_allowed_users.side_effect = ValueError("bad")
            r = self.client.post("/api/telegram/users", json={"user_ids": ["abc"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_set_users_no_body(self):
        with patch("orbit.core.telegram_bp._get_bot") as gb:
            r = self.client.post("/api/telegram/users")
        self.assertEqual(r.status_code, 200)
        gb.return_value.set_allowed_users.assert_called_once_with([])

    def test_register(self):
        from orbit.core.telegram_bp import register
        server = MagicMock() if False else __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        self.assertTrue(register(server))
        server.register_blueprint.assert_called_once_with(telegram_bp)


if __name__ == "__main__":
    unittest.main()
