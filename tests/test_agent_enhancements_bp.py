"""Unit tests for orbit/orbit/core/agent_enhancements_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.agent_enhancements_bp import agent_enhancements_bp


def _dream(id="d1", summary="s", topics=("a",)):
    d = MagicMock()
    d.id = id
    d.summary = summary
    d.topics = list(topics)
    return d


def _gate_result(allowed=True, gate="security", reason="ok",
                 severity="low", suggestions=None):
    r = MagicMock()
    r.allowed = allowed
    r.gate_name = gate
    r.reason = reason
    r.severity = severity
    r.suggestions = suggestions or ["use quotes"]
    return r


def _score(rid="r1"):
    s = MagicMock()
    s.response_id = rid
    s.overall_score = 0.9
    s.relevance_score = 0.95
    s.coherence_score = 0.9
    s.safety_score = 1.0
    s.effort_score = 0.8
    s.hallucination_risk = "low"
    s.flags = []
    return s


class EnhBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(agent_enhancements_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(agent_enhancements_bp.name, "agent_enhancements_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/enhancements/dream/stats",
                  "/api/enhancements/dream/consolidate",
                  "/api/enhancements/gate/stats",
                  "/api/enhancements/gate/validate",
                  "/api/enhancements/evolution/stats",
                  "/api/enhancements/evolution/strategy/<agent_id>",
                  "/api/enhancements/evolution/history",
                  "/api/enhancements/observer/stats",
                  "/api/enhancements/observer/audit",
                  "/api/enhancements/dashboard"]:
            self.assertIn(p, rules)


class TestDream(EnhBpBase):
    def test_stats(self):
        with patch("orbit.core.agent_enhancements.get_dream_consolidator") as gd:
            gd.return_value.get_stats.return_value = {"dreams": 4}
            r = self.client.get("/api/enhancements/dream/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"dreams": 4})

    def test_consolidate(self):
        mem = [_dream("d1", "first", ("py",)), _dream("d2", "second")]
        with patch("orbit.core.agent_enhancements.get_dream_consolidator") as gd, \
             patch("orbit.memory.get_all", return_value=mem):
            gd.return_value.consolidate.return_value = [_dream()]
            r = self.client.post("/api/enhancements/dream/consolidate")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["new_dreams"], 1)
        self.assertEqual(body["total_entries_processed"], 2)
        self.assertEqual(body["dreams"],
                         [{"id": "d1", "summary": "s", "topics": ["a"]}])
        gd.return_value.consolidate.assert_called_once_with(mem)

    def test_consolidate_no_new_dreams(self):
        with patch("orbit.core.agent_enhancements.get_dream_consolidator") as gd, \
             patch("orbit.memory.get_all", return_value=[]):
            gd.return_value.consolidate.return_value = []
            r = self.client.post("/api/enhancements/dream/consolidate")
        body = r.get_json()
        self.assertEqual(body["new_dreams"], 0)
        self.assertEqual(body["dreams"], [])


class TestGate(EnhBpBase):
    def test_stats(self):
        with patch("orbit.core.agent_enhancements.get_gatekeeper") as gg:
            gg.return_value.get_stats.return_value = {"blocked": 2}
            r = self.client.get("/api/enhancements/gate/stats")
        self.assertEqual(r.get_json(), {"blocked": 2})

    def test_validate_success(self):
        with patch("orbit.core.agent_enhancements.get_gatekeeper") as gg:
            gg.return_value.validate_tool_call.return_value = _gate_result()
            r = self.client.post("/api/enhancements/gate/validate",
                                 json={"tool": "shell", "command": "ls",
                                       "agent_id": "a1"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["allowed"])
        self.assertEqual(body["gate_name"], "security")
        self.assertEqual(body["reason"], "ok")
        self.assertEqual(body["severity"], "low")
        self.assertEqual(body["suggestions"], ["use quotes"])
        gg.return_value.validate_tool_call.assert_called_once_with(
            "shell", "ls", "a1")

    def test_validate_defaults(self):
        with patch("orbit.core.agent_enhancements.get_gatekeeper") as gg:
            gg.return_value.validate_tool_call.return_value = _gate_result(
                allowed=False, severity="high")
            r = self.client.post("/api/enhancements/gate/validate",
                                 json={"tool": "t", "command": "c"})
        self.assertFalse(r.get_json()["allowed"])
        gg.return_value.validate_tool_call.assert_called_once_with(
            "t", "c", "")

    def test_validate_missing_tool_400(self):
        with patch("orbit.core.agent_enhancements.get_gatekeeper") as gg:
            r = self.client.post("/api/enhancements/gate/validate",
                                 json={"command": "c"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("tool and command required", r.get_json()["error"])
        gg.return_value.validate_tool_call.assert_not_called()

    def test_validate_missing_command_400(self):
        r = self.client.post("/api/enhancements/gate/validate",
                             json={"tool": "t"})
        self.assertEqual(r.status_code, 400)

    def test_validate_no_body_400(self):
        r = self.client.post("/api/enhancements/gate/validate")
        self.assertEqual(r.status_code, 400)


class TestEvolution(EnhBpBase):
    def test_stats(self):
        with patch("orbit.core.agent_enhancements.get_self_evolution") as ge:
            ge.return_value.get_all_metrics.return_value = {"agents": 3}
            r = self.client.get("/api/enhancements/evolution/stats")
        self.assertEqual(r.get_json(), {"agents": 3})

    def test_strategy(self):
        with patch("orbit.core.agent_enhancements.get_self_evolution") as ge:
            ge.return_value.get_strategy.return_value = {"mode": "explore"}
            r = self.client.get("/api/enhancements/evolution/strategy/planner")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"agent_id": "planner", "strategy": {"mode": "explore"}})
        ge.return_value.get_strategy.assert_called_once_with("planner")

    def test_strategy_none(self):
        with patch("orbit.core.agent_enhancements.get_self_evolution") as ge:
            ge.return_value.get_strategy.return_value = None
            r = self.client.get("/api/enhancements/evolution/strategy/nope")
        self.assertEqual(r.get_json()["strategy"], None)

    def test_history_with_agent(self):
        with patch("orbit.core.agent_enhancements.get_self_evolution") as ge:
            ge.return_value.get_strategy_history.return_value = [{"t": 1}]
            r = self.client.get("/api/enhancements/evolution/history?agent_id=a1")
        ge.return_value.get_strategy_history.assert_called_once_with("a1")

    def test_history_no_agent(self):
        with patch("orbit.core.agent_enhancements.get_self_evolution") as ge:
            ge.return_value.get_strategy_history.return_value = []
            r = self.client.get("/api/enhancements/evolution/history")
        ge.return_value.get_strategy_history.assert_called_once_with(None)


class TestObserver(EnhBpBase):
    def test_stats(self):
        with patch("orbit.core.agent_enhancements.get_observer_audit") as go:
            go.return_value.get_stats.return_value = {"audited": 10}
            r = self.client.get("/api/enhancements/observer/stats")
        self.assertEqual(r.get_json(), {"audited": 10})

    def test_audit_success(self):
        with patch("orbit.core.agent_enhancements.get_observer_audit") as go:
            go.return_value.audit_response.return_value = _score()
            r = self.client.post("/api/enhancements/observer/audit",
                                 json={"query": "q", "response": "r",
                                       "agent_id": "a1"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["response_id"], "r1")
        self.assertEqual(body["overall_score"], 0.9)
        self.assertEqual(body["relevance_score"], 0.95)
        self.assertEqual(body["coherence_score"], 0.9)
        self.assertEqual(body["safety_score"], 1.0)
        self.assertEqual(body["effort_score"], 0.8)
        self.assertEqual(body["hallucination_risk"], "low")
        self.assertEqual(body["flags"], [])
        go.return_value.audit_response.assert_called_once_with("q", "r", "a1")

    def test_audit_defaults(self):
        with patch("orbit.core.agent_enhancements.get_observer_audit") as go:
            go.return_value.audit_response.return_value = _score()
            r = self.client.post("/api/enhancements/observer/audit",
                                 json={"query": "q", "response": "r"})
        go.return_value.audit_response.assert_called_once_with("q", "r", "")

    def test_audit_missing_query_400(self):
        with patch("orbit.core.agent_enhancements.get_observer_audit") as go:
            r = self.client.post("/api/enhancements/observer/audit",
                                 json={"response": "r"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("query and response required", r.get_json()["error"])
        go.return_value.audit_response.assert_not_called()

    def test_audit_missing_response_400(self):
        r = self.client.post("/api/enhancements/observer/audit",
                             json={"query": "q"})
        self.assertEqual(r.status_code, 400)

    def test_audit_no_body_400(self):
        r = self.client.post("/api/enhancements/observer/audit")
        self.assertEqual(r.status_code, 400)


class TestDashboard(EnhBpBase):
    def test_dashboard(self):
        with patch("orbit.core.agent_enhancements.get_dream_consolidator") as gd, \
             patch("orbit.core.agent_enhancements.get_gatekeeper") as gg, \
             patch("orbit.core.agent_enhancements.get_self_evolution") as ge, \
             patch("orbit.core.agent_enhancements.get_observer_audit") as go:
            gd.return_value.get_stats.return_value = {"dreams": 1}
            gg.return_value.get_stats.return_value = {"blocked": 2}
            ge.return_value.get_all_metrics.return_value = {"agents": 3}
            go.return_value.get_stats.return_value = {"audited": 4}
            r = self.client.get("/api/enhancements/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {
            "dreams": {"dreams": 1},
            "gatekeeper": {"blocked": 2},
            "evolution": {"agents": 3},
            "observer": {"audited": 4},
        })


if __name__ == "__main__":
    unittest.main()
