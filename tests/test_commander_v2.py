"""Tests for Commander v2 — multi-step, agent delegation, parsing."""

from orbit.orbit.core.commander import (
    Commander,
    _split_multi_step,
    get_commander,
    parse_command,
)


class TestMultiStepParsing:
    def test_split_two_steps(self):
        parts = _split_multi_step("open chrome then search weather")
        assert len(parts) == 2
        assert parts[0] == "open chrome"
        assert parts[1] == "search weather"

    def test_split_three_steps(self):
        parts = _split_multi_step("open notepad and type hello then press enter")
        assert len(parts) == 3

    def test_split_with_also(self):
        parts = _split_multi_step("screenshot also open chrome")
        assert len(parts) == 2

    def test_split_single_step(self):
        parts = _split_multi_step("open chrome")
        assert len(parts) == 1

    def test_parse_multi_step_intent(self):
        intent = parse_command("open chrome then search weather")
        assert intent.action == "multi_step"
        assert intent.category == "multi"
        assert len(intent.params["steps"]) == 2


class TestAgentDelegation:
    def test_parse_agent_colon(self):
        intent = parse_command("agent: search for weather")
        assert intent.action == "delegate_to_agent"
        assert intent.category == "agent"
        assert intent.target == "search for weather"

    def test_parse_ask_queen(self):
        intent = parse_command("ask queen to summarize this")
        assert intent.action == "delegate_to_agent"
        assert "summarize this" in intent.target

    def test_parse_task_keyword(self):
        intent = parse_command("task: create a file")
        assert intent.action == "delegate_to_agent"


class TestCommanderSingleton:
    def test_singleton(self):
        c1 = get_commander()
        c2 = get_commander()
        assert c1 is c2

    def test_status_includes_new_intents(self):
        c = get_commander()
        status = c.get_status()
        intents = status["supported_intents"]
        assert any("multi-step" in i for i in intents)
        assert any("agent" in i for i in intents)

    def test_history_empty_initially(self):
        c = Commander()
        assert c.get_history() == []


class TestExistingParsingStillWorks:
    def test_open_app(self):
        intent = parse_command("open chrome")
        assert intent.action == "open_app"
        assert intent.target == "chrome"

    def test_close_app(self):
        intent = parse_command("close notepad")
        assert intent.action == "close_app"

    def test_screenshot(self):
        intent = parse_command("take screenshot")
        assert intent.action == "take_screenshot"

    def test_volume_up(self):
        intent = parse_command("volume up")
        assert intent.action == "volume_up"

    def test_web_search(self):
        intent = parse_command("search for python tutorial")
        assert intent.action == "web_search"
        assert "python tutorial" in intent.target

    def test_type_text(self):
        intent = parse_command('type "hello world"')
        assert intent.action == "keyboard_type"
        assert intent.target == "hello world"

    def test_unknown_fallback(self):
        intent = parse_command("asdfghjkl")
        assert intent.action == "unknown"
        assert intent.confidence == 0.0
