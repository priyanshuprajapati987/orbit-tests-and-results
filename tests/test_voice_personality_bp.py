"""Unit tests for orbit/orbit/core/voice_personality_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.voice_personality_bp import personality_bp


class TestVoicePersonalityBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(personality_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(personality_bp.name, "voice_personality")

    def test_url_prefix(self):
        self.assertEqual(personality_bp.url_prefix, "/api/voice/personality")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/voice/personality/status", "/api/voice/personality/emotion",
                  "/api/voice/personality/detect", "/api/voice/personality/history",
                  "/api/voice/personality/reset"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.is_enabled.return_value = True
            vp._current_emotion = "happy"
            vp.get_stats.return_value = {"calls": 5}
            r = self.client.get("/api/voice/personality/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["enabled"])
        self.assertEqual(body["current_emotion"], "happy")
        self.assertEqual(body["stats"], {"calls": 5})

    def test_set_emotion(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.set_emotion.return_value = {"emotion": "sad"}
            r = self.client.post("/api/voice/personality/emotion", json={"emotion": "sad"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["emotion"], "sad")
        vp.set_emotion.assert_called_once_with("sad")

    def test_set_emotion_default(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.set_emotion.return_value = {"emotion": "default"}
            r = self.client.post("/api/voice/personality/emotion", json={})
        vp.set_emotion.assert_called_once_with("default")

    def test_set_emotion_no_body(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.set_emotion.return_value = {"emotion": "default"}
            r = self.client.post("/api/voice/personality/emotion")
        vp.set_emotion.assert_called_once_with("default")

    def test_detect(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.detect_emotion.return_value = "happy"
            vp.get_voice_config.return_value = {"pitch": 1.2}
            r = self.client.post("/api/voice/personality/detect", json={"text": "I am great"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["emotion"], "happy")
        self.assertEqual(body["voice_config"], {"pitch": 1.2})
        vp.detect_emotion.assert_called_once_with("I am great")
        vp.get_voice_config.assert_called_once_with("happy")

    def test_detect_default_text(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.detect_emotion.return_value = "neutral"
            vp.get_voice_config.return_value = {}
            r = self.client.post("/api/voice/personality/detect", json={})
        vp.detect_emotion.assert_called_once_with("")

    def test_history(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.get_history.return_value = [{"e": "happy"}]
            r = self.client.get("/api/voice/personality/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["history"], [{"e": "happy"}])
        vp.get_history.assert_called_once_with(5)

    def test_history_default(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.get_history.return_value = []
            r = self.client.get("/api/voice/personality/history")
        vp.get_history.assert_called_once_with(20)

    def test_history_invalid_limit(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.get_history.return_value = []
            r = self.client.get("/api/voice/personality/history?limit=abc")
        self.assertEqual(r.status_code, 200)
        vp.get_history.assert_called_once_with(20)

    def test_history_clamped(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            vp.get_history.return_value = []
            r = self.client.get("/api/voice/personality/history?limit=500")
        vp.get_history.assert_called_once_with(200)

    def test_reset(self):
        with patch("orbit.core.voice_personality_bp.get_voice_personality") as gvp:
            vp = gvp.return_value
            r = self.client.post("/api/voice/personality/reset")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        self.assertEqual(r.get_json()["message"], "Voice personality reset")
        vp.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
