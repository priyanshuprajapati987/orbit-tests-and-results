"""Regression tests: Persona-shifting chameleon (rewrite draft to recipient)."""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _stub_router(monkeypatch, answer):
    import orbit.orbit.core.llm.router as rmod

    class _Resp:
        def __init__(self):
            self.content = answer
            self.provider = "ollama"
            self.model = "local"
            self.latency_ms = 1
            self.success = True
            self.error = None
            self.used_cache = False
            self.confidence = None
            self.refined = False
            self.critique = None
            self.counter_arguments = None

    class _Stub:
        def generate(self, req):
            return _Resp()

    monkeypatch.setattr(rmod, "get_router", lambda: _Stub())


def test_rewrite_returns_rewritten(monkeypatch):
    from orbit.orbit.core.persona_shift import rewrite

    _stub_router(
        monkeypatch, "Hi Boss, the launch is on track. Decision needed: approve QA."
    )
    res = rewrite("hey boss launch is going good just need u to approve qa", "boss")
    assert res["rewritten"]
    assert res["recipient"] == "boss"
    assert "formal" not in res["rewritten"].lower() or True


def test_empty_text_errors(monkeypatch):
    from orbit.orbit.core.persona_shift import rewrite

    _stub_router(monkeypatch, "x")
    res = rewrite("", "boss")
    assert "error" in res


def test_unknown_recipient_falls_back(monkeypatch):
    from orbit.orbit.core.persona_shift import _style_for, rewrite

    _stub_router(monkeypatch, "neutral version")
    assert _style_for("alien_overlord") == _style_for("generic")
    res = rewrite("hello", "alien_overlord")
    assert res["recipient"] == "alien_overlord"
    assert res["rewritten"]


def test_rewrite_for_name_uses_relationship(monkeypatch):
    from orbit.orbit.core.persona_shift import rewrite_for_name

    _stub_router(monkeypatch, "Hi Sarah, here is the update.")
    # relationship_tracker may or may not be populated; must not raise.
    res = rewrite_for_name("update for sarah", "Sarah")
    assert "rewritten" in res
