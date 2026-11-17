"""Unit tests for orbit/orbit/core/portkey_gateway_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.portkey_gateway_bp import portkey_gateway_bp


class TestPortkeyGatewayBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(portkey_gateway_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(portkey_gateway_bp.name, "portkey_gateway_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/gateway/status", "/api/gateway/models", "/api/gateway/config",
                  "/api/gateway/chat", "/api/gateway/chat/stream", "/api/gateway/start",
                  "/api/gateway/stop", "/api/gateway/metrics", "/api/gateway/metrics/reset",
                  "/api/gateway/config-template"]:
            self.assertIn(p, rules)

    def test_status(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.get_status.return_value = {"ok": True}
        r = self.client.get("/api/gateway/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        patch.stopall()

    def test_models(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.list_models.return_value = ["m1"]
        r = self.client.get("/api/gateway/models?provider=openai")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["models"], ["m1"])
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["provider_filter"], "openai")
        gw.return_value.list_models.assert_called_once_with(filter_provider="openai")
        patch.stopall()

    def test_models_default(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.list_models.return_value = []
        r = self.client.get("/api/gateway/models")
        gw.return_value.list_models.assert_called_once_with(filter_provider=None)
        patch.stopall()

    def test_config(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.get_config_template.return_value = {"template": True}
        r = self.client.get("/api/gateway/config")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["template"])
        patch.stopall()

    def test_update_config_missing_body_400(self):
        r = self.client.post("/api/gateway/config", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_update_config_success(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.update_config.return_value = {"updated": True}
        r = self.client.post("/api/gateway/config", json={"key": "val"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["config"], {"updated": True})
        gw.return_value.update_config.assert_called_once_with({"key": "val"})
        patch.stopall()

    def test_update_config_no_body(self):
        r = self.client.post("/api/gateway/config")
        self.assertEqual(r.status_code, 400)

    def test_chat_missing_messages_400(self):
        r = self.client.post("/api/gateway/chat", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_chat_bad_messages_400(self):
        r = self.client.post("/api/gateway/chat", json={"messages": "not a list"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_chat_message_missing_fields_400(self):
        r = self.client.post("/api/gateway/chat", json={"messages": [{"role": "user"}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_chat_success(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.generate.return_value = {"reply": "hi"}
        r = self.client.post("/api/gateway/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "model": "gpt-4", "temperature": 0.5, "max_tokens": 100, "config": {"x": 1}
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["reply"], "hi")
        gw.return_value.generate.assert_called_once_with(
            [{"role": "user", "content": "hi"}],
            model="gpt-4", temperature=0.5, max_tokens=100, config={"x": 1}
        )
        patch.stopall()

    def test_chat_defaults(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.generate.return_value = {"reply": "hi"}
        r = self.client.post("/api/gateway/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        gw.return_value.generate.assert_called_once_with(
            [{"role": "user", "content": "hi"}],
            model="gpt-4o-mini", temperature=None, max_tokens=None, config=None
        )
        patch.stopall()

    def test_chat_no_body(self):
        r = self.client.post("/api/gateway/chat")
        self.assertEqual(r.status_code, 400)

    def test_chat_stream(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.generate_stream.return_value = ["chunk1", "chunk2"]
        r = self.client.post("/api/gateway/chat/stream", json={"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r.content_type)
        body = r.get_data(as_text=True)
        self.assertIn("chunk1", body)
        self.assertIn("chunk2", body)
        self.assertIn("[DONE]", body)
        gw.return_value.generate_stream.assert_called_once_with(
            [{"role": "user", "content": "hi"}],
            model="gpt-4o-mini", temperature=None, max_tokens=None
        )
        patch.stopall()

    def test_chat_stream_missing_messages_400(self):
        r = self.client.post("/api/gateway/chat/stream", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_chat_stream_no_body(self):
        r = self.client.post("/api/gateway/chat/stream")
        self.assertEqual(r.status_code, 400)

    def test_start(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.start.return_value = {"started": True}
        r = self.client.post("/api/gateway/start")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["started"])
        gw.return_value.start.assert_called_once_with(auto_start=True)
        patch.stopall()

    def test_stop(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.stop.return_value = {"stopped": True}
        r = self.client.post("/api/gateway/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["stopped"])
        gw.return_value.stop.assert_called_once()
        patch.stopall()

    def test_metrics(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.get_metrics.return_value = {"total": 5}
        r = self.client.get("/api/gateway/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)
        patch.stopall()

    def test_metrics_reset(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.reset_metrics.return_value = {"reset": True}
        r = self.client.post("/api/gateway/metrics/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["metrics"], {"reset": True})
        gw.return_value.reset_metrics.assert_called_once()
        patch.stopall()

    def test_config_template(self):
        gw = patch("orbit.core.portkey_gateway_bp._get_gw").start()
        gw.return_value.get_config_template.return_value = {"template": True}
        r = self.client.get("/api/gateway/config-template")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["template"])
        patch.stopall()


if __name__ == "__main__":
    unittest.main()
