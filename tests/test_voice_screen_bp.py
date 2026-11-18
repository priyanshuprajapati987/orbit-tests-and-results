"""Unit tests for orbit/orbit/core/voice_screen_bp.py."""

import json
import os
import queue
import sys
import unittest
from dataclasses import dataclass, asdict
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.voice_screen_bp import voice_screen_bp


@dataclass
class FakeEvent:
    kind: str
    text: str

    def to_dict(self):
        return asdict(self)


def _ctrl():
    ctrl = MagicMock()
    ctrl.get_status.return_value = {"active": False, "mode": None}
    ctrl.get_config.return_value = {"language": "en"}
    ctrl.set_config.return_value = {"status": "ok"}
    ctrl.get_config_schema.return_value = {"fields": ["language"]}
    ctrl.start.return_value = {"status": "started"}
    ctrl.stop.return_value = {"status": "stopped"}
    ctrl.handle_command.return_value = {"handled": True}
    ctrl._history = []
    return ctrl


class VoiceScreenBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(voice_screen_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(voice_screen_bp.name, "voice_screen")
        self.assertEqual(voice_screen_bp.url_prefix, "/api/voice-screen")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/voice-screen/status", "/api/voice-screen/start",
                  "/api/voice-screen/stop", "/api/voice-screen/config",
                  "/api/voice-screen/config/schema", "/api/voice-screen/command",
                  "/api/voice-screen/history", "/api/voice-screen/stream"]:
            self.assertIn(p, rules)


class TestStatus(VoiceScreenBpBase):
    def test_status(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/status")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["active"])

    def test_status_exception_500(self):
        with patch("orbit.core.voice_screen_bp.get_voice_screen",
                   side_effect=RuntimeError("boom")):
            r = self.client.get("/api/voice-screen/status")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")


class TestStart(VoiceScreenBpBase):
    def test_start_default_mode(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/start", json={})
        self.assertEqual(r.status_code, 200)
        ctrl.start.assert_called_once_with(mode=None)

    def test_start_with_mode(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/start", json={"mode": "handsfree"})
        ctrl.start.assert_called_once_with(mode="handsfree")

    def test_start_no_body(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/start")
        self.assertEqual(r.status_code, 200)
        ctrl.start.assert_called_once_with(mode=None)

    def test_start_exception_500(self):
        with patch("orbit.core.voice_screen_bp.get_voice_screen") as gm:
            gm.return_value.start.side_effect = RuntimeError("x")
            r = self.client.post("/api/voice-screen/start", json={})
        self.assertEqual(r.status_code, 500)


class TestStop(VoiceScreenBpBase):
    def test_stop(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "stopped")
        ctrl.stop.assert_called_once()

    def test_stop_exception_500(self):
        with patch("orbit.core.voice_screen_bp.get_voice_screen") as gm:
            gm.return_value.stop.side_effect = RuntimeError("x")
            r = self.client.post("/api/voice-screen/stop")
        self.assertEqual(r.status_code, 500)


class TestConfig(VoiceScreenBpBase):
    def test_get_config(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/config")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["language"], "en")

    def test_get_config_exception_500(self):
        with patch("orbit.core.voice_screen_bp.get_voice_screen",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/voice-screen/config")
        self.assertEqual(r.status_code, 500)

    def test_set_config(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/config", json={"language": "hi"})
        self.assertEqual(r.status_code, 200)
        ctrl.set_config.assert_called_once_with({"language": "hi"})

    def test_set_config_no_body(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/config")
        self.assertEqual(r.status_code, 200)
        ctrl.set_config.assert_called_once_with({})

    def test_set_config_exception_500(self):
        with patch("orbit.core.voice_screen_bp.get_voice_screen") as gm:
            gm.return_value.set_config.side_effect = RuntimeError("x")
            r = self.client.post("/api/voice-screen/config", json={})
        self.assertEqual(r.status_code, 500)


class TestConfigSchema(VoiceScreenBpBase):
    def test_schema(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/config/schema")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["fields"], ["language"])

    def test_schema_exception_500(self):
        with patch("orbit.core.voice_screen_bp.get_voice_screen",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/voice-screen/config/schema")
        self.assertEqual(r.status_code, 500)


class TestCommand(VoiceScreenBpBase):
    def test_command(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/command", json={"text": "hello"})
        self.assertEqual(r.status_code, 200)
        ctrl.handle_command.assert_called_once_with("hello")

    def test_command_default_text(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/command", json={})
        ctrl.handle_command.assert_called_once_with("")

    def test_command_no_body(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.post("/api/voice-screen/command")
        self.assertEqual(r.status_code, 200)

    def test_command_exception_500(self):
        with patch("orbit.core.voice_screen_bp.get_voice_screen") as gm:
            gm.return_value.handle_command.side_effect = RuntimeError("x")
            r = self.client.post("/api/voice-screen/command", json={"text": "a"})
        self.assertEqual(r.status_code, 500)


class TestHistory(VoiceScreenBpBase):
    def test_history_serializes_events(self):
        ctrl = _ctrl()
        ctrl._history = [FakeEvent("speech", "hi"), FakeEvent("action", "click")]
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/history")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0], {"kind": "speech", "text": "hi"})

    def test_history_default_limit(self):
        ctrl = _ctrl()
        ctrl._history = [FakeEvent("s", str(i)) for i in range(60)]
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/history")
        self.assertEqual(len(r.get_json()), 50)  # default limit 50 (last 50)

    def test_history_custom_limit(self):
        ctrl = _ctrl()
        ctrl._history = [FakeEvent("s", str(i)) for i in range(10)]
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/history?limit=3")
        self.assertEqual(len(r.get_json()), 3)
        # last 3 kept
        self.assertEqual(r.get_json()[-1]["text"], "9")

    def test_history_bad_limit_fallback(self):
        ctrl = _ctrl()
        ctrl._history = [FakeEvent("s", "a")]
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/history?limit=abc")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()), 1)

    def test_history_limit_clamped_low(self):
        ctrl = _ctrl()
        ctrl._history = [FakeEvent("s", str(i)) for i in range(5)]
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/history?limit=0")
        self.assertEqual(len(r.get_json()), 1)  # max(1, ...)

    def test_history_limit_clamped_high(self):
        ctrl = _ctrl()
        ctrl._history = [FakeEvent("s", "a")]
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/history?limit=99999")
        self.assertEqual(r.status_code, 200)  # clamped to 500, no crash

    def test_history_empty(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/history")
        self.assertEqual(r.get_json(), [])

    def test_history_exception_500(self):
        with patch("orbit.core.voice_screen_bp.get_voice_screen",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/voice-screen/history")
        self.assertEqual(r.status_code, 500)


class TestStream(VoiceScreenBpBase):
    def test_stream_headers_and_subscribe(self):
        ctrl = _ctrl()
        captured = {}

        def sub(q):
            captured["q"] = q

        ctrl.subscribe.side_effect = sub
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/stream", buffered=False)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "text/event-stream")
        self.assertEqual(r.headers["Cache-Control"], "no-cache")
        self.assertEqual(r.headers["X-Accel-Buffering"], "no")
        ctrl.subscribe.assert_called_once()
        self.assertIsInstance(captured["q"], queue.Queue)
        # consume generator to avoid warnings, then close
        r.response.close()

    def test_stream_yields_queued_message(self):
        ctrl = _ctrl()
        captured = {}
        ctrl.subscribe.side_effect = lambda q: captured.update(q=q)
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/stream", buffered=False)
        captured["q"].put({"kind": "speech", "text": "hello"})
        # werkzeug pre-fetches the first chunk during client.get (keepalive);
        # our queued message arrives on the following next()
        first = next(r.response)
        if isinstance(first, bytes):
            first = first.decode("utf-8")
        self.assertEqual(first, ": keepalive\n\n")
        line = next(r.response)
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        self.assertTrue(line.startswith("data: "))
        self.assertIn("hello", line)
        r.response.close()
        ctrl.unsubscribe.assert_called_once_with(captured["q"])

    def test_stream_keepalive_on_empty_queue(self):
        ctrl = _ctrl()
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/stream", buffered=False)
        # first q.get(timeout=1.0) blocks ~1s then yields keepalive
        line = next(r.response)
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        self.assertEqual(line, ": keepalive\n\n")
        r.response.close()

    def test_stream_unsubscribe_on_close(self):
        ctrl = _ctrl()
        captured = {}
        ctrl.subscribe.side_effect = lambda q: captured.update(q=q)
        with patch("orbit.core.voice_screen_bp.get_voice_screen", return_value=ctrl):
            r = self.client.get("/api/voice-screen/stream", buffered=False)
        r.response.close()
        ctrl.unsubscribe.assert_called_once_with(captured["q"])


if __name__ == "__main__":
    unittest.main()
