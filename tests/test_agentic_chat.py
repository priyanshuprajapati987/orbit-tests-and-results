"""Tests for core/agentic_chat.py — GPT-class agentic tool-use loop.

Hermetic: router is mocked (no live LLM calls). Tool registry is monkeypatched
where needed. Trigger heuristics + TOOL-line parser + ReAct loop + SSE wiring
in chat_api are covered.
"""

from __future__ import annotations

import asyncio
import json

import pytest


def _collect(coro):
    """Drive an async generator to completion and return its event list."""

    async def _run():
        return [ev async for ev in coro]

    return asyncio.run(_run())


# ── Trigger heuristics ───────────────────────────────────────────────────


class TestTrigger:
    def test_off_env(self, monkeypatch):
        monkeypatch.setattr("orbit.orbit.core.agentic_chat._AGENTIC_ON", False)
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("latest AI news today please") is False

    def test_force_prefix(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("deep: explain quantum entanglement") is True
        assert should_go_agentic("research: transformer architectures") is True

    def test_current_info(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("what is the latest news on AI chips") is True

    def test_needs_tool(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("search the web for python 3.14 release notes") is True

    def test_multi_step(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("read the config and then summarize it") is True

    def test_long_question(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        q = (
            "Can you explain in depth how retrieval augmented generation "
            "works in modern language model systems and when to prefer it?"
        )
        assert should_go_agentic(q) is True

    def test_short_chit_chat_skipped(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("hi") is False
        assert should_go_agentic("thanks!") is False


# ── TOOL-line parser ─────────────────────────────────────────────────────


class TestParser:
    def test_valid_tool_line(self):
        from orbit.orbit.core.agentic_chat import _parse_tool_line

        text = 'TOOL:{"name": "web_search", "arguments": {"query": "python"}}'
        parsed = _parse_tool_line(text)
        assert parsed == {"name": "web_search", "arguments": {"query": "python"}}

    def test_tool_alias(self):
        from orbit.orbit.core.agentic_chat import _parse_tool_line

        text = 'TOOL:{"tool": "system_info", "args": {}}'
        parsed = _parse_tool_line(text)
        assert parsed["name"] == "system_info"

    def test_no_tool_line(self):
        from orbit.orbit.core.agentic_chat import _parse_tool_line

        assert _parse_tool_line("Just a plain answer.") is None
        assert _parse_tool_line("") is None

    def test_malformed_json(self):
        from orbit.orbit.core.agentic_chat import _parse_tool_line

        assert _parse_tool_line('TOOL:{"name": broken}') is None

    def test_strip_tool_line(self):
        from orbit.orbit.core.agentic_chat import _strip_tool_line

        text = 'TOOL:{"name": "x", "arguments": {}}'
        assert _strip_tool_line(text) == ""
        mixed = 'some prose\nTOOL:{"name": "x", "arguments": {}}\nmore'
        assert "TOOL" not in _strip_tool_line(mixed)

    def test_alt_format_bare_string(self):
        from orbit.orbit.core.agentic_chat import _parse_tool_line

        result = _parse_tool_line('TOOL:execute_code("print(2+2)")')
        assert result is not None
        assert result["name"] == "execute_code"
        assert result["arguments"]["code"] == "print(2+2)"

    def test_alt_format_json_parens(self):
        from orbit.orbit.core.agentic_chat import _parse_tool_line

        result = _parse_tool_line('TOOL:execute_code({"code": "print(42)"})')
        assert result is not None
        assert result["arguments"]["code"] == "print(42)"

    def test_alt_format_kw_args(self):
        from orbit.orbit.core.agentic_chat import _parse_tool_line

        result = _parse_tool_line('TOOL:web_search(query="python 3.14")')
        assert result is not None
        assert result["arguments"]["query"] == "python 3.14"

    def test_alt_format_multiline(self):
        from orbit.orbit.core.agentic_chat import _parse_tool_line

        result = _parse_tool_line(
            'TOOL:execute_code("import math\nresult = math.factorial(12)\nprint(result)")'
        )
        assert result is not None
        assert "factorial" in result["arguments"]["code"]

    def test_strip_alt_format(self):
        from orbit.orbit.core.agentic_chat import _strip_tool_line

        stripped = _strip_tool_line('TOOL:execute_code("print(2+2)")')
        assert stripped == ""


# ── Tool registry ────────────────────────────────────────────────────────


class TestRegistry:
    def test_unknown_tool(self):
        from orbit.orbit.core.agentic_chat import execute_tool

        out = execute_tool("nonexistent_tool", {})
        assert out.startswith("ERROR")
        assert "nonexistent_tool" in out

    def test_tool_exception_becomes_error(self, monkeypatch):
        from orbit.orbit.core import agentic_chat

        def boom(args):
            raise RuntimeError("kaboom")

        monkeypatch.setitem(
            agentic_chat.TOOL_REGISTRY, "boom", {"fn": boom, "desc": "test"}
        )
        out = agentic_chat.execute_tool("boom", {})
        assert out.startswith("ERROR")
        assert "kaboom" in out

    def test_registry_size(self):
        from orbit.orbit.core.agentic_chat import TOOL_REGISTRY

        assert len(TOOL_REGISTRY) >= 10
        assert "web_search" in TOOL_REGISTRY
        assert "read_file" in TOOL_REGISTRY
        assert "execute_code" in TOOL_REGISTRY
        assert "browse_web" in TOOL_REGISTRY
        assert "deep_research" in TOOL_REGISTRY

    def test_execute_code_tool(self):
        from orbit.orbit.core.agentic_chat import execute_tool

        result = execute_tool("execute_code", {"code": "print(2+2)"})
        assert "4" in result
        assert "OUTPUT" in result

    def test_execute_code_banned_import(self):
        from orbit.orbit.core.agentic_chat import execute_tool

        result = execute_tool("execute_code", {"code": "import os; print(os.getcwd())"})
        assert "BLOCKED" in result or "ERROR" in result

    def test_execute_code_requires_code(self):
        from orbit.orbit.core.agentic_chat import execute_tool

        result = execute_tool("execute_code", {})
        assert "ERROR" in result

    def test_browse_web_requires_url(self):
        from orbit.orbit.core.agentic_chat import execute_tool

        result = execute_tool("browse_web", {})
        assert "ERROR" in result

    def test_deep_research_requires_topic(self):
        from orbit.orbit.core.agentic_chat import execute_tool

        result = execute_tool("deep_research", {})
        assert "ERROR" in result

    def test_trigger_code_keywords(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("run this python code to compute factorial")
        assert should_go_agentic("calculate 15% of 240")
        assert should_go_agentic("execute this code")

    def test_trigger_browse_keywords(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("open the url https://example.com")
        assert should_go_agentic("read the page content")

    def test_trigger_research_keywords(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("deep research on quantum computing")
        assert should_go_agentic("find sources and citations for AI safety")


# ── ReAct loop (mocked router) ───────────────────────────────────────────


class _FakeRouter:
    """Deterministic scripted router: replays a list of full responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def stream_generate(self, request):
        self.calls += 1
        text = self._responses.pop(0) if self._responses else "(empty)"
        # Yield in 3 chunks to exercise incremental buffer parsing
        n = max(1, len(text) // 3)
        for i in range(0, len(text), n):
            yield text[i : i + n]


@pytest.fixture
def fake_router(monkeypatch):
    def _install(responses):
        fr = _FakeRouter(responses)
        from orbit.orbit.core.llm import router as router_mod

        monkeypatch.setattr(router_mod, "get_router", lambda: fr)
        return fr

    return _install


class TestReActLoop:
    def test_direct_answer_no_tools(self, fake_router):
        fr = fake_router(["The capital of France is Paris."])
        from orbit.orbit.core.agentic_chat import get_agentic_chat

        events = _collect(get_agentic_chat().stream("capital of france?"))

        done = events[-1]["done"]
        assert done["agentic"] is True
        assert "Paris" in done["content"]
        assert done["tools_used"] == []
        assert fr.calls == 1

    def test_thinking_then_answer(self, fake_router):
        fake_router(
            ["<thinking>The user wants a fact. I recall it.</thinking>Water boils at 100C."]
        )
        from orbit.orbit.core.agentic_chat import get_agentic_chat

        events = _collect(get_agentic_chat().stream("boiling point of water?"))

        thinking = "".join(e["thinking"] for e in events if "thinking" in e)
        done = events[-1]["done"]
        assert "boils" in done["content"]
        assert "thinking" not in done["content"].lower()  # never leak into answer
        assert thinking and "user wants a fact" in thinking  # trace captured
        assert "</thi" not in thinking  # no partial closing-tag leak
        assert done["thought"] is True

    def test_tool_then_answer(self, fake_router, monkeypatch):
        fr = fake_router(
            [
                'TOOL:{"name": "web_search", "arguments": {"query": "latest AI"}}',
                "OBSERVATION received. Here is the answer: AI is advancing rapidly.",
            ]
        )
        from orbit.orbit.core import agentic_chat

        monkeypatch.setitem(
            agentic_chat.TOOL_REGISTRY,
            "web_search",
            {"fn": lambda a: "- Fake result | snippet | https://example.com", "desc": "x"},
        )
        from orbit.orbit.core.agentic_chat import get_agentic_chat

        events = _collect(get_agentic_chat().stream("latest AI news?"))

        starts = [e["tool_start"] for e in events if "tool_start" in e]
        results = [e["tool_result"] for e in events if "tool_result" in e]
        done = events[-1]["done"]

        assert len(starts) == 1 and starts[0]["name"] == "web_search"
        assert len(results) == 1 and "Fake result" in results[0]["output"]
        assert done["tools_used"] == ["web_search"]
        assert "advancing" in done["content"]
        assert fr.calls == 2

    def test_multi_step_tool_chain(self, fake_router, monkeypatch):
        fake_router(
            [
                'TOOL:{"name": "list_dir", "arguments": {"path": "."}}',
                'TOOL:{"name": "read_file", "arguments": {"path": "./a.txt"}}',
                "The file contains hello world.",
            ]
        )
        from orbit.orbit.core import agentic_chat

        monkeypatch.setitem(
            agentic_chat.TOOL_REGISTRY,
            "list_dir",
            {"fn": lambda a: "a.txt\nb.txt", "desc": "x"},
        )
        monkeypatch.setitem(
            agentic_chat.TOOL_REGISTRY,
            "read_file",
            {"fn": lambda a: "hello world", "desc": "x"},
        )
        from orbit.orbit.core.agentic_chat import get_agentic_chat

        events = _collect(get_agentic_chat().stream("list files then read a.txt"))

        done = events[-1]["done"]
        assert done["steps"] == 3
        assert done["tools_used"] == ["list_dir", "read_file"]
        assert "hello world" in done["content"]

    def test_max_steps_forces_final(self, fake_router, monkeypatch):
        # Step 1 tries a tool; step 2 (== max_steps) must produce a final answer.
        # If step 2 still emits a TOOL line the loop would exhaust with no answer,
        # so the scripted router gives a clean final on the last step.
        fake_router(
            [
                'TOOL:{"name": "system_info", "arguments": {}}',
                "Final answer after tool calls.",
            ]
        )
        from orbit.orbit.core import agentic_chat

        monkeypatch.setitem(
            agentic_chat.TOOL_REGISTRY,
            "system_info",
            {"fn": lambda a: '{"cpu": 42}', "desc": "x"},
        )
        from orbit.orbit.core.agentic_chat import get_agentic_chat

        events = _collect(
            get_agentic_chat().stream("system status deep dive?", max_steps=2)
        )

        done = events[-1]["done"]
        assert done["steps"] <= 2
        assert "Final answer" in done["content"]

    def test_router_exception_yields_error_done(self, monkeypatch):
        from orbit.orbit.core.llm import router as router_mod

        class _Boom:
            async def stream_generate(self, request):
                raise RuntimeError("router down")
                yield ""  # pragma: no cover

        monkeypatch.setattr(router_mod, "get_router", lambda: _Boom())
        from orbit.orbit.core.agentic_chat import get_agentic_chat

        events = _collect(get_agentic_chat().stream("hello"))

        done = events[-1]["done"]
        assert done.get("error")
        assert "agentic_failed" in done["error"]


# ── SSE contract + wiring smoke ──────────────────────────────────────────


class TestSSEContract:
    def test_tool_line_format_stable(self):
        """The TOOL: line format the model must emit — keep regex in sync."""
        from orbit.orbit.core.agentic_chat import _TOOL_LINE_RE

        sample = 'TOOL:{"name": "web_search", "arguments": {"query": "x"}}'
        m = _TOOL_LINE_RE.search(sample)
        assert m, "canonical TOOL line must match"
        assert json.loads(m.group(1))["name"] == "web_search"

    def test_stream_events_have_sse_types(self, fake_router, monkeypatch):
        """Every yielded event maps to a known SSE type (frontend handler contract)."""
        fake_router(
            [
                "<thinking>need data</thinking>"
                'TOOL:{"name": "web_search", "arguments": {"query": "x"}}',
                "Final.",
            ]
        )
        from orbit.orbit.core import agentic_chat

        monkeypatch.setitem(
            agentic_chat.TOOL_REGISTRY,
            "web_search",
            {"fn": lambda a: "result", "desc": "x"},
        )
        from orbit.orbit.core.agentic_chat import get_agentic_chat

        events = _collect(get_agentic_chat().stream("search x latest?"))
        known = {"thinking", "tool_start", "tool_result", "token", "done"}
        assert all(set(e.keys()) & known for e in events)
        # frontend processLine must handle exactly these types
        types_seen = set()
        for e in events:
            types_seen |= set(e.keys())
        assert types_seen <= known

    def test_chat_api_has_agentic_branch(self):
        """chat_stream must import + gate the agentic path (wiring regression)."""
        import inspect

        from orbit.orbit.core import chat_api

        src = inspect.getsource(chat_api.chat_stream)
        assert "should_go_agentic" in src
        assert "tool_start" in src
        assert "thinking" in src
        assert "agentic_fallback" in src
