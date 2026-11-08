"""Unit tests for orbit/orbit/core/autonomous_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.autonomous_bp import autonomous_bp


class TestAutonomousBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(autonomous_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(autonomous_bp.name, "autonomous_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/autonomous/start", "/api/autonomous/status", "/api/autonomous/stop", "/api/autonomous/transcripts"]:
            self.assertIn(p, rules)

    def test_start(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.start.return_value = {"session_id": "s1"}
            r = self.client.get("/api/autonomous/start?opponent=chatgpt&minutes=10&topic=ai&max_turns=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["session_id"], "s1")
        ga.return_value.start.assert_called_once_with(opponent="chatgpt", minutes=10.0, topic="ai", max_turns=5, background=True)

    def test_start_defaults(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.start.return_value = {"session_id": "s2"}
            r = self.client.get("/api/autonomous/start")
        ga.return_value.start.assert_called_once_with(opponent="chatgpt", minutes=30.0, topic=None, max_turns=60, background=True)

    def test_start_bad_minutes(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.start.return_value = {"session_id": "s3"}
            r = self.client.get("/api/autonomous/start?minutes=abc")
        ga.return_value.start.assert_called_once_with(opponent="chatgpt", minutes=30.0, topic=None, max_turns=60, background=True)

    def test_start_bad_max_turns(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.start.return_value = {"session_id": "s4"}
            r = self.client.get("/api/autonomous/start?max_turns=xyz")
        ga.return_value.start.assert_called_once_with(opponent="chatgpt", minutes=30.0, topic=None, max_turns=60, background=True)

    def test_status(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.get_status.return_value = {"running": True}
            r = self.client.get("/api/autonomous/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["running"])
        ga.return_value.get_status.assert_called_once_with(None)

    def test_status_with_session(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.get_status.return_value = {"running": False}
            r = self.client.get("/api/autonomous/status?session_id=s1")
        ga.return_value.get_status.assert_called_once_with("s1")

    def test_stop(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.stop.return_value = True
            r = self.client.get("/api/autonomous/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["stopped"])
        ga.return_value.stop.assert_called_once_with(None)

    def test_stop_with_session(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.stop.return_value = False
            r = self.client.get("/api/autonomous/stop?session_id=s1")
        ga.return_value.stop.assert_called_once_with("s1")

    def test_transcripts(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.get_transcripts.return_value = ["t1", "t2"]
            r = self.client.get("/api/autonomous/transcripts?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["transcripts"], ["t1", "t2"])
        ga.return_value.get_transcripts.assert_called_once_with(5)

    def test_transcripts_default(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.get_transcripts.return_value = []
            r = self.client.get("/api/autonomous/transcripts")
        ga.return_value.get_transcripts.assert_called_once_with(10)

    def test_transcripts_bad_limit(self):
        with patch("orbit.core.autonomous_chat.get_autonomous") as ga:
            ga.return_value.get_transcripts.return_value = []
            r = self.client.get("/api/autonomous/transcripts?limit=abc")
        ga.return_value.get_transcripts.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
