"""Unit tests for orbit/orbit/core/agent_debate_bp.py."""

import os
import sys
import unittest
from dataclasses import dataclass
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.agent_debate_bp import agent_debate_bp


@dataclass
class FakeResult:
    verdict: str = "v"


class TestAgentDebateBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(agent_debate_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(agent_debate_bp.name, "agent_debate")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/debate/run", "/api/debate/history", "/api/debate/stats", "/api/debate/agents"]:
            self.assertIn(p, rules)

    def test_run_missing_question_400(self):
        r = self.client.post("/api/debate/run", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_run_success(self):
        with patch("orbit.core.agent_debate_bp.get_debate") as gd:
            gd.return_value.debate.return_value = FakeResult("v")
            r = self.client.post("/api/debate/run", json={"question": "q", "positions": ["a"], "context": "c"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["verdict"], "v")
        gd.return_value.debate.assert_called_once_with("q", positions=["a"], context="c")

    def test_run_no_body(self):
        r = self.client.post("/api/debate/run")
        self.assertEqual(r.status_code, 400)

    def test_history(self):
        with patch("orbit.core.agent_debate_bp.get_debate") as gd:
            gd.return_value.get_history.return_value = [{"d": 1}]
            r = self.client.get("/api/debate/history")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["debates"], [{"d": 1}])

    def test_stats(self):
        with patch("orbit.core.agent_debate_bp.get_debate_stats", return_value={"total": 2}):
            r = self.client.get("/api/debate/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 2)

    def test_agents(self):
        with patch("orbit.core.agent_debate_bp.get_debate") as gd:
            gd.return_value._agents = {"a": {"name": "AgentA"}, "b": {"name": "AgentB"}}
            gd.return_value._judge = object()
            r = self.client.get("/api/debate/agents")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["agents"], [{"id": "a", "name": "AgentA"}, {"id": "b", "name": "AgentB"}])
        self.assertTrue(body["has_judge"])

    def test_agents_no_judge(self):
        with patch("orbit.core.agent_debate_bp.get_debate") as gd:
            gd.return_value._agents = {}
            gd.return_value._judge = None
            r = self.client.get("/api/debate/agents")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["has_judge"])


if __name__ == "__main__":
    unittest.main()
