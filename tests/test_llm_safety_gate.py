"""Safety-gate enforcement on the LLM path (kill switch + agent trust).

Regression cover for the review P0/P1 gap: ``can_act()`` was never called
before generation — PolicyEngine only gated TOOLS, so an active kill switch
or an exhausted per-day call budget still let every model call through,
including via the legacy fallback (``_legacy_generate``) in legacy_adapter.

All tests are hermetic: the gate returns before any provider is contacted,
and generation-after-gate tests mock ``_generate_with_failover``.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from orbit.orbit.core import kill_switch as ks
from orbit.orbit.core.llm import legacy_adapter
from orbit.orbit.core.llm.router import LLMRequest, LLMResponse, get_router


@pytest.fixture(autouse=True)
def fresh_safety(tmp_path):
    """Fresh singletons with tmp-dir persistence (never touches the real
    orbit_data/security/kill_switch.json or agent_trust.json)."""
    ks._reset_singletons_for_tests()
    switch = ks.KillSwitch()
    switch._persist_file = tmp_path / "kill_switch.json"
    switch.deactivate(by="test")
    switch.disable_dry_run()
    tm = ks.AgentTrustManager()
    tm._persist_file = tmp_path / "agent_trust.json"
    yield ks
    ks._reset_singletons_for_tests()


def _canned_router_response():
    return LLMResponse(
        content="canned-ok",
        provider="test",
        model="test-model",
        latency_ms=1,
        success=True,
    )


def _generate(prompt=None, **kw):
    req = LLMRequest(prompt=prompt or f"unique-{uuid.uuid4()}", **kw)
    return asyncio.run(get_router().generate(req))


def _patch_failover(monkeypatch, response=None):
    monkeypatch.setattr(
        get_router(),
        "_generate_with_failover",
        AsyncMock(return_value=response or _canned_router_response()),
    )


class TestKillSwitchGate:
    def test_kill_switch_blocks_router_generate(self, fresh_safety):
        fresh_safety.KillSwitch().activate(by="test", reason="unit")
        resp = _generate("this must never reach a provider")
        assert resp.success is False
        assert resp.provider == "none"
        assert "kill_switch_active" in (resp.error or "")
        assert resp.content.startswith("[Error: LLM call blocked")

    def test_dry_run_allows_and_logs(self, fresh_safety, monkeypatch):
        # can_act contract: dry-run (switch NOT active) = observe, don't block
        sw = fresh_safety.KillSwitch()
        sw.enable_dry_run()
        _patch_failover(monkeypatch)
        resp = _generate()
        assert resp.success is True
        assert resp.content == "canned-ok"
        assert len(sw.get_dry_run_log()) >= 1

    def test_active_switch_wins_over_dry_run(self, fresh_safety):
        # hard block must not be softened by dry-run mode
        sw = fresh_safety.KillSwitch()
        sw.activate(by="test", reason="unit")
        sw.enable_dry_run()
        resp = _generate()
        assert resp.success is False
        assert "kill_switch_active" in (resp.error or "")

    def test_inactive_switch_allows_generation(self, fresh_safety, monkeypatch):
        _patch_failover(monkeypatch)
        resp = _generate()
        assert resp.success is True
        assert resp.content == "canned-ok"


class TestTrustGate:
    def test_router_has_default_trust_config(self, fresh_safety):
        tm = fresh_safety.AgentTrustManager()
        r = tm.can_act("ROUTER", cost_usd=0.0, tool="llm_generate")
        assert r.get("allowed") is True
        # unknown agents stay fail-closed
        r2 = tm.can_act("UNKNOWN_AGENT_XYZ")
        assert r2.get("allowed") is False
        assert r2.get("reason") == "unknown_agent"

    def test_call_limit_blocks_router_generate(self, fresh_safety, monkeypatch):
        tm = fresh_safety.AgentTrustManager()
        # in-memory only (no update_config -> no _save) so nothing persists
        tm._configs["ROUTER"].max_api_calls_per_day = 0
        _patch_failover(monkeypatch)
        resp = _generate()
        assert resp.success is False
        assert "daily_call_limit_reached" in (resp.error or "")

    def test_audit_usage_feeds_gate_counter(self, fresh_safety):
        tm = fresh_safety.AgentTrustManager()
        tm.record_usage("ROUTER", cost_usd=0.01)
        tm.record_usage("ROUTER", cost_usd=0.01)
        usage = tm.get_usage("ROUTER")
        assert usage.get("daily_calls", 0) >= 2
        assert usage.get("daily_cost", 0.0) >= 0.02

    def test_gate_fails_open_on_internal_error(self, fresh_safety, monkeypatch):
        def _boom():
            raise RuntimeError("trust manager exploded")

        monkeypatch.setattr(fresh_safety, "get_trust_manager", _boom)
        _patch_failover(monkeypatch)
        resp = _generate()  # must NOT brick chat
        assert resp.success is True
        assert resp.content == "canned-ok"


class TestLegacyFallbackGate:
    def test_blocked_call_never_reaches_legacy_fallback(self, fresh_safety):
        """The known bypass: router blocks (success=False) and the adapter
        would fall back to _legacy_generate — the gate at adapter entry must
        return the [Error ...] string directly instead."""
        fresh_safety.KillSwitch().activate(by="test", reason="unit")
        out = legacy_adapter.generate("hi there")
        assert isinstance(out, str)
        assert out.startswith("[Error: LLM call blocked")
        assert "kill_switch_active" in out

    def test_inactive_switch_passes_adapter_entry(self, fresh_safety, monkeypatch):
        _patch_failover(monkeypatch)
        out = legacy_adapter.generate(f"hello-{uuid.uuid4()}")
        assert out == "canned-ok"


def _fallback_audit_calls(audit):
    return sum(v["calls"] for k, v in audit._stats.items() if k.startswith("legacy-fallback/"))


class TestLegacyFallbackSafetyRecord:
    """CONTEXT "Legacy Fallback Safety Gap": when the modern router fails and
    the adapter falls back to ``_legacy_generate``, the call must still be
    audit-logged, trust usage recorded, and breaker-updated — record-only,
    never gating the fallback ("pipeline never blocked")."""

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path):
        from orbit.orbit.core import circuit_breaker as cb_mod
        from orbit.orbit.core.llm_audit import get_llm_audit

        audit = get_llm_audit()
        old_file, old_today = audit._audit_file, audit._today_file
        audit._audit_file = tmp_path / "llm_calls.jsonl"
        audit._today_file = tmp_path / "llm_today.jsonl"
        cb_mod.circuit_breakers.pop("legacy-fallback", None)
        yield
        audit._audit_file, audit._today_file = old_file, old_today
        cb_mod.circuit_breakers.pop("legacy-fallback", None)

    def _run_fallback(self, monkeypatch, legacy_result="legacy-ok"):
        """Modern router raises -> adapter falls back to the patched legacy
        router, exercising _legacy_generate's safety recording."""
        class _BoomRouter:
            async def generate(self, req):
                raise RuntimeError("modern down")

        monkeypatch.setattr(legacy_adapter, "get_router", lambda: _BoomRouter())
        import orbit.orbit.router as legacy_mod

        monkeypatch.setattr(legacy_mod, "generate", lambda *a, **k: legacy_result)
        return legacy_adapter.generate(f"fb-{uuid.uuid4()}")

    def test_fallback_success_recorded(self, fresh_safety, monkeypatch):
        from orbit.orbit.core import circuit_breaker as cb_mod
        from orbit.orbit.core.llm_audit import get_llm_audit

        audit = get_llm_audit()
        audit_before = _fallback_audit_calls(audit)
        tm = fresh_safety.AgentTrustManager()
        calls_before = tm.get_usage("ROUTER").get("daily_calls", 0)

        out = self._run_fallback(monkeypatch)

        assert out == "legacy-ok"
        # audit: provider="legacy-fallback" entry recorded
        assert _fallback_audit_calls(audit) == audit_before + 1
        # trust: the fallback CALL counted toward ROUTER's daily budget
        assert tm.get_usage("ROUTER").get("daily_calls", 0) == calls_before + 1
        # breaker: success recorded
        state = cb_mod.get_circuit_breaker("legacy-fallback").get_state()
        assert state["total_successes"] == 1
        assert state["total_failures"] == 0

    def test_fallback_failure_recorded(self, fresh_safety, monkeypatch):
        from orbit.orbit.core import circuit_breaker as cb_mod
        from orbit.orbit.core.llm_audit import get_llm_audit

        audit = get_llm_audit()
        audit_before = _fallback_audit_calls(audit)

        out = self._run_fallback(monkeypatch, legacy_result="[Error: legacy boom]")

        assert out == "[Error: legacy boom]"
        assert _fallback_audit_calls(audit) == audit_before + 1
        state = cb_mod.get_circuit_breaker("legacy-fallback").get_state()
        assert state["total_failures"] >= 1
        assert state["last_errors"], "failure must be visible in breaker status"

    def test_blocked_call_records_nothing(self, fresh_safety):
        """Kill-switch block returns at adapter entry — no fallback, no
        fallback audit/breaker traffic (the gate decides, not the recorder)."""
        from orbit.orbit.core import circuit_breaker as cb_mod
        from orbit.orbit.core.llm_audit import get_llm_audit

        audit = get_llm_audit()
        audit_before = _fallback_audit_calls(audit)
        fresh_safety.KillSwitch().activate(by="test", reason="unit")

        out = legacy_adapter.generate("blocked-hi")

        assert out.startswith("[Error: LLM call blocked")
        assert _fallback_audit_calls(audit) == audit_before
        assert cb_mod.get_circuit_breaker("legacy-fallback").get_state()["total_calls"] == 0

    def test_recording_failures_never_brick_fallback(self, fresh_safety, monkeypatch):
        """Each safety recorder is independently fail-open — a broken audit
        logger must not lose the legacy answer."""
        import orbit.orbit.core.llm_audit as audit_mod

        def _boom():
            raise RuntimeError("audit exploded")

        monkeypatch.setattr(audit_mod, "get_llm_audit", _boom)
        out = self._run_fallback(monkeypatch)
        assert out == "legacy-ok"
