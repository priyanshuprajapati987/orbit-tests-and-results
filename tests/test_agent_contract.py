# ORBIT — Phase 2 agent contract tests (no network, no LLM)
#
# Run:  python -m pytest tests/test_agent_contract.py -v
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def contract():
    return pytest.importorskip("orbit.orbit.core.agent_contract")


# ── Schema validation ───────────────────────────────────────────────────────

def test_request_rejects_empty_text(contract):
    req = contract.AgentRequest(text="   ")
    assert req.validate() is not None


def test_request_rejects_bad_timeout(contract):
    req = contract.AgentRequest(text="hello", timeout_s=0)
    assert req.validate() is not None
    assert contract.AgentRequest(text="hello", timeout_s=901).validate() is not None
    assert contract.AgentRequest(text="hello", timeout_s=60).validate() is None


def test_request_rejects_bad_permissions(contract):
    assert contract.AgentRequest(text="hi", permissions="root").validate() is not None
    assert contract.AgentRequest(text="hi", permissions="read").validate() is None


def test_result_to_dict_shape(contract):
    r = contract.AgentResult(
        ok=True, output="x", agent_label="QUEEN", elapsed_ms=1.5, trace_id="abc"
    )
    d = r.to_dict()
    assert set(d) >= {"ok", "output", "agent_label", "elapsed_ms", "trace_id", "error", "timed_out"}


# ── run_agent against fake agents (deterministic) ──────────────────────────

class _FakeOk:
    label = "FAKE"
    metrics = {"calls": 1}

    def execute(self, text, context=None):
        return f"echo:{text}"


class _FakeBoom:
    label = "BOOM"
    metrics = {}

    def execute(self, text, context=None):
        raise RuntimeError("kaputt sk-secret-abcdefghijklmnop")


class _FakeSlow:
    label = "SLOW"
    metrics = {}

    def execute(self, text, context=None):
        time.sleep(5)
        return "late"


def test_run_agent_success_path(contract, monkeypatch):
    monkeypatch.setattr(contract, "get_agent", lambda key: _FakeOk())
    res = contract.run_agent("FAKE", contract.AgentRequest(text="hello"))
    assert res.ok and res.output == "echo:hello"
    assert res.agent_label == "FAKE"
    assert res.elapsed_ms >= 0
    assert res.metrics_snapshot.get("calls") == 1


def test_run_agent_timeout(contract, monkeypatch):
    monkeypatch.setattr(contract, "get_agent", lambda key: _FakeSlow())
    res = contract.run_agent("SLOW", contract.AgentRequest(text="wait", timeout_s=0.5))
    assert not res.ok and res.timed_out
    assert "timeout" in res.error


def test_run_agent_agent_exception_is_contained(contract, monkeypatch):
    monkeypatch.setattr(contract, "get_agent", lambda key: _FakeBoom())
    res = contract.run_agent("BOOM", contract.AgentRequest(text="boom"))
    assert not res.ok and not res.timed_out
    assert "agent_error" in res.error
    assert "kaputt" in res.error  # raw error kept in-memory result for logs


def test_run_agent_unknown_key(contract):
    res = contract.run_agent("NOPE_NOT_AN_AGENT", contract.AgentRequest(text="x"))
    assert not res.ok
    assert "unknown agent" in res.error


def test_run_agent_invalid_request_short_circuits(contract, monkeypatch):
    called = []
    monkeypatch.setattr(contract, "get_agent", lambda key: called.append(key) or _FakeOk())
    res = contract.run_agent("FAKE", contract.AgentRequest(text=""))
    assert not res.ok and "invalid_request" in res.error
    assert called == []  # agent never instantiated


# ── Registry integration (light, no LLM call) ──────────────────────────────

def test_registry_exposes_orchestration_four(contract):
    agents = pytest.importorskip("orbit.agents")
    for key in ("QUEEN", "PLN", "EXE", "CRT"):
        assert key in agents.AGENT_REGISTRY, f"{key} missing from AGENT_REGISTRY"


def test_real_queen_agent_callable_via_contract_no_llm_needed_for_shape(contract):
    # Runs QUEEN.execute for a trivial text; on machines without Ollama the
    # agent should still return a bounded AgentResult (ok may be False).
    res = contract.run_agent(
        "QUEEN", contract.AgentRequest(text="ping", timeout_s=30)
    )
    assert isinstance(res, contract.AgentResult)
    assert res.agent_label
    assert res.trace_id
    assert 0 <= res.elapsed_ms <= 60_000
