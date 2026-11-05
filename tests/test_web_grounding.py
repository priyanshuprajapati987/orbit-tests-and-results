"""Regression tests: live web-grounding in the conversation engine.

- Time-sensitive query with internet up + WebSearchTool returning results -> grounding
  context string is produced (and would be injected as extra_context).
- Time-sensitive query with internet down -> degrades to None (no grounding, graceful).
- Non-time-sensitive query -> no grounding attempted.
"""

import os
import sys
import types

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _fake_plan(qtype="general"):
    return types.SimpleNamespace(query_type=types.SimpleNamespace(value=qtype))


def test_grounding_produces_context_when_online(monkeypatch):
    import asyncio

    from orbit.orbit.core import conversation_engine as ce

    monkeypatch.setattr(ce, "GROUND_ENABLED", True)

    # Force internet check True.
    import orbit.orbit.core.llm.router as rmod

    monkeypatch.setattr(
        rmod.LLMRouter, "_check_internet", lambda self, timeout=2.0: True
    )

    # Stub WebSearchTool.search to return canned results (no real network).
    import orbit.orbit.tools.web_search as ws

    monkeypatch.setattr(
        ws.WebSearchTool,
        "search",
        lambda self, q, n=5, engine="duckduckgo": {
            "query": q,
            "results": [
                {
                    "title": "Live headline",
                    "snippet": "ORBIT won the AI race today.",
                    "url": "http://x",
                },
            ],
            "engine": "duckduckgo",
        },
    )

    engine = ce.ConversationEngine.__new__(ce.ConversationEngine)
    ctx = asyncio.run(
        engine._ground_web("what is the latest AI news today", _fake_plan("search"))
    )
    assert ctx is not None
    assert "Live web results" in ctx
    assert "ORBIT won the AI race today." in ctx


def test_grounding_degrades_offline(monkeypatch):
    import asyncio

    from orbit.orbit.core import conversation_engine as ce

    monkeypatch.setattr(ce, "GROUND_ENABLED", True)
    import orbit.orbit.core.llm.router as rmod

    monkeypatch.setattr(
        rmod.LLMRouter, "_check_internet", lambda self, timeout=2.0: False
    )

    engine = ce.ConversationEngine.__new__(ce.ConversationEngine)
    ctx = asyncio.run(
        engine._ground_web("what is the latest AI news today", _fake_plan("search"))
    )
    assert ctx is None  # offline -> no grounding, graceful


def test_no_grounding_for_plain_query(monkeypatch):
    import asyncio

    from orbit.orbit.core import conversation_engine as ce

    monkeypatch.setattr(ce, "GROUND_ENABLED", True)
    # Internet would be up, but the query is not time-sensitive -> no grounding.
    import orbit.orbit.core.llm.router as rmod

    monkeypatch.setattr(
        rmod.LLMRouter, "_check_internet", lambda self, timeout=2.0: True
    )

    engine = ce.ConversationEngine.__new__(ce.ConversationEngine)
    ctx = asyncio.run(
        engine._ground_web("explain photosynthesis", _fake_plan("general"))
    )
    assert ctx is None
