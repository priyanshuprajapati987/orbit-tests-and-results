"""Tests for Commander (natural-language OS control) + self-improvement adoption fix."""

import os
import sys
from pathlib import Path

os.environ["ORBIT_SKIP_STARTUP"] = "1"
os.environ["ORBIT_API_AUTH_ENABLED"] = "0"
sys.path.insert(0, str(Path(__file__).parent.parent))


# ══════════════════════════════════════════════════════════════════════
# Commander Parser Tests
# ══════════════════════════════════════════════════════════════════════


def test_parse_open_app():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("open chrome")
    assert intent.action == "open_app"
    assert intent.target == "chrome"
    assert intent.confidence > 0.8
    assert intent.category == "app"


def test_parse_open_app_alias():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("launch vs code")
    assert intent.action == "open_app"
    assert intent.target == "code"
    assert intent.confidence > 0.9


def test_parse_close_app():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("close firefox")
    assert intent.action == "close_app"
    assert intent.target == "firefox"


def test_parse_screenshot():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("take a screenshot")
    assert intent.action == "take_screenshot"
    assert intent.confidence > 0.9


def test_parse_volume_up():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("volume up")
    assert intent.action == "volume_up"
    assert intent.confidence > 0.9


def test_parse_volume_mute():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("mute volume")
    assert intent.action == "volume_mute"


def test_parse_brightness_down():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("dim the screen")
    assert intent.action == "brightness_down"
    assert intent.category == "system"


def test_parse_lock_screen():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("lock screen")
    assert intent.action == "lock_screen"
    assert intent.category == "system"


def test_parse_shutdown():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("shut down the computer")
    assert intent.action == "shutdown"


def test_parse_web_search():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("search for python tutorials")
    assert intent.action == "web_search"
    assert intent.target == "for python tutorials"
    assert intent.category == "browser"


def test_parse_open_url():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("open https://github.com")
    assert intent.action == "open_url"
    assert "github.com" in intent.target


def test_parse_type_text():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command('type "hello world"')
    assert intent.action == "keyboard_type"
    assert intent.target == "hello world"


def test_parse_press_key():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("press enter")
    assert intent.action == "keyboard_press"
    assert intent.target == "enter"


def test_parse_scroll():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("scroll down")
    assert intent.action == "mouse_scroll"
    assert intent.target == "down"


def test_parse_system_info():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("system info")
    assert intent.action == "system_info"
    assert intent.category == "info"


def test_parse_weather():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("what's the weather")
    assert intent.action == "get_weather"


def test_parse_time():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("what time is it")
    assert intent.action == "get_time"


def test_parse_unknown():
    from orbit.orbit.core.commander import parse_command

    intent = parse_command("asdfghjkl random gibberish")
    assert intent.action == "unknown"
    assert intent.confidence == 0.0


# ══════════════════════════════════════════════════════════════════════
# Commander Executor Tests
# ══════════════════════════════════════════════════════════════════════


def test_commander_execute_unknown():
    from orbit.orbit.core.commander import get_commander

    c = get_commander()
    result = c.execute("random gibberish")
    assert result.success is False
    assert "don't understand" in result.message.lower()


def test_commander_execute_time():
    from orbit.orbit.core.commander import get_commander

    c = get_commander()
    result = c.execute("what time is it")
    assert result.success is True
    assert "AM" in result.message or "PM" in result.message


def test_commander_execute_date():
    from orbit.orbit.core.commander import get_commander

    c = get_commander()
    result = c.execute("what's the date")
    assert result.success is True
    assert "2026" in result.message or "2025" in result.message


def test_commander_execute_system_info():
    from orbit.orbit.core.commander import get_commander

    c = get_commander()
    result = c.execute("system info")
    assert result.success is True
    assert result.data is not None
    assert "os" in result.data


def test_commander_history():
    from orbit.orbit.core.commander import get_commander

    c = get_commander()
    c.execute("what time is it")
    c.execute("system info")
    history = c.get_history(10)
    assert len(history) >= 2
    assert history[-1]["action"] == "system_info"


def test_commander_status():
    from orbit.orbit.core.commander import get_commander

    c = get_commander()
    status = c.get_status()
    assert "total_commands" in status
    assert "success_rate" in status
    assert "supported_intents" in status


# ══════════════════════════════════════════════════════════════════════
# Commander API Tests
# ══════════════════════════════════════════════════════════════════════


def test_api_commander_status():
    from orbit.orbit.server import create_app

    app = create_app()
    c = app.test_client()
    r = c.get("/api/commander/status")
    assert r.status_code == 200
    data = r.get_json()
    assert "total_commands" in data


def test_api_commander_parse():
    from orbit.orbit.server import create_app

    app = create_app()
    c = app.test_client()
    r = c.post("/api/commander/parse", json={"command": "open chrome"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["action"] == "open_app"
    assert data["target"] == "chrome"


def test_api_commander_execute():
    from orbit.orbit.server import create_app

    app = create_app()
    c = app.test_client()
    r = c.post("/api/commander/execute", json={"command": "what time is it"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert "AM" in data["message"] or "PM" in data["message"]


def test_api_commander_parse_empty():
    from orbit.orbit.server import create_app

    app = create_app()
    c = app.test_client()
    r = c.post("/api/commander/parse", json={"command": ""})
    assert r.status_code == 400


def test_api_commander_history():
    from orbit.orbit.server import create_app

    app = create_app()
    c = app.test_client()
    r = c.get("/api/commander/history")
    assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Self-Improvement Adoption Tests
# ══════════════════════════════════════════════════════════════════════


def test_self_improvement_lessons_context():
    from orbit.orbit.core.self_improvement import get_self_improvement

    si = get_self_improvement()
    # Add some feedback
    si.add_feedback(
        "TEST_AGENT", "test_task", "input", "output", 0.2, comment="bad result"
    )
    # Get lessons context
    ctx = si.get_improvement_context("TEST_AGENT")
    assert ctx["agent_id"] == "TEST_AGENT"
    assert "lessons" in ctx


def test_self_improvement_lesson_applied():
    from orbit.orbit.core.self_improvement import get_self_improvement

    si = get_self_improvement()
    si.add_feedback("TEST_AGENT2", "task", "in", "out", 0.1, comment="fail")
    lessons = si.get_lessons("TEST_AGENT2")
    assert len(lessons) > 0
    result = si.record_lesson_applied(lessons[0]["id"], True)
    assert result is True


def test_conversation_engine_has_lessons_method():
    from orbit.orbit.core.conversation_engine import ConversationEngine

    assert hasattr(ConversationEngine, "_get_lessons_context")


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
