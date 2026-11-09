"""Unit tests for orbit/orbit/core/webhook_system_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.webhook_system_bp import webhook_system_bp


def make_webhook(**kw):
    m = MagicMock()
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class TestWebhookSystemBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(webhook_system_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(webhook_system_bp.name, "webhook_system_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/webhooks/list", "/api/webhooks/register", "/api/webhooks/remove/<webhook_id>",
                  "/api/webhooks/enable/<webhook_id>", "/api/webhooks/event",
                  "/api/webhooks/verify", "/api/webhooks/events", "/api/webhooks/stats"]:
            self.assertIn(p, rules)

    def test_list(self):
        wh = make_webhook(webhook_id="w1", name="n", url="u", events=["e"], enabled=True, trigger_count=2, fail_count=1)
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.list_webhooks.return_value = [wh]
            r = self.client.get("/api/webhooks/list")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["webhook_id"], "w1")
        self.assertEqual(body[0]["name"], "n")
        self.assertEqual(body[0]["url"], "u")
        self.assertEqual(body[0]["events"], ["e"])
        self.assertTrue(body[0]["enabled"])
        self.assertEqual(body[0]["trigger_count"], 2)
        self.assertEqual(body[0]["fail_count"], 1)

    def test_list_empty(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.list_webhooks.return_value = []
            r = self.client.get("/api/webhooks/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])

    def test_register_missing_fields_400(self):
        r = self.client.post("/api/webhooks/register", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_register_missing_url_400(self):
        r = self.client.post("/api/webhooks/register", json={"name": "n"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_register_success(self):
        wh = make_webhook(webhook_id="w1", secret="s1")
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.register.return_value = wh
            r = self.client.post("/api/webhooks/register", json={"name": "n", "url": "u", "events": ["e"], "secret": "s"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["webhook_id"], "w1")
        self.assertEqual(body["secret"], "s1")
        self.assertEqual(body["status"], "registered")
        gw.return_value.register.assert_called_once_with("n", "u", ["e"], "s")

    def test_register_default_events(self):
        wh = make_webhook(webhook_id="w2", secret="s2")
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.register.return_value = wh
            r = self.client.post("/api/webhooks/register", json={"name": "n", "url": "u"})
        gw.return_value.register.assert_called_once_with("n", "u", [], None)

    def test_register_no_body(self):
        r = self.client.post("/api/webhooks/register")
        self.assertEqual(r.status_code, 400)

    def test_remove(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.unregister.return_value = True
            r = self.client.post("/api/webhooks/remove/w1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "removed")
        gw.return_value.unregister.assert_called_once_with("w1")

    def test_remove_not_found(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.unregister.return_value = False
            r = self.client.post("/api/webhooks/remove/w1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "not_found")

    def test_enable(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.enable.return_value = True
            r = self.client.post("/api/webhooks/enable/w1", json={"enabled": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "enabled")
        gw.return_value.enable.assert_called_once_with("w1", False)

    def test_enable_default(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.enable.return_value = True
            r = self.client.post("/api/webhooks/enable/w1", json={})
        gw.return_value.enable.assert_called_once_with("w1", True)

    def test_enable_no_body(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.enable.return_value = True
            r = self.client.post("/api/webhooks/enable/w1")
        gw.return_value.enable.assert_called_once_with("w1", True)

    def test_event_missing_event_type_400(self):
        r = self.client.post("/api/webhooks/event", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_event_success(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.receive_event.return_value = ["w1"]
            r = self.client.post("/api/webhooks/event", json={"event_type": "push", "payload": {"x": 1}})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["triggered"], ["w1"])
        self.assertEqual(body["count"], 1)
        gw.return_value.receive_event.assert_called_once_with("push", {"x": 1})

    def test_event_default_payload(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.receive_event.return_value = []
            r = self.client.post("/api/webhooks/event", json={"event_type": "push"})
        gw.return_value.receive_event.assert_called_once_with("push", {})

    def test_event_no_body(self):
        r = self.client.post("/api/webhooks/event")
        self.assertEqual(r.status_code, 400)

    def test_verify_missing_fields_400(self):
        r = self.client.post("/api/webhooks/verify", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_verify_success(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.verify_signature.return_value = True
            r = self.client.post("/api/webhooks/verify", json={"payload": "data", "signature": "sig", "secret": "sec"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["valid"])
        gw.return_value.verify_signature.assert_called_once_with(b"data", "sig", "sec")

    def test_verify_no_body(self):
        r = self.client.post("/api/webhooks/verify")
        self.assertEqual(r.status_code, 400)

    def test_events(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.get_events.return_value = [{"id": 1}]
            r = self.client.get("/api/webhooks/events?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"id": 1}])
        gw.return_value.get_events.assert_called_once_with(5)

    def test_events_default(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.get_events.return_value = []
            r = self.client.get("/api/webhooks/events")
        gw.return_value.get_events.assert_called_once_with(50)

    def test_stats(self):
        with patch("orbit.core.webhook_system_bp.get_webhook_system") as gw:
            gw.return_value.get_stats.return_value = {"total": 3}
            r = self.client.get("/api/webhooks/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 3)


if __name__ == "__main__":
    unittest.main()
