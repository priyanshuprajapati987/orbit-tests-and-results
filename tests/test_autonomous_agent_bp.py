"""Unit tests for orbit/orbit/core/autonomous_agent_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.autonomous_agent_bp import (
    autonomous_agent_bp, _request_user_id,
)

P = "orbit.core.autonomous_agent_bp."


def _fake_users_db(count=1):
    """Patch guard's user-table probe: Session().query(User).count()."""
    return patch("orbit.core.auth.store.get_session_factory",
                 return_value=MagicMock(
                     return_value=MagicMock(
                         __enter__=MagicMock(return_value=MagicMock(
                             query=MagicMock(return_value=MagicMock(
                                 count=MagicMock(return_value=count))))),
                         __exit__=MagicMock(return_value=False))))


class AutoBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(autonomous_agent_bp)
        self.client = self.app.test_client()
        self.ks = MagicMock()
        self.tm = MagicMock()
        self.audit = MagicMock()
        self.mm = MagicMock()

    def _patch_all(self):
        return (
            patch(P + "get_kill_switch", return_value=self.ks),
            patch(P + "get_trust_manager", return_value=self.tm),
            patch(P + "get_llm_audit", return_value=self.audit),
            patch(P + "get_model_monitor", return_value=self.mm),
        )

    def _enter(self, *extra):
        stack = []
        for p in self._patch_all() + extra:
            stack.append(p.start())
            self.addCleanup(p.stop)
        return stack

    def test_blueprint_name(self):
        self.assertEqual(autonomous_agent_bp.name, "autonomous_agent")
        self.assertEqual(autonomous_agent_bp.url_prefix, "/api/autonomous")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/autonomous/kill-switch/status",
                  "/api/autonomous/kill-switch/activate",
                  "/api/autonomous/kill-switch/deactivate",
                  "/api/autonomous/dry-run/enable",
                  "/api/autonomous/dry-run/disable",
                  "/api/autonomous/dry-run/summary",
                  "/api/autonomous/trust/status",
                  "/api/autonomous/trust/check",
                  "/api/autonomous/trust/usage/<agent_id>",
                  "/api/autonomous/trust/config",
                  "/api/autonomous/audit/stats",
                  "/api/autonomous/audit/recent",
                  "/api/autonomous/audit/cost-by-agent",
                  "/api/autonomous/audit/cost-by-provider",
                  "/api/autonomous/models/status",
                  "/api/autonomous/models/scan",
                  "/api/autonomous/models/releases"]:
            self.assertIn(p, rules)


class TestKillSwitch(AutoBpBase):
    def test_status(self):
        self._enter()
        self.ks.status.return_value = {"active": True}
        r = self.client.get("/api/autonomous/kill-switch/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"active": True})

    def test_status_exception_500(self):
        with patch(P + "get_kill_switch", side_effect=RuntimeError("ks")):
            r = self.client.get("/api/autonomous/kill-switch/status")
        self.assertEqual(r.status_code, 500)
        self.assertIn("ks", r.get_json()["error"])

    def test_activate_defaults(self):
        self._enter()
        self.ks.activate.return_value = {"ok": True}
        r = self.client.post("/api/autonomous/kill-switch/activate")
        self.assertEqual(r.status_code, 200)
        self.ks.activate.assert_called_once_with(
            by="api", reason="manual activation")

    def test_activate_custom_fields(self):
        self._enter()
        self.ks.activate.return_value = {"ok": True}
        r = self.client.post("/api/autonomous/kill-switch/activate",
                             json={"by": "victus", "reason": "drill"})
        self.ks.activate.assert_called_once_with(
            by="victus", reason="drill")

    def test_activate_exception_500(self):
        self._enter()
        self.ks.activate.side_effect = RuntimeError("nope")
        r = self.client.post("/api/autonomous/kill-switch/activate")
        self.assertEqual(r.status_code, 500)
        self.assertIn("nope", r.get_json()["error"])

    def test_activate_401_when_anon_with_users(self):
        self._enter()
        with _fake_users_db(1), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "", "role": ""}):
            r = self.client.post("/api/autonomous/kill-switch/activate")
        self.assertEqual(r.status_code, 401)
        self.ks.activate.assert_not_called()

    def test_activate_403_when_non_admin(self):
        self._enter()
        with _fake_users_db(1), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "u1", "role": "user"}):
            r = self.client.post("/api/autonomous/kill-switch/activate")
        self.assertEqual(r.status_code, 403)
        self.ks.activate.assert_not_called()

    def test_activate_admin_allowed(self):
        self._enter()
        self.ks.activate.return_value = {"ok": True}
        with _fake_users_db(1), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "u1", "role": "admin"}):
            r = self.client.post("/api/autonomous/kill-switch/activate")
        self.assertEqual(r.status_code, 200)
        self.ks.activate.assert_called_once()

    def test_deactivate_defaults(self):
        self._enter()
        self.ks.deactivate.return_value = {"ok": False}
        r = self.client.post("/api/autonomous/kill-switch/deactivate")
        self.assertEqual(r.status_code, 200)
        self.ks.deactivate.assert_called_once_with(by="api")

    def test_deactivate_custom_by(self):
        self._enter()
        self.ks.deactivate.return_value = {"ok": False}
        self.client.post("/api/autonomous/kill-switch/deactivate",
                         json={"by": "admin"})
        self.ks.deactivate.assert_called_once_with(by="admin")

    def test_deactivate_exception_500(self):
        self._enter()
        self.ks.deactivate.side_effect = RuntimeError("d fail")
        r = self.client.post("/api/autonomous/kill-switch/deactivate")
        self.assertEqual(r.status_code, 500)


class TestDryRun(AutoBpBase):
    def test_enable(self):
        self._enter()
        self.ks.enable_dry_run.return_value = {"dry_run": True}
        r = self.client.post("/api/autonomous/dry-run/enable")
        self.assertEqual(r.get_json(), {"dry_run": True})

    def test_enable_exception_500(self):
        with patch(P + "get_kill_switch", side_effect=RuntimeError("e")):
            r = self.client.post("/api/autonomous/dry-run/enable")
        self.assertEqual(r.status_code, 500)

    def test_disable(self):
        self._enter()
        self.ks.disable_dry_run.return_value = {"dry_run": False}
        r = self.client.post("/api/autonomous/dry-run/disable")
        self.assertEqual(r.get_json(), {"dry_run": False})

    def test_disable_exception_500(self):
        self._enter()
        self.ks.disable_dry_run.side_effect = RuntimeError("d")
        r = self.client.post("/api/autonomous/dry-run/disable")
        self.assertEqual(r.status_code, 500)

    def test_summary(self):
        self._enter()
        self.ks.get_dry_run_summary.return_value = {"actions": 7}
        r = self.client.get("/api/autonomous/dry-run/summary")
        self.assertEqual(r.get_json(), {"actions": 7})

    def test_summary_exception_500(self):
        self._enter()
        self.ks.get_dry_run_summary.side_effect = RuntimeError("s")
        r = self.client.get("/api/autonomous/dry-run/summary")
        self.assertEqual(r.status_code, 500)


class TestTrust(AutoBpBase):
    def test_status(self):
        self._enter()
        self.tm.get_all_usage.return_value = {"planner": 3}
        r = self.client.get("/api/autonomous/trust/status")
        self.assertEqual(r.get_json(), {"planner": 3})

    def test_status_exception_500(self):
        with patch(P + "get_trust_manager", side_effect=RuntimeError("t")):
            r = self.client.get("/api/autonomous/trust/status")
        self.assertEqual(r.status_code, 500)

    def test_check_defaults(self):
        self._enter()
        self.tm.can_act.return_value = {"allowed": True}
        r = self.client.post("/api/autonomous/trust/check", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"allowed": True})
        kwargs = self.tm.can_act.call_args.kwargs
        self.assertEqual(kwargs["user_id"], "local")  # fallback
        args = self.tm.can_act.call_args.args
        self.assertEqual(args, ("", 0.0, ""))

    def test_check_full_fields(self):
        self._enter()
        self.tm.can_act.return_value = {"allowed": False}
        r = self.client.post("/api/autonomous/trust/check", json={
            "agent_id": "planner", "cost_usd": 0.25,
            "tool": "shell", "user_id": "u9"})
        self.tm.can_act.assert_called_once_with(
            "planner", 0.25, "shell", user_id="u9")

    def test_check_fallback_user_id_patch(self):
        self._enter()
        with patch(P + "_request_user_id", return_value="fallback"):
            self.client.post("/api/autonomous/trust/check",
                             json={"agent_id": "a"})
        kwargs = self.tm.can_act.call_args.kwargs
        self.assertEqual(kwargs["user_id"], "fallback")

    def test_check_exception_500(self):
        self._enter()
        self.tm.can_act.side_effect = RuntimeError("tc")
        r = self.client.post("/api/autonomous/trust/check", json={})
        self.assertEqual(r.status_code, 500)

    def test_usage_with_user_id(self):
        self._enter()
        self.tm.get_usage.return_value = {"spent": 1.0}
        r = self.client.get("/api/autonomous/trust/usage/a1?user_id=u1")
        self.tm.get_usage.assert_called_once_with("a1", user_id="u1")
        self.assertEqual(r.get_json(), {"spent": 1.0})

    def test_usage_fallback_user_id(self):
        self._enter()
        self.tm.get_usage.return_value = {}
        self.client.get("/api/autonomous/trust/usage/a1")
        kwargs = self.tm.get_usage.call_args.kwargs
        self.assertEqual(kwargs["user_id"], "local")

    def test_usage_exception_500(self):
        with patch(P + "get_trust_manager", side_effect=RuntimeError("u")):
            r = self.client.get("/api/autonomous/trust/usage/a1")
        self.assertEqual(r.status_code, 500)

    def test_config_missing_agent_400(self):
        self._enter()
        r = self.client.post("/api/autonomous/trust/config",
                             json={"max_cost": 1})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "agent_id required")
        self.tm.update_config.assert_not_called()

    def test_config_success_strips_agent_id(self):
        self._enter()
        self.tm.update_config.return_value = {"ok": True}
        r = self.client.post("/api/autonomous/trust/config", json={
            "agent_id": "planner", "max_cost": 5, "cooldown": 10})
        self.assertEqual(r.status_code, 200)
        self.tm.update_config.assert_called_once_with(
            "planner", max_cost=5, cooldown=10)

    def test_config_result_error_400(self):
        self._enter()
        self.tm.update_config.return_value = {"error": "unknown agent"}
        r = self.client.post("/api/autonomous/trust/config",
                             json={"agent_id": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "unknown agent")

    def test_config_exception_500(self):
        self._enter()
        self.tm.update_config.side_effect = RuntimeError("cf")
        r = self.client.post("/api/autonomous/trust/config",
                             json={"agent_id": "a"})
        self.assertEqual(r.status_code, 500)

    def test_config_admin_401(self):
        self._enter()
        with _fake_users_db(1), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "", "role": ""}):
            r = self.client.post("/api/autonomous/trust/config",
                                 json={"agent_id": "a"})
        self.assertEqual(r.status_code, 401)
        self.tm.update_config.assert_not_called()


class TestAudit(AutoBpBase):
    def test_stats(self):
        self._enter()
        self.audit.get_stats.return_value = {"calls": 12}
        r = self.client.get("/api/autonomous/audit/stats")
        self.assertEqual(r.get_json(), {"calls": 12})

    def test_stats_exception_500(self):
        with patch(P + "get_llm_audit", side_effect=RuntimeError("a")):
            r = self.client.get("/api/autonomous/audit/stats")
        self.assertEqual(r.status_code, 500)

    def test_recent_default_limit(self):
        self._enter()
        self.audit.get_recent.return_value = []
        r = self.client.get("/api/autonomous/audit/recent")
        self.audit.get_recent.assert_called_once_with(50)

    def test_recent_custom_limit(self):
        self._enter()
        self.audit.get_recent.return_value = []
        self.client.get("/api/autonomous/audit/recent?limit=5")
        self.audit.get_recent.assert_called_once_with(5)

    def test_recent_bad_limit_defaults_50(self):
        self._enter()
        self.audit.get_recent.return_value = []
        self.client.get("/api/autonomous/audit/recent?limit=abc")
        self.audit.get_recent.assert_called_once_with(50)

    def test_recent_exception_500(self):
        self._enter()
        self.audit.get_recent.side_effect = RuntimeError("r")
        r = self.client.get("/api/autonomous/audit/recent")
        self.assertEqual(r.status_code, 500)

    def test_cost_by_agent(self):
        self._enter()
        self.audit.get_cost_by_agent.return_value = {"planner": 0.5}
        r = self.client.get("/api/autonomous/audit/cost-by-agent")
        self.assertEqual(r.get_json(), {"planner": 0.5})

    def test_cost_by_agent_exception_500(self):
        self._enter()
        self.audit.get_cost_by_agent.side_effect = RuntimeError("c")
        r = self.client.get("/api/autonomous/audit/cost-by-agent")
        self.assertEqual(r.status_code, 500)

    def test_cost_by_provider(self):
        self._enter()
        self.audit.get_cost_by_provider.return_value = {"ollama": 0.1}
        r = self.client.get("/api/autonomous/audit/cost-by-provider")
        self.assertEqual(r.get_json(), {"ollama": 0.1})

    def test_cost_by_provider_exception_500(self):
        self._enter()
        self.audit.get_cost_by_provider.side_effect = RuntimeError("p")
        r = self.client.get("/api/autonomous/audit/cost-by-provider")
        self.assertEqual(r.status_code, 500)


class TestModelMonitor(AutoBpBase):
    def test_status(self):
        self._enter()
        self.mm.get_status.return_value = {"models": 4}
        r = self.client.get("/api/autonomous/models/status")
        self.assertEqual(r.get_json(), {"models": 4})

    def test_status_exception_500(self):
        with patch(P + "get_model_monitor", side_effect=RuntimeError("m")):
            r = self.client.get("/api/autonomous/models/status")
        self.assertEqual(r.status_code, 500)

    def test_scan(self):
        self._enter()
        self.mm.run_full_scan.return_value = {"scanned": 9}
        r = self.client.post("/api/autonomous/models/scan")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"scanned": 9})

    def test_scan_exception_500(self):
        self._enter()
        self.mm.run_full_scan.side_effect = RuntimeError("scan fail")
        r = self.client.post("/api/autonomous/models/scan")
        self.assertEqual(r.status_code, 500)
        self.assertIn("scan fail", r.get_json()["error"])

    def test_releases_default_limit(self):
        self._enter()
        self.mm.get_releases.return_value = []
        self.client.get("/api/autonomous/models/releases")
        self.mm.get_releases.assert_called_once_with(50)

    def test_releases_custom_limit(self):
        self._enter()
        self.mm.get_releases.return_value = [{"v": 1}]
        r = self.client.get("/api/autonomous/models/releases?limit=2")
        self.mm.get_releases.assert_called_once_with(2)
        self.assertEqual(r.get_json(), [{"v": 1}])

    def test_releases_exception_500(self):
        self._enter()
        self.mm.get_releases.side_effect = RuntimeError("rel")
        r = self.client.get("/api/autonomous/models/releases")
        self.assertEqual(r.status_code, 500)


class TestRequestId(AutoBpBase):
    def test_default_local(self):
        with self.app.test_request_context("/"):
            self.assertEqual(_request_user_id(), "local")

    def test_from_current_user(self):
        with self.app.test_request_context("/"), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "u1", "role": "user"}):
            self.assertEqual(_request_user_id(), "u1")

    def test_empty_id_becomes_local(self):
        with self.app.test_request_context("/"), \
             patch("orbit.core.auth.guards.current_user",
                   return_value={"id": "", "role": ""}):
            self.assertEqual(_request_user_id(), "local")

    def test_exception_falls_back_local(self):
        with self.app.test_request_context("/"), \
             patch("orbit.core.auth.guards.current_user",
                   side_effect=RuntimeError("no user")):
            self.assertEqual(_request_user_id(), "local")


if __name__ == "__main__":
    unittest.main()
