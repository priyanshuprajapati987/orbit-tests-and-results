# ORBIT — Chat/command/router function audit.
# Pure-logic: MessageFormatter, state machine, commander parsing, smart-router.
# No LLM/provider calls; deterministic functions only.
#
# Run:  python -m pytest tests/test_chat_router_audit.py -v
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ───────────────────────── conversation_engine ─────────────────────────

class TestConversationState:
    def test_states(self):
        from orbit.orbit.core.conversation_engine import ConversationState

        vals = [s.value for s in ConversationState]
        assert set(vals) == {"idle", "routing", "generating", "complete", "error"}

    def test_valid_transitions_idle(self):
        from orbit.orbit.core.conversation_engine import ConversationState, VALID_TRANSITIONS

        allowed = VALID_TRANSITIONS[ConversationState.IDLE]
        assert ConversationState.ROUTING in allowed
        assert ConversationState.ERROR in allowed
        assert ConversationState.COMPLETE not in allowed

    def test_valid_transitions_generating(self):
        from orbit.orbit.core.conversation_engine import ConversationState, VALID_TRANSITIONS

        allowed = VALID_TRANSITIONS[ConversationState.GENERATING]
        assert ConversationState.COMPLETE in allowed
        assert ConversationState.ERROR in allowed
        assert ConversationState.IDLE not in allowed

    def test_engine_transition_valid(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine, ConversationState

        e = ConversationEngine(session_id="t1")
        assert e.state == ConversationState.IDLE
        e._transition(ConversationState.ROUTING)
        assert e.state == ConversationState.ROUTING

    def test_engine_transition_invalid_raises(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine, ConversationState

        e = ConversationEngine(session_id="t2")
        with pytest.raises(ValueError, match="Invalid transition"):
            e._transition(ConversationState.COMPLETE)  # IDLE -> COMPLETE not allowed

    def test_engine_double_error_idempotent(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine, ConversationState

        e = ConversationEngine(session_id="t3")
        e._transition(ConversationState.ERROR)
        e._transition(ConversationState.ERROR)  # must NOT raise (idempotent)
        assert e.state == ConversationState.ERROR

    def test_engine_recovery_error_to_routing(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine, ConversationState

        e = ConversationEngine(session_id="t4")
        e._transition(ConversationState.ERROR)
        e._transition(ConversationState.ROUTING)  # hard recovery
        assert e.state == ConversationState.ROUTING


class TestTurnResult:
    def test_to_dict_shape(self):
        from orbit.orbit.core.conversation_engine import ConversationState, TurnResult

        r = TurnResult(
            content="hello", state=ConversationState.COMPLETE, query_type="general",
            complexity="simple", provider="ollama", model="llama3.2",
            latency_ms=123.456, confidence=0.9123, token_estimate=42,
        )
        d = r.to_dict()
        assert d["state"] == "complete"
        assert d["latency_ms"] == 123.5
        assert d["confidence"] == 0.91
        assert d["token_estimate"] == 42
        assert d["used_cache"] is False


class TestMessageFormatter:
    def test_truncate_short_passthrough(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        assert MessageFormatter.truncate("hello") == "hello"

    def test_truncate_empty(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        assert MessageFormatter.truncate("") == ""
        assert MessageFormatter.truncate(None) is None

    def test_truncate_long(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        long = "x" * 2000
        out = MessageFormatter.truncate(long, max_len=100)
        assert len(out) < 200
        assert "truncated" in out

    def test_collapse_blank_lines(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        assert MessageFormatter.collapse_blank_lines("a\n\n\n\n\nb") == "a\n\nb"
        assert MessageFormatter.collapse_blank_lines("  a  ") == "a"

    def test_collapse_many_newlines(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        out = MessageFormatter.collapse_blank_lines("a\n\n\n\n\n\n\n\nb")
        assert "\n\n\n" not in out

    def test_structure_lists_converts_comma_run(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        # heuristic requires >=5 short items AND total len >120
        text = ("apple, banana, cherry, date, elderberry, fig, grape, honeydew, "
                "ice-cream, jackfruit, kiwi, lemon, mango, nectarine, orange")
        out = MessageFormatter.structure_lists(text)
        assert "- apple" in out
        assert "- banana" in out

    def test_structure_lists_keeps_bullets(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        text = "- already\n- bullet\n- list"
        out = MessageFormatter.structure_lists(text)
        assert out == text  # unchanged

    def test_structure_lists_short_line_untouched(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        assert MessageFormatter.structure_lists("short, line") == "short, line"

    def test_format_pipeline(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        out = MessageFormatter.format("a\n\n\n\nb")
        assert "\n\n\n" not in out


# ───────────────────────── commander ─────────────────────────

class TestCommanderParse:
    def _parse(self, text):
        from orbit.orbit.core.commander import parse_command

        return parse_command(text)

    def test_open_app_known(self):
        i = self._parse("open chrome")
        assert i.action == "open_app"
        assert i.target == "chrome"
        assert i.category == "app"
        assert i.confidence >= 0.9

    def test_open_app_alias_vscode(self):
        i = self._parse("launch vs code")
        assert i.action == "open_app"
        assert i.target == "code"

    def test_open_app_alias_edge(self):
        i = self._parse("start microsoft edge")
        assert i.target == "msedge"

    def test_open_app_unknown(self):
        i = self._parse("open someapp")
        assert i.action == "open_app"
        assert i.target == "someapp"
        assert i.confidence < 0.9  # lower confidence for unknown

    def test_close_app(self):
        i = self._parse("close firefox")
        assert i.action == "close_app"
        assert i.target == "firefox"

    def test_delegate_agent_prefix(self):
        i = self._parse("agent: search for weather")
        assert i.action == "delegate_to_agent"
        assert i.target == "search for weather"
        assert i.confidence == 0.9

    def test_delegate_ask_prefix(self):
        i = self._parse("ask queen to plan my day")
        assert i.action == "delegate_to_agent"

    def test_multi_step(self):
        i = self._parse("open chrome then search weather")
        assert i.action == "multi_step"
        assert len(i.params["steps"]) == 2
        assert i.confidence == 0.85

    def test_multi_step_three(self):
        i = self._parse("open chrome and take screenshot and check weather")
        assert i.action == "multi_step"
        assert len(i.params["steps"]) == 3

    def test_screenshot(self):
        i = self._parse("take a screenshot")
        assert i.action == "take_screenshot"

    def test_volume_up(self):
        i = self._parse("volume up")
        assert i.action == "volume_up"

    def test_volume_down(self):
        i = self._parse("volume down")
        assert i.action == "volume_down"

    def test_volume_mute(self):
        i = self._parse("mute the volume")
        assert i.action == "volume_mute"

    def test_brightness_up(self):
        i = self._parse("brightness up")
        assert i.action == "brightness_up"

    def test_system_shutdown(self):
        i = self._parse("shutdown the computer")
        assert i.action == "shutdown"

    def test_system_lock(self):
        i = self._parse("lock screen")
        assert i.action == "lock_screen"

    def test_clipboard_copy(self):
        i = self._parse("copy this")
        assert i.action == "clipboard_copy"

    def test_clipboard_paste(self):
        i = self._parse("paste it")
        assert i.action == "clipboard_paste"

    def test_screenshot_keyword_only(self):
        i = self._parse("screenshot")
        assert i.action == "take_screenshot"

    def test_open_url_not_app(self):
        i = self._parse("open https://example.com")
        assert i.action != "open_app" or "http" in i.target  # URL handled separately

    def test_empty_input(self):
        i = self._parse("")
        assert i.action == "" or i.confidence == 0.0  # no crash

    def test_unknown_text(self):
        i = self._parse("tell me a joke about penguins")
        # may fall through to agent delegation or empty; must not crash
        assert hasattr(i, "action")

    def test_split_multi_step_then(self):
        from orbit.orbit.core.commander import _split_multi_step

        parts = _split_multi_step("open chrome then search weather")
        assert parts == ["open chrome", "search weather"]

    def test_split_multi_step_and(self):
        from orbit.orbit.core.commander import _split_multi_step

        parts = _split_multi_step("take screenshot and check time")
        assert parts == ["take screenshot", "check time"]

    def test_split_multi_step_no_separator(self):
        from orbit.orbit.core.commander import _split_multi_step

        parts = _split_multi_step("just one command")
        assert parts == ["just one command"]


class TestCommandResult:
    def test_defaults(self):
        from orbit.orbit.core.commander import CommandResult

        r = CommandResult()
        assert r.success is False
        assert r.message == ""
        assert r.latency_ms == 0
        assert r.timestamp  # auto-set


# ───────────────────────── smart_router ─────────────────────────

class TestSmartRouter:
    def _router(self):
        from orbit.orbit.core.smart_router import get_smart_router

        return get_smart_router()

    def test_route_empty(self):
        r = self._router().route("")
        assert r.best_agent() is None
        assert r.agents == []

    def test_route_open_app(self):
        r = self._router().route("open chrome")
        assert r.best_agent() is not None
        assert r.intent != ""

    def test_route_screenshot(self):
        r = self._router().route("take a screenshot of my screen")
        assert r.best_agent() is not None

    def test_route_weather(self):
        r = self._router().route("what is the weather today")
        assert r.best_agent() is not None

    def test_route_code(self):
        r = self._router().route("write a python function to sort a list")
        assert r.best_agent() is not None

    def test_route_history_context(self):
        r = self._router().route("what about that?", history=["open chrome", "what is the weather"])
        assert hasattr(r, "best_agent")

    def test_route_result_to_dict(self):
        r = self._router().route("open notepad")
        d = r.to_dict()
        assert "agents" in d or "intent" in d

    def test_has_negation_true(self):
        from orbit.orbit.core.smart_router import _has_negation

        # "not" appears in the 6 words before keyword_pos (7 = pos of "open")
        assert _has_negation("do not open chrome", 7) is True

    def test_has_negation_false(self):
        from orbit.orbit.core.smart_router import _has_negation

        assert _has_negation("open chrome please", 5) is False

    def test_has_negation_multiword(self):
        from orbit.orbit.core.smart_router import _has_negation

        # "open" starts at index 14 in "please do not open chrome"
        assert _has_negation("please do not open chrome", 14) is True

    def test_has_pronoun_true(self):
        from orbit.orbit.core.smart_router import SmartRouter

        r = SmartRouter()
        assert r._has_pronoun("it is broken") is True
        assert r._has_pronoun("this needs fixing") is True

    def test_has_pronoun_false(self):
        from orbit.orbit.core.smart_router import SmartRouter

        r = SmartRouter()
        assert r._has_pronoun("open chrome") is False
        assert r._has_pronoun("take a screenshot") is False

    def test_classify_intent(self):
        router = self._router()
        assert router._classify_intent("open chrome") in ("computer", "chat", "websearch", "code", "general")
        assert router._classify_intent("search the web for news") in ("computer", "chat", "websearch", "code", "general")

    def test_score_agents_returns_list(self):
        router = self._router()
        scores = router._score_agents("open chrome and search weather")
        assert isinstance(scores, list)
        if scores:
            label, score, reason = scores[0]
            assert isinstance(label, str)
            assert isinstance(score, (int, float))

    def test_score_features_returns_list(self):
        router = self._router()
        scores = router._score_features("take a screenshot")
        assert isinstance(scores, list)

    def test_stats_shape(self):
        router = self._router()
        s = router.get_stats()
        assert "routes" in s

    def test_auto_route(self):
        from orbit.orbit.core.smart_router import auto_route

        r = auto_route("open notepad")
        assert hasattr(r, "best_agent")

    def test_best_agent_none_on_empty(self):
        from orbit.orbit.core.smart_router import RouteResult

        r = RouteResult()
        assert r.best_agent() is None
        assert r.best_feature() is None


# ───────────────────────── agents registry ─────────────────────────

class TestAgentsRegistry:
    def test_registry_not_empty(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        assert len(AGENT_REGISTRY) > 0

    def test_all_agents_have_label(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        for key, cls in AGENT_REGISTRY.items():
            assert hasattr(cls, "label"), f"{key} missing label"
            assert isinstance(cls.label, str) and cls.label

    def test_all_agents_have_color(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        for key, cls in AGENT_REGISTRY.items():
            assert hasattr(cls, "color"), f"{key} missing color"

    def test_queen_in_registry(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        assert "QUEEN" in AGENT_REGISTRY

    def test_agent_instantiate_no_assistant(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        for key, cls in AGENT_REGISTRY.items():
            try:
                inst = cls()  # no assistant — many should tolerate
                assert hasattr(inst, "execute")
            except TypeError:
                # some agents require assistant arg — acceptable
                pass

    def test_agent_execute_signature(self):
        import inspect

        from orbit.orbit.agents import AGENT_REGISTRY

        for key, cls in AGENT_REGISTRY.items():
            if hasattr(cls, "execute"):
                sig = inspect.signature(cls.execute)
                params = list(sig.parameters)
                assert "text" in params, f"{key}.execute missing text param"
