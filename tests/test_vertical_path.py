# ORBIT — Phase 1 Vertical-Path Tests (pure logic, no network)
#
# Covers the most-used vertical slice WITHOUT the full Flask app:
#   assistant init -> tool decision table -> router config -> response scoring
# (Full LLM path: scripts/run_ground_truth_benchmark.py with Ollama up;
#  server contract: tests/test_api_contract.py with ORBIT_SMOKE_SERVER=1)
#
# Run:  python -m pytest tests/test_vertical_path.py -v
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ── 1. Assistant boot path ──────────────────────────────────────────────────

def test_assistant_imports_and_initializes():
    mod = pytest.importorskip("orbit.orbit.assistant", reason="assistant not importable")
    assistant_cls = getattr(mod, "Assistant", None)
    assert assistant_cls is not None, "Assistant class missing"
    instance = assistant_cls()  # verified light-init (no network)
    assert hasattr(instance, "check_ollama")
    assert hasattr(instance, "get_router_status")
    assert hasattr(instance, "history")


# ── 2. Tool decision table (TOOL_DEFINITIONS contract) ─────────────────────

def test_tool_definitions_integrity():
    mod = pytest.importorskip("orbit.orbit.assistant")
    tool_defs = getattr(mod, "TOOL_DEFINITIONS", None)
    assert isinstance(tool_defs, dict) and tool_defs, "TOOL_DEFINITIONS missing"
    assert len(tool_defs) >= 40, f"TOOL_DEFINITIONS shrank unexpectedly: {len(tool_defs)}"
    for name, spec in tool_defs.items():
        assert isinstance(name, str) and name, "tool name must be non-empty str"
        # RouteLLM/ToolGate schema: keyword-routed dict (or class/callable)
        if isinstance(spec, dict):
            assert any(k in spec for k in ("keywords", "description", "action", "func", "handler")), (
                f"tool '{name}' lacks routing keys (keywords/description/action)"
            )


# ── 3. Provider routing policy (local-first / offline) ─────────────────────

def _routing():
    cfg = pytest.importorskip("orbit.orbit.config")
    return cfg


def test_provider_routing_covers_all_ten_tasks():
    cfg = _routing()
    routing = cfg.PROVIDER_ROUTING
    expected = {
        "coding", "reasoning", "fast", "general", "writing",
        "search", "creative", "facts", "vision", "voice",
    }
    assert expected <= set(routing), f"missing tasks: {expected - set(routing)}"


def test_offline_mode_restricted_to_ollama(monkeypatch):
    cfg = _routing()
    if not getattr(cfg, "OFFLINE_MODE", False):
        pytest.skip("ORBIT_OFFLINE not enabled in this environment")
    for task, order in cfg.PROVIDER_ROUTING.items():
        assert order == ["ollama"], f"offline mode leaks non-local provider for {task}: {order}"


def test_local_first_policy_documented_flags_exist():
    # Config must expose the Phase-1 policy switches (values tested in
    # test_offline_mode_restricted_to_ollama / benchmark harness env docs).
    cfg = _routing()
    assert hasattr(cfg, "OFFLINE_MODE"), "ORBIT_OFFLINE flag missing"
    src = _config_source()
    assert "ORBIT_LOCAL_FIRST" in src, "ORBIT_LOCAL_FIRST policy flag missing from config"


def _config_source() -> str:
    cfg = _routing()
    import inspect

    return inspect.getsource(cfg)


# ── 4. Response scoring path (ground-truth check pipeline) ─────────────────

def test_ground_truth_dataset_complete():
    gt = pytest.importorskip("orbit.orbit.core.ground_truth")
    items = getattr(gt, "GROUND_TRUTH", None)
    assert items, "GROUND_TRUTH dataset missing"
    assert len(items) == 103, f"dataset drifted: {len(items)} != 103 (update CLAIMS.md if intentional)"
    cats = {i.category for i in items}
    assert cats <= {"facts", "math", "coding", "reasoning", "general"}, cats


def test_ground_truth_scoring_math_tolerance():
    gt = pytest.importorskip("orbit.orbit.core.ground_truth")
    math_items = [i for i in gt.GROUND_TRUTH if i.category == "math" and i.number is not None]
    assert math_items, "no math items with numeric answers"
    sample = math_items[0]
    # correct numeric response passes
    assert sample.check(str(sample.number))["correct"] is True
    # clearly wrong numeric response fails (avoid digit-substring collisions,
    # e.g. answer=4 vs probe "42": required-substring matching would pass)
    wrong = "-999" if "4" not in "-999" or sample.number != 4.0 else "-777"
    assert sample.check(wrong)["correct"] is False or sample.number == float(wrong)


def test_ground_truth_scoring_required_substrings():
    gt = pytest.importorskip("orbit.orbit.core.ground_truth")
    fact_items = [i for i in gt.GROUND_TRUTH if i.category == "facts" and i.required]
    assert fact_items, "no fact items with required substrings"
    sample = fact_items[0]
    fake_good = " ".join(sample.required) + " extra context"
    assert sample.check(fake_good)["correct"] is True
    assert sample.check("completely unrelated answer")["correct"] is False
