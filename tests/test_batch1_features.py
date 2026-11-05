"""Regression tests: glass-box transparency, runtime mode, router tuner, agent society."""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def test_transparency_records_latest():
    from orbit.orbit.core.transparency import get_transparency_store

    s = get_transparency_store()
    s.reset()
    s.record(
        {"content": "hi", "confidence": 0.5, "provider": "local", "query_type": "chat"}
    )
    assert s.latest()["confidence"] == 0.5
    assert len(s.history(5)) == 1


def test_runtime_mode_default_and_set():
    from orbit.orbit.core.runtime_mode import RuntimeMode

    rm = RuntimeMode(default="local")
    assert rm.force_offline() is True
    assert rm.set("auto") == "auto"
    assert rm.force_offline() is False
    try:
        rm.set("cloud")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid mode accepted")


def test_router_tuner_reorders_by_score():
    from orbit.orbit.core.router_tuner import RouterTuner

    t = RouterTuner()
    t.record("chat", "ollama", latency_ms=5000, success=True)  # slow -> low score
    t.record("chat", "openrouter", latency_ms=400, success=True)  # fast -> high
    chain = t.optimize_chain("chat", [("ollama", "m1"), ("openrouter", "m2")])
    assert chain[0][0] == "openrouter"
    assert "openrouter" in t.stats()["chat"]


def test_agent_society_debate_empty():
    from orbit.orbit.core.agent_society import debate

    res = debate("")
    assert res["ok"] is False
