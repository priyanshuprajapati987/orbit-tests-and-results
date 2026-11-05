"""Tests for autonomous agent safety systems: kill switch, dry-run, trust, audit, model monitor."""

from unittest.mock import patch

import pytest

from orbit.orbit.core.kill_switch import (
    AgentTrustConfig,
    AgentTrustManager,
    KillSwitch,
    TrustLevel,
    _reset_singletons_for_tests,
)


class TestKillSwitch:
    @pytest.fixture(autouse=True)
    def _reset(self):
        ks = KillSwitch()
        ks._active = False
        ks._dry_run = False
        ks._dry_run_log.clear()
        ks._activated_at = None
        ks._activated_by = ""
        ks._reason = ""
        yield

    def test_activate_deactivate(self):
        ks = KillSwitch()
        r = ks.activate(by="test", reason="unit test")
        assert r["active"] is True
        assert ks.is_active() is True
        r = ks.deactivate(by="test")
        assert r["active"] is False
        assert ks.is_active() is False

    def test_status_shape(self):
        ks = KillSwitch()
        s = ks.status()
        assert "active" in s
        assert "dry_run" in s

    def test_dry_run_enable_disable(self):
        ks = KillSwitch()
        ks.enable_dry_run()
        assert ks.is_dry_run() is True
        ks.disable_dry_run()
        assert ks.is_dry_run() is False

    def test_dry_run_log(self):
        ks = KillSwitch()
        ks.enable_dry_run()
        ks.log_dry_run("test.action", details="testing", cost_usd=0.05)
        log = ks.get_dry_run_log()
        assert len(log) == 1
        assert log[0]["action"] == "test.action"
        assert log[0]["cost_usd"] == 0.05

    def test_dry_run_summary(self):
        ks = KillSwitch()
        ks.enable_dry_run()
        ks.log_dry_run("a", cost_usd=0.1)
        ks.log_dry_run("b", cost_usd=0.2)
        s = ks.get_dry_run_summary()
        assert s["pending_actions"] == 2
        assert abs(s["total_estimated_cost_usd"] - 0.3) < 0.01


class TestAgentTrust:
    @pytest.fixture(autouse=True)
    def _reset(self):
        _reset_singletons_for_tests()
        # Ensure kill switch is off for trust tests
        ks = KillSwitch()
        ks._active = False
        ks._dry_run = False
        ks._save()
        yield

    def test_known_agent_allowed(self):
        tm = AgentTrustManager()
        r = tm.can_act("TAS", cost_usd=0.0)
        assert r["allowed"] is True

    def test_unknown_agent_blocked(self):
        tm = AgentTrustManager()
        r = tm.can_act("UNKNOWN_AGENT")
        assert r["allowed"] is False
        assert r["reason"] == "unknown_agent"

    def test_budget_exceeded(self):
        tm = AgentTrustManager()
        tm._configs["TEST"] = AgentTrustConfig(
            agent_id="TEST",
            trust_level=TrustLevel.MEDIUM,
            daily_budget_usd=1.0,
            max_api_calls_per_day=100,
        )
        tm.record_usage("TEST", cost_usd=0.9)
        r = tm.can_act("TEST", cost_usd=0.2)
        assert r["allowed"] is False
        assert r["reason"] == "daily_budget_exceeded"

    def test_call_limit(self):
        tm = AgentTrustManager()
        tm._configs["TEST"] = AgentTrustConfig(
            agent_id="TEST",
            trust_level=TrustLevel.MEDIUM,
            daily_budget_usd=100.0,
            max_api_calls_per_day=3,
        )
        for _ in range(3):
            tm.record_usage("TEST")
        r = tm.can_act("TEST")
        assert r["allowed"] is False
        assert r["reason"] == "daily_call_limit_reached"

    def test_tool_blocked(self):
        tm = AgentTrustManager()
        tm._configs["TEST"] = AgentTrustConfig(
            agent_id="TEST",
            trust_level=TrustLevel.MEDIUM,
            blocked_tools=["system.command"],
        )
        r = tm.can_act("TEST", tool="system.command")
        assert r["allowed"] is False
        assert r["reason"] == "tool_blocked"

    def test_usage_tracking(self):
        tm = AgentTrustManager()
        tm.record_usage("TAS", cost_usd=0.5)
        u = tm.get_usage("TAS")
        assert u["daily_cost"] == 0.5
        assert u["daily_calls"] == 1

    def test_kill_switch_blocks_all(self):
        ks = KillSwitch()
        ks.activate(by="test", reason="test")
        tm = AgentTrustManager()
        r = tm.can_act("QUEEN", cost_usd=0.0)
        assert r["allowed"] is False
        assert r["reason"] == "kill_switch_active"
        ks.deactivate()

    def test_dry_run_logs_not_blocks(self):
        ks = KillSwitch()
        ks.enable_dry_run()
        tm = AgentTrustManager()
        r = tm.can_act("TAS", cost_usd=0.5, tool="file.write")
        assert r["allowed"] is True
        assert r.get("dry_run") is True
        ks.disable_dry_run()


class TestPolicyEngineKillSwitch:
    def test_kill_switch_blocks_check(self):
        from orbit.orbit.core.policy_engine import get_policy_engine

        real_ks = KillSwitch()
        real_ks._active = False
        real_ks._dry_run = False
        with patch(
            "orbit.orbit.core.kill_switch.get_kill_switch", return_value=real_ks
        ):
            real_ks.activate(by="test", reason="test block")
            try:
                pe = get_policy_engine()
                d = pe.check("system", "command")
                assert d.allowed is False
                assert "kill_switch" in d.reason
            finally:
                real_ks.deactivate()

    def test_dry_run_allows_with_log(self):
        from orbit.orbit.core.policy_engine import get_policy_engine

        real_ks = KillSwitch()
        real_ks._active = False
        real_ks._dry_run = False
        with patch(
            "orbit.orbit.core.kill_switch.get_kill_switch", return_value=real_ks
        ):
            real_ks.enable_dry_run()
            try:
                pe = get_policy_engine()
                d = pe.check("system", "command")
                assert d.allowed is True  # dry run logs but allows
                log = real_ks.get_dry_run_log()
                assert any("system.command" in e["action"] for e in log)
            finally:
                real_ks.disable_dry_run()


class TestLLMAuditLogger:
    def test_log_and_stats(self):
        from orbit.orbit.core.llm_audit import get_llm_audit

        audit = get_llm_audit()
        before = audit._total_calls_today
        aid = audit.log(
            provider="test_provider",
            model="test_model",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            latency_ms=200,
            success=True,
            agent_id="TAS",
        )
        assert aid
        assert audit._total_calls_today == before + 1

    def test_recent_entries(self):
        from orbit.orbit.core.llm_audit import get_llm_audit

        audit = get_llm_audit()
        audit.log(provider="x", model="y", cost_usd=0.0)
        recent = audit.get_recent(limit=5)
        assert isinstance(recent, list)

    def test_cost_by_agent(self):
        from orbit.orbit.core.llm_audit import get_llm_audit

        audit = get_llm_audit()
        audit.log(provider="x", model="y", cost_usd=0.1, agent_id="TEST_AGENT")
        costs = audit.get_cost_by_agent()
        assert isinstance(costs, dict)


class TestModelMonitor:
    def test_status(self):
        from orbit.orbit.core.model_monitor import get_model_monitor

        mon = get_model_monitor()
        s = mon.get_status()
        assert "total_known_models" in s
        assert "needs_scan" in s

    def test_releases_list(self):
        from orbit.orbit.core.model_monitor import get_model_monitor

        mon = get_model_monitor()
        r = mon.get_releases(limit=10)
        assert isinstance(r, list)
