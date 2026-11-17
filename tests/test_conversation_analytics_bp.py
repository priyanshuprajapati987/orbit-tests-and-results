"""Unit tests for orbit/orbit/core/conversation_analytics_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.conversation_analytics_bp import conversation_analytics_bp


class TestConversationAnalyticsBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(conversation_analytics_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(conversation_analytics_bp.name, "conversation_analytics_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        expected = [
            "/api/conversation-analytics/dashboard",
            "/api/conversation-analytics/topics",
            "/api/conversation-analytics/hourly",
            "/api/conversation-analytics/agents",
            "/api/conversation-analytics/satisfaction",
            "/api/conversation-analytics/quality",
            "/api/conversation-analytics/session/start",
            "/api/conversation-analytics/session/turn",
            "/api/conversation-analytics/session/end",
        ]
        for p in expected:
            self.assertIn(p, rules)

    def test_dashboard(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            ga.return_value.get_dashboard.return_value = {"total": 10}
            r = self.client.get("/api/conversation-analytics/dashboard")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["total"], 10)

    def test_topics(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            ga.return_value.get_topic_distribution.return_value = {"a": 3}
            r = self.client.get("/api/conversation-analytics/topics")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json(), {"a": 3})

    def test_hourly(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            ga.return_value.get_hourly_distribution.return_value = {"9": 5}
            r = self.client.get("/api/conversation-analytics/hourly")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json(), {"9": 5})

    def test_agents(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            ga.return_value.get_agent_usage.return_value = {"planner": 2}
            r = self.client.get("/api/conversation-analytics/agents")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json(), {"planner": 2})

    def test_satisfaction(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            ga.return_value.get_satisfaction_trend.return_value = [4.5]
            r = self.client.get("/api/conversation-analytics/satisfaction")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json(), [4.5])

    def test_quality(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            ga.return_value.get_quality_metrics.return_value = {"score": 0.9}
            r = self.client.get("/api/conversation-analytics/quality")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["score"], 0.9)

    def test_start_session_success(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            sess = MagicMock()
            sess.session_id = "s1"
            ga.return_value.start_session.return_value = sess
            r = self.client.post("/api/conversation-analytics/session/start", json={"session_id": "s1"})
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["session_id"], "s1")
            self.assertEqual(body["status"], "started")
            ga.return_value.start_session.assert_called_once_with("s1")

    def test_start_session_missing_id_400(self):
        r = self.client.post("/api/conversation-analytics/session/start", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_start_session_no_body_400(self):
        r = self.client.post("/api/conversation-analytics/session/start")
        self.assertEqual(r.status_code, 400)

    def test_start_session_empty_id_400(self):
        r = self.client.post("/api/conversation-analytics/session/start", json={"session_id": ""})
        self.assertEqual(r.status_code, 400)

    def test_add_turn_success(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            r = self.client.post("/api/conversation-analytics/session/turn", json={
                "session_id": "s1", "role": "assistant", "content": "hi",
                "agent": "planner", "latency_ms": 120, "tokens": 50,
            })
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["status"], "added")
            ga.return_value.add_turn.assert_called_once_with("s1", "assistant", "hi", "planner", 120, 50)

    def test_add_turn_defaults(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            r = self.client.post("/api/conversation-analytics/session/turn", json={"session_id": "s1"})
            self.assertEqual(r.status_code, 200)
            ga.return_value.add_turn.assert_called_once_with("s1", "user", "", None, 0, 0)

    def test_add_turn_missing_session_400(self):
        r = self.client.post("/api/conversation-analytics/session/turn", json={"role": "user"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_turn_no_body_400(self):
        r = self.client.post("/api/conversation-analytics/session/turn")
        self.assertEqual(r.status_code, 400)

    def test_end_session_success(self):
        with patch("orbit.core.conversation_analytics_bp.get_analytics") as ga:
            r = self.client.post("/api/conversation-analytics/session/end", json={"session_id": "s1"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["status"], "ended")
            ga.return_value.end_session.assert_called_once_with("s1")

    def test_end_session_missing_id_400(self):
        r = self.client.post("/api/conversation-analytics/session/end", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_end_session_no_body_400(self):
        r = self.client.post("/api/conversation-analytics/session/end")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
