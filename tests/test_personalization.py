"""Regression tests: personalization via SmartMemory in the chat path.

- build_personalization_context returns None when there is nothing learned.
- After learning a preference + a correction, it returns a compact '[User memory]' block
  that surfaces them (so ORBIT can tailor answers).
- ConversationEngine._personalize degrades to None on any failure and never raises.
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def test_personalization_empty(tmp_path, monkeypatch):
    import orbit.orbit.core.smart_memory as sm

    monkeypatch.setattr(sm, "_get_data_dir", lambda: tmp_path)
    m = sm.SmartMemory()
    assert m.build_personalization_context("hello there") is None


def test_personalization_surfaces_learned(tmp_path, monkeypatch):
    import orbit.orbit.core.smart_memory as sm

    monkeypatch.setattr(sm, "_get_data_dir", lambda: tmp_path)
    m = sm.SmartMemory()
    m.learn_preference("write python code now", "COD", True)
    ctx = m.build_personalization_context("write python code")
    assert ctx is not None
    assert "COD" in ctx
    assert "User memory" in ctx

    m.record_correction("python code refactor", "RES", "WRI")
    ctx2 = m.build_personalization_context("python code refactor")
    assert ctx2 is not None
    assert "WRI" in ctx2


def test_personalization_caps_and_skips_garbage():
    from collections import defaultdict

    from orbit.orbit.core.smart_memory import SmartMemory

    m = SmartMemory.__new__(SmartMemory)
    m._preferences = {}
    m._corrections = []
    m._topic_frequency = {}
    m._agent_patterns = {}
    m._time_patterns = defaultdict(lambda: defaultdict(int))
    m._recent_queries = __import__("collections").deque(maxlen=50)
    m._query_lengths = []
    m._expertise_level = "intermediate"
    m._lock = __import__("threading").RLock()
    # 50 synthetic garbage preferences + a couple of real ones.
    for i in range(50):
        m._preferences[f"agent_for_query_{i}"] = type(
            "P", (), {"value": f"agent_{i % 5}", "confidence": 0.6}
        )()
    m._preferences["response_style"] = type(
        "P", (), {"value": "concise", "confidence": 0.7}
    )()
    ctx = m.build_personalization_context("anything")
    assert ctx is not None
    assert "agent_for_query_" not in ctx  # synthetic skipped
    assert "response_style" in ctx
    assert ctx.count("\n-") <= 8  # capped


def test_engine_personalize_never_raises(monkeypatch):
    from orbit.orbit.core import conversation_engine as ce

    # Stub smart_memory to return a known block.
    class Stub:
        def build_personalization_context(self, q=""):
            return "[User memory]\n- User preference (response_style): concise"

    import orbit.orbit.core.smart_memory as sm

    monkeypatch.setattr(sm, "get_smart_memory", lambda: Stub())

    engine = ce.ConversationEngine.__new__(ce.ConversationEngine)
    out = engine._personalize("make it short")
    assert out is not None and "concise" in out

    # Failure path -> None, no exception.
    monkeypatch.setattr(
        sm, "get_smart_memory", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    assert engine._personalize("anything") is None
