"""Deep tests for orbit/orbit/assistant_handlers.py — 43 intent handlers (~1094 lines).

Every handler runs through ``ah._handle_tool`` / ``ah._handle_<name>`` with the
underlying feature module (notes, habits, meeting, scheduler, ...) patched, so
no real user data is read or written and no timers/network are touched.

Source bugs fixed together with these tests:
- ``_handle_list`` routed "uncheck item 3" into ``check_item(checked=True)``
  because "uncheck" contains the substring "check" — uncheck/undone is now
  tested before check/mark/done.
- ``_handle_list`` claimed success even when ``delete_list`` returned False
  for a missing list.
- ``_handle_focus`` parsed the unit but ignored it: "focus 2 hours" started a
  2-minute session; hours are now converted to minutes.
- ``_handle_meeting`` called ``search_meetings("")`` before validating the
  empty query.
"""

import sys
import threading
import types
import unittest
from unittest import mock

from orbit.orbit import assistant_handlers as ah
from orbit.orbit import (
    briefing,
    calculator,
    conv_search,
    countdowns,
    expenses,
    flashcards,
    focus_timer,
    habits,
    journal,
    lists,
    meeting,
    notes,
    scheduler,
    screen,
    screen_sharing,
    smart_actions,
    sysinfo,
)


def make_assistant():
    """Assistant stand-in: real history lock, canned prefix, no side effects."""
    a = mock.MagicMock()
    a._history_lock = threading.Lock()
    a.history = []
    a._get_prefix.return_value = "Sir"
    return a


class TestDispatch(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_unknown_intent_returns_empty(self):
        self.assertEqual(ah._handle_tool(self.a, "definitely_not_a_handler", "hi"), "")

    def test_handlers_table_matches_module_functions(self):
        # Every intent maps to _handle_<intent> defined in this module.
        self.assertTrue(ah._HANDLERS)
        self.assertGreaterEqual(len(ah._HANDLERS), 43)
        for intent, fn in ah._HANDLERS.items():
            self.assertEqual(fn.__name__, f"_handle_{intent}")
            self.assertIs(fn, getattr(ah, f"_handle_{intent}"))

    def test_unknown_intent_does_not_touch_assistant(self):
        ah._handle_tool(self.a, "nope", "text")
        self.a.computer_tool.handle_natural.assert_not_called()


class TestComputer(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_success_dict_stdout_truncated(self):
        self.a.computer_tool.handle_natural.return_value = {
            "success": True,
            "stdout": "x" * 1500,
        }
        out = ah._handle_computer(self.a, "open notepad")
        self.assertEqual(len(out), 1000)

    def test_success_dict_data_fallback(self):
        self.a.computer_tool.handle_natural.return_value = {
            "success": True,
            "data": {"k": "v"},
        }
        self.assertEqual(ah._handle_computer(self.a, "run"), "{'k': 'v'}")

    def test_failure_dict_reports_error(self):
        self.a.computer_tool.handle_natural.return_value = {
            "success": False,
            "error": "not found",
        }
        self.assertEqual(ah._handle_computer(self.a, "open zzz"), "Error: not found")

    def test_failure_dict_missing_error_key(self):
        self.a.computer_tool.handle_natural.return_value = {"success": False}
        self.assertEqual(ah._handle_computer(self.a, "x"), "Error: unknown")

    def test_non_dict_result_stringified(self):
        self.a.computer_tool.handle_natural.return_value = 42
        self.assertEqual(ah._handle_computer(self.a, "x"), "42")

    def test_non_dict_result_truncated(self):
        self.a.computer_tool.handle_natural.return_value = "y" * 2000
        self.assertEqual(len(ah._handle_computer(self.a, "x")), 1000)

    def test_tool_exception_returns_stringified_error(self):
        self.a.computer_tool.handle_natural.side_effect = RuntimeError("boom")
        self.assertEqual(ah._handle_computer(self.a, "x"), "Error: boom")

    def test_tool_value_error_returns_stringified_error(self):
        self.a.computer_tool.handle_natural.side_effect = ValueError("bad input")
        self.assertEqual(ah._handle_computer(self.a, "x"), "Error: bad input")

    def test_via_dispatch(self):
        self.a.computer_tool.handle_natural.return_value = {"success": True, "stdout": "ok"}
        self.assertEqual(ah._handle_tool(self.a, "computer", "run ls"), "ok")


class TestToolDelegates(unittest.TestCase):
    """news / security / n8n are straight delegations to the assistant's tools."""

    def setUp(self):
        self.a = make_assistant()

    def test_news_delegates(self):
        self.a.news_tool.handle_natural.return_value = "📰 headlines"
        self.assertEqual(ah._handle_news(self.a, "news"), "📰 headlines")
        self.a.news_tool.handle_natural.assert_called_once_with("news")

    def test_security_delegates(self):
        self.a.security_tool.handle_natural.return_value = "🛡 scan"
        self.assertEqual(ah._handle_security(self.a, "scan"), "🛡 scan")
        self.a.security_tool.handle_natural.assert_called_once_with("scan")

    def test_n8n_delegates(self):
        self.a.n8n_tool.handle_natural.return_value = "⚡ flows"
        self.assertEqual(ah._handle_n8n(self.a, "flows"), "⚡ flows")
        self.a.n8n_tool.handle_natural.assert_called_once_with("flows")

    def test_delegates_via_dispatch(self):
        self.a.news_tool.handle_natural.return_value = "n"
        self.assertEqual(ah._handle_tool(self.a, "news", "x"), "n")


class TestCai(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_audit_routes_to_run_audit(self):
        with mock.patch("orbit.orbit.tools.cai_security.run_audit", return_value="audited") as audit, \
                mock.patch("orbit.orbit.tools.cai_security.run_analysis") as ana:
            out = ah._handle_cai(self.a, "run cai audit")
        audit.assert_called_once_with()
        ana.assert_not_called()
        self.assertEqual(out, "audited")

    def test_threat_routes_to_run_threat_analysis(self):
        with mock.patch("orbit.orbit.tools.cai_security.run_threat_analysis", return_value="threats") as th, \
                mock.patch("orbit.orbit.tools.cai_security.run_analysis") as ana:
            out = ah._handle_cai(self.a, "cai threat report")
        th.assert_called_once_with()
        ana.assert_not_called()
        self.assertEqual(out, "threats")

    def test_default_routes_to_run_analysis(self):
        with mock.patch("orbit.orbit.tools.cai_security.run_analysis", return_value="report") as ana:
            out = ah._handle_cai(self.a, "cai check my system")
        ana.assert_called_once_with("cai check my system")
        self.assertEqual(out, "report")


class TestWorldMonitor(unittest.TestCase):
    def test_opens_worldmonitor_url(self):
        with mock.patch.object(ah.webbrowser, "open") as wb:
            out = ah._handle_worldmonitor(make_assistant(), "open world monitor")
        wb.assert_called_once_with("https://worldmonitor.app")
        self.assertIn("World Monitor", out)


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_clear_all_clears_module_and_history(self):
        self.a.history = [{"user": "hi"}]
        with mock.patch("orbit.orbit.memory.clear") as clear:
            out = ah._handle_memory(self.a, "clear all memories")
        clear.assert_called_once_with()
        self.assertEqual(self.a.history, [])
        self.assertIn("Saari memories clear", out)

    def test_clear_old_with_deletions(self):
        with mock.patch("orbit.orbit.memory.apply_cleanup", return_value=3):
            out = ah._handle_memory(self.a, "cleanup old memories")
        self.assertIn("3 purani memories", out)

    def test_clear_old_without_deletions(self):
        with mock.patch("orbit.orbit.memory.apply_cleanup", return_value=0):
            out = ah._handle_memory(self.a, "clear old")
        self.assertIn("Koi purani memory nahi", out)

    def test_clear_forget_clears_history(self):
        self.a.history = [{"user": "x"}]
        with mock.patch("orbit.orbit.memory.clear") as clear:
            out = ah._handle_memory(self.a, "forget everything")
        clear.assert_called_once_with()
        self.assertEqual(self.a.history, [])
        self.assertIn("Memory cleared", out)

    def test_recall_empty(self):
        with mock.patch("orbit.orbit.memory.get_recent", return_value=[]):
            out = ah._handle_memory(self.a, "recall previous chats")
        self.assertIn("Koi purani baat nahi", out)

    def test_recall_with_history(self):
        with mock.patch(
            "orbit.orbit.memory.get_recent",
            return_value=[{"user": "hi", "assistant": "hello sir"}],
        ):
            out = ah._handle_memory(self.a, "recall history")
        self.assertIn("Purani baatein", out)
        self.assertIn("hello sir", out)

    def test_remember_saves_fact(self):
        with mock.patch("orbit.orbit.memory.save_conversation") as save:
            out = ah._handle_memory(self.a, "remember that I like tea")
        save.assert_called_once_with(
            "remember", "I like tea", context="explicit_memory"
        )
        self.assertIn("Noted: I like tea", out)

    def test_remember_without_fact_falls_through(self):
        with mock.patch("orbit.orbit.memory.save_conversation") as save:
            out = ah._handle_memory(self.a, "remember")
        save.assert_not_called()
        self.assertIn("Commands", out)

    def test_unknown_text_returns_help(self):
        out = ah._handle_memory(self.a, "zzz nothing")
        self.assertIn("Commands", out)


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_search_calls_notes_search(self):
        with mock.patch("orbit.orbit.notes.search", return_value=[{"id": 1}]) as search, \
                mock.patch("orbit.orbit.notes.format_list", return_value="- item") as fmt:
            out = ah._handle_notes(self.a, "search notes budget")
        search.assert_called_once_with("budget")
        fmt.assert_called_once_with([{"id": 1}])
        self.assertIn("Notes search results", out)

    def test_search_empty_query(self):
        out = ah._handle_notes(self.a, "search notes")
        self.assertIn("Kya search karun", out)

    def test_search_no_results(self):
        with mock.patch("orbit.orbit.notes.search", return_value=[]):
            out = ah._handle_notes(self.a, "find notes zzz")
        self.assertIn("koi note nahi mila", out)

    def test_show_all_empty(self):
        with mock.patch("orbit.orbit.notes.get_all", return_value=[]):
            out = ah._handle_notes(self.a, "show notes")
        self.assertIn("Koi notes nahi", out)

    def test_show_all_nonempty(self):
        with mock.patch("orbit.orbit.notes.get_all", return_value=[{"id": 1}]) as ga, \
                mock.patch("orbit.orbit.notes.format_list", return_value="- n") as fmt:
            out = ah._handle_notes(self.a, "show my notes")
        ga.assert_called_once_with()
        fmt.assert_called_once_with([{"id": 1}])
        self.assertIn("Your Notes", out)

    def test_delete_parses_note_id(self):
        with mock.patch("orbit.orbit.notes.delete", return_value=True) as delete:
            out = ah._handle_notes(self.a, "delete note 3")
        delete.assert_called_once_with(3)
        self.assertIn("Note #3 delete", out)

    def test_delete_missing(self):
        with mock.patch("orbit.orbit.notes.delete", return_value=False):
            out = ah._handle_notes(self.a, "delete note 3")
        self.assertIn("nahi mila", out)

    def test_delete_without_id(self):
        out = ah._handle_notes(self.a, "remove note")
        self.assertIn("Note # batao", out)

    def test_pin_toggles(self):
        with mock.patch("orbit.orbit.notes.toggle_pin", return_value={"pinned": True}) as tp:
            out = ah._handle_notes(self.a, "pin note 2")
        tp.assert_called_once_with(2)
        self.assertIn("📌", out)
        self.assertIn("pin kar diya", out)

    def test_unpin(self):
        with mock.patch("orbit.orbit.notes.toggle_pin", return_value={"pinned": False}):
            out = ah._handle_notes(self.a, "unpin note 2")
        self.assertIn("📍", out)
        self.assertIn("unpin kar diya", out)

    def test_pin_missing(self):
        with mock.patch("orbit.orbit.notes.toggle_pin", return_value=None):
            out = ah._handle_notes(self.a, "pin note 9")
        self.assertIn("nahi mila", out)

    def test_pin_without_id(self):
        out = ah._handle_notes(self.a, "pin")
        self.assertIn("Note # batao", out)

    def test_add_strips_keyword_and_saves(self):
        with mock.patch("orbit.orbit.notes.add", return_value={"id": 5, "title": "buy milk"}) as add:
            out = ah._handle_notes(self.a, "note buy milk")
        add.assert_called_once_with("buy milk", "")
        self.assertIn("Note #5 saved", out)

    def test_add_splits_long_text(self):
        long_text = "a" * 100
        with mock.patch("orbit.orbit.notes.add", return_value={"id": 1, "title": "x"}) as add:
            ah._handle_notes(self.a, f"note {long_text}")
        title, body = add.call_args.args
        self.assertEqual(len(title), 80)
        self.assertEqual(body, "a" * 20)

    def test_add_empty_text(self):
        out = ah._handle_notes(self.a, "note")
        self.assertIn("Kya note karun?", out)

    def test_add_via_remember_this(self):
        with mock.patch("orbit.orbit.notes.add", return_value={"id": 6, "title": "milk"}) as add:
            out = ah._handle_notes(self.a, "remember this milk")
        add.assert_called_once_with("milk", "")
        self.assertIn("Note #6 saved", out)


class TestFocus(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()
        focus_timer.stop()

    def tearDown(self):
        focus_timer.stop()

    def test_stop_when_running(self):
        focus_timer.start(5)
        out = ah._handle_focus(self.a, "focus band karo")
        self.assertIn("Focus session stopped", out)
        self.assertIn("Sir", out)
        self.assertFalse(focus_timer.status().get("running"))

    def test_stop_when_idle_still_reports_stopped(self):
        out = ah._handle_focus(self.a, "focus stop")
        self.assertIn("Focus session stopped", out)

    def test_status_query(self):
        with mock.patch.object(focus_timer, "format_status", return_value="25:00 left") as fs:
            out = ah._handle_focus(self.a, "focus status")
        fs.assert_called_once_with(focus_timer.status())
        self.assertEqual(out, "25:00 left")

    def test_time_query(self):
        with mock.patch.object(focus_timer, "format_status", return_value="10:00"):
            out = ah._handle_focus(self.a, "how much focus time left")
        self.assertEqual(out, "10:00")

    def test_today_stats(self):
        with mock.patch.object(
            focus_timer, "today_stats",
            return_value={"focus_minutes": 50, "sessions": 2, "breaks": 1},
        ):
            out = ah._handle_focus(self.a, "focus today")
        self.assertIn("50 min", out)
        self.assertIn("2 sessions", out)
        self.assertIn("1 breaks", out)

    def test_week_stats(self):
        with mock.patch.object(
            focus_timer, "week_stats",
            return_value={"Mon": {"focus_minutes": 30}, "Tue": {"focus_minutes": 20}},
        ):
            out = ah._handle_focus(self.a, "focus week")
        self.assertIn("50 min across 2 days", out)

    def test_running_shows_status(self):
        focus_timer.start(5)
        with mock.patch.object(focus_timer, "format_status", return_value="running!"):
            out = ah._handle_focus(self.a, "focus")
        self.assertEqual(out, "running!")
        focus_timer.stop()

    def test_start_with_minutes(self):
        with mock.patch.object(focus_timer, "start") as start, \
                mock.patch.object(focus_timer, "set_callbacks") as cb, \
                mock.patch.object(focus_timer, "status", return_value={"running": False}):
            out = ah._handle_focus(self.a, "focus 30")
        cb.assert_called_once_with()
        start.assert_called_once_with(30)
        self.assertIn("30 minutes", out)
        self.assertIn("Focus mode ON", out)

    def test_start_hours_converts_to_minutes(self):
        # BUG FIXED: the unit was parsed but ignored — "focus 2 hours" started
        # a 2-MINUTE session.
        with mock.patch.object(focus_timer, "start") as start, \
                mock.patch.object(focus_timer, "set_callbacks"), \
                mock.patch.object(focus_timer, "status", return_value={"running": False}):
            ah._handle_focus(self.a, "focus 2 hours")
        start.assert_called_once_with(120)

    def test_start_hr_unit(self):
        with mock.patch.object(focus_timer, "start") as start, \
                mock.patch.object(focus_timer, "set_callbacks"), \
                mock.patch.object(focus_timer, "status", return_value={"running": False}):
            ah._handle_focus(self.a, "focus 1 hr")
        start.assert_called_once_with(60)

    def test_start_without_duration_defaults_to_25(self):
        with mock.patch.object(focus_timer, "start") as start, \
                mock.patch.object(focus_timer, "set_callbacks"), \
                mock.patch.object(focus_timer, "status", return_value={"running": False}):
            ah._handle_focus(self.a, "focus")
        start.assert_called_once_with(25)

    def test_start_integration_runs_real_timer(self):
        # Integration: the fixed hour conversion must produce a running timer.
        out = ah._handle_focus(self.a, "focus 1 hours")
        self.assertIn("Focus mode ON", out)
        self.assertIn("60 minutes", out)
        self.assertTrue(focus_timer.status().get("running"))
        focus_timer.stop()


class TestClipboard(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_history_empty(self):
        with mock.patch.object(smart_actions, "get_history", return_value=[]):
            out = ah._handle_clipboard(self.a, "show clipboard history")
        self.assertIn("khali hai", out)

    def test_history_nonempty(self):
        with mock.patch.object(
            smart_actions, "get_history", return_value=[{"text": "abc"}]
        ) as gh, mock.patch.object(
            smart_actions, "format_history", return_value="hist"
        ) as fmt:
            out = ah._handle_clipboard(self.a, "clipboard history")
        gh.assert_called_once_with(10)
        self.assertEqual(out, "hist")

    def test_clear_history(self):
        with mock.patch.object(smart_actions, "clear_history") as clear:
            out = ah._handle_clipboard(self.a, "clear clipboard")
        clear.assert_called_once_with()
        self.assertIn("clear kar di", out)

    def test_last_with_smart_actions(self):
        with mock.patch.object(
            smart_actions, "get_history", return_value=[{"text": "https://x.com"}]
        ) as gh, mock.patch.object(
            smart_actions,
            "analyze",
            return_value={
                "has_actions": True,
                "actions": [{"label": "Open URL"}],
            },
        ):
            out = ah._handle_clipboard(self.a, "last copied")
        gh.assert_called_once_with(1)
        self.assertIn("Last copy", out)
        self.assertIn("Open URL", out)

    def test_last_without_actions(self):
        with mock.patch.object(
            smart_actions, "get_history", return_value=[{"text": "plain"}]
        ), mock.patch.object(
            smart_actions, "analyze", return_value={"has_actions": False, "actions": []}
        ):
            out = ah._handle_clipboard(self.a, "latest copy")
        self.assertIn("Last copy", out)
        self.assertNotIn("Smart Actions", out)

    def test_last_when_empty(self):
        with mock.patch.object(smart_actions, "get_history", return_value=[]):
            out = ah._handle_clipboard(self.a, "last copy")
        self.assertIn("Clipboard khali hai", out)

    def test_default_shows_five(self):
        with mock.patch.object(
            smart_actions, "get_history", return_value=[{"text": "a"}]
        ) as gh, mock.patch.object(
            smart_actions, "format_history", return_value="five"
        ):
            out = ah._handle_clipboard(self.a, "clipboard")
        gh.assert_called_once_with(5)
        self.assertEqual(out, "five")

    def test_default_empty(self):
        with mock.patch.object(smart_actions, "get_history", return_value=[]):
            out = ah._handle_clipboard(self.a, "clipboard")
        self.assertIn("Kuch copy karo", out)


class TestBookmark(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_show_all_empty(self):
        with mock.patch("orbit.orbit.bookmarks.get_all", return_value=[]):
            out = ah._handle_bookmark(self.a, "show bookmarks")
        self.assertIn("Koi bookmarks nahi", out)

    def test_show_all_nonempty(self):
        with mock.patch(
            "orbit.orbit.bookmarks.get_all", return_value=[{"id": 1}]
        ) as ga, mock.patch(
            "orbit.orbit.bookmarks.format_list", return_value="bm-list"
        ) as fmt:
            out = ah._handle_bookmark(self.a, "show my bookmarks")
        ga.assert_called_once_with()
        fmt.assert_called_once_with([{"id": 1}])
        self.assertEqual(out, "bm-list")

    def test_search_hit(self):
        with mock.patch(
            "orbit.orbit.bookmarks.search", return_value=[{"id": 2}]
        ) as search, mock.patch(
            "orbit.orbit.bookmarks.format_search", return_value="found"
        ) as fmt:
            out = ah._handle_bookmark(self.a, "search bookmark react")
        search.assert_called_once_with("react")
        self.assertEqual(out, "found")

    def test_search_miss(self):
        with mock.patch("orbit.orbit.bookmarks.search", return_value=[]):
            out = ah._handle_bookmark(self.a, "search bookmark zzz")
        self.assertIn("koi bookmark nahi mila", out)

    def test_search_empty_query(self):
        out = ah._handle_bookmark(self.a, "search bookmark")
        self.assertIn("Kya search karun?", out)

    def test_delete_parses_id(self):
        with mock.patch("orbit.orbit.bookmarks.delete", return_value=True) as delete:
            out = ah._handle_bookmark(self.a, "delete bookmark 4")
        delete.assert_called_once_with(4)
        self.assertIn("Bookmark #4 delete", out)

    def test_delete_missing(self):
        with mock.patch("orbit.orbit.bookmarks.delete", return_value=False):
            out = ah._handle_bookmark(self.a, "delete bookmark 4")
        self.assertIn("nahi mila", out)

    def test_delete_without_id(self):
        out = ah._handle_bookmark(self.a, "remove bookmark")
        self.assertIn("ID batao", out)

    def test_add_from_text_url(self):
        with mock.patch(
            "orbit.orbit.bookmarks.add",
            return_value={"id": 7, "title": "Example", "url": "https://example.com"},
        ) as add:
            out = ah._handle_bookmark(self.a, "bookmark https://example.com react")
        add.assert_called_once()
        args, kwargs = add.call_args
        self.assertEqual(args[0], "https://example.com")
        self.assertIn("tags", kwargs)
        self.assertIn("Bookmark #7 saved", out)

    def test_add_from_clipboard(self):
        fake_pyperclip = types.ModuleType("pyperclip")
        fake_pyperclip.paste = mock.Mock(return_value="https://clip.example")
        with mock.patch.dict(sys.modules, {"pyperclip": fake_pyperclip}), \
                mock.patch(
                    "orbit.orbit.bookmarks.add",
                    return_value={"id": 8, "title": "clip"},
                ) as add:
            out = ah._handle_bookmark(self.a, "bookmark this")
        add.assert_called_once_with("https://clip.example", title="bookmark this")
        self.assertIn("saved from clipboard", out)

    def test_clipboard_exception_is_logged_not_raised(self):
        fake_pyperclip = types.ModuleType("pyperclip")
        fake_pyperclip.paste = mock.Mock(side_effect=RuntimeError("no clipboard"))
        with mock.patch.dict(sys.modules, {"pyperclip": fake_pyperclip}):
            out = ah._handle_bookmark(self.a, "bookmark this")
        self.assertIn("Kya bookmark karun?", out)

    def test_no_url_no_clipboard(self):
        with mock.patch.dict(sys.modules, {"pyperclip": None}):
            # pyperclip import fails -> except path -> help text.
            out = ah._handle_bookmark(self.a, "bookmark something")
        self.assertIn("URL batao", out)


class TestCalculate(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_ok_result_bold(self):
        with mock.patch.object(
            calculator, "calculate",
            return_value={"type": "number", "display": "42"},
        ):
            out = ah._handle_calculate(self.a, "6 * 7")
        self.assertEqual(out, "🧮 **42**")

    def test_error_result_not_bold(self):
        with mock.patch.object(
            calculator, "calculate",
            return_value={"type": "error", "display": "samajh nahi aaya"},
        ):
            out = ah._handle_calculate(self.a, "zzz")
        self.assertEqual(out, "🧮 samajh nahi aaya")
        self.assertNotIn("**", out)


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_quoted_query_wins(self):
        with mock.patch.object(conv_search, "search", return_value=[]) as search, \
                mock.patch.object(conv_search, "format_results", return_value="res") as fmt:
            out = ah._handle_search(self.a, 'search chat "python code"')
        search.assert_called_once_with("python code")
        self.assertEqual(out, "res")

    def test_plain_query(self):
        with mock.patch.object(conv_search, "search", return_value=[]) as search, \
                mock.patch.object(conv_search, "format_results", return_value="res"):
            out = ah._handle_search(self.a, "search karo flask routes")
        search.assert_called_once_with("flask routes")
        self.assertEqual(out, "res")

    def test_empty_query_shows_stats(self):
        with mock.patch.object(conv_search, "stats", return_value={"total": 99}), \
                mock.patch.object(conv_search, "search") as search:
            out = ah._handle_search(self.a, "search")
        search.assert_not_called()
        self.assertIn("Total 99 messages", out)

    def test_too_short_query_shows_stats(self):
        with mock.patch.object(conv_search, "stats", return_value={"total": 5}):
            out = ah._handle_search(self.a, "dhund")
        self.assertIn("Total 5 messages", out)


class TestHabit(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_show_all(self):
        with mock.patch.object(habits, "format_list", return_value="habits"):
            out = ah._handle_habit(self.a, "show habits")
        self.assertEqual(out, "habits")

    def test_show_today(self):
        with mock.patch.object(habits, "format_today", return_value="today"):
            out = ah._handle_habit(self.a, "show habits today")
        self.assertEqual(out, "today")

    def test_add_habit(self):
        with mock.patch.object(
            habits, "add", return_value={"id": 3, "name": "Exercise"}
        ) as add:
            out = ah._handle_habit(self.a, "add habit exercise")
        add.assert_called_once_with("Exercise", "daily")
        self.assertIn("#3 Exercise", out)
        self.assertIn("[daily]", out)

    def test_add_weekly_habit(self):
        with mock.patch.object(
            habits, "add", return_value={"id": 4, "name": "Run"}
        ) as add:
            ah._handle_habit(self.a, "add habit run weekly")
        add.assert_called_once_with("Run", "weekly")

    def test_add_weekend_habit(self):
        with mock.patch.object(
            habits, "add", return_value={"id": 5, "name": "Gym"}
        ) as add:
            ah._handle_habit(self.a, "add habit gym weekend")
        add.assert_called_once_with("Gym", "weekend")

    def test_add_without_name(self):
        out = ah._handle_habit(self.a, "add habit")
        self.assertIn("Habit ka naam batao", out)

    def test_delete_habit(self):
        with mock.patch.object(habits, "delete", return_value=True) as delete:
            out = ah._handle_habit(self.a, "delete habit 7")
        delete.assert_called_once_with(7)
        self.assertIn("Habit #7 delete", out)

    def test_delete_missing(self):
        with mock.patch.object(habits, "delete", return_value=False):
            out = ah._handle_habit(self.a, "delete habit 7")
        self.assertIn("nahi mila", out)

    def test_delete_without_id(self):
        out = ah._handle_habit(self.a, "delete habit")
        self.assertIn("ID batao", out)

    def test_log_habit_with_streak(self):
        with mock.patch.object(habits, "log", return_value=True) as log, \
                mock.patch.object(
                    habits, "get_all", return_value=[{"id": 3, "streak": 4}]
                ):
            out = ah._handle_habit(self.a, "log habit 3")
        log.assert_called_once_with(3)
        self.assertIn("Habit #3 done", out)
        self.assertIn("🔥4d streak", out)

    def test_log_habit_already_done(self):
        with mock.patch.object(habits, "log", return_value=False):
            out = ah._handle_habit(self.a, "mark habit 3")
        self.assertIn("already marked today", out)

    def test_log_without_id(self):
        out = ah._handle_habit(self.a, "log habit")
        self.assertIn("ID batao", out)

    def test_streak_show(self):
        # NOTE: "show ..." hits the show branch first, so use a streak-only ask.
        with mock.patch.object(
            habits, "today_status",
            return_value=[{"id": 1, "name": "Run", "streak": 3, "best_streak": 9}],
        ):
            out = ah._handle_habit(self.a, "kitne streak hain")
        self.assertIn("Habit Streaks", out)
        self.assertIn("3d streak", out)
        self.assertIn("best: 9d", out)

    def test_streak_show_empty(self):
        with mock.patch.object(habits, "today_status", return_value=[]):
            out = ah._handle_habit(self.a, "kitne streak")
        self.assertIn("Koi habits nahi", out)

    def test_default_logs_by_number(self):
        with mock.patch.object(habits, "log", return_value=True):
            out = ah._handle_habit(self.a, "habit 8")
        self.assertIn("Habit #8 done", out)

    def test_default_falls_back_to_today(self):
        with mock.patch.object(habits, "log") as log, \
                mock.patch.object(habits, "format_today", return_value="today-list"):
            out = ah._handle_habit(self.a, "habit")
        log.assert_not_called()
        self.assertEqual(out, "today-list")


class TestLists(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_generation_ask_falls_through_to_llm(self):
        # E4 contract: content-generation asks return None (fall through).
        out = ah._handle_list(self.a, "Give me a list of 3 programming languages")
        self.assertIsNone(out)

    def test_generation_ask_with_ops_dispatches(self):
        with mock.patch.object(
            lists, "add_items_from_text", return_value=[{"text": "milk"}]
        ) as add:
            out = ah._handle_list(self.a, "add milk to my list of chores")
        self.assertIsNotNone(out)
        add.assert_called_once()

    def test_create_list(self):
        with mock.patch.object(lists, "add_item") as add:
            out = ah._handle_list(self.a, "create shopping list")
        add.assert_called_once_with("shopping", "(list created)")
        self.assertIn("create kar di", out)

    def test_show_all_lists(self):
        with mock.patch.object(
            lists, "format_all_lists", return_value="all-lists"
        ) as fmt:
            out = ah._handle_list(self.a, "show all lists")
        fmt.assert_called_once_with()
        self.assertEqual(out, "all-lists")

    def test_show_specific_list(self):
        with mock.patch.object(
            lists, "format_list", return_value="milk"
        ) as fmt:
            out = ah._handle_list(self.a, "show grocery list")
        fmt.assert_called_once_with("grocery")
        self.assertEqual(out, "milk")

    def test_show_defaults_to_shopping(self):
        with mock.patch.object(
            lists, "format_list", return_value="x"
        ) as fmt:
            ah._handle_list(self.a, "show")
        fmt.assert_called_once_with("shopping")

    def test_check_item_by_id(self):
        with mock.patch.object(lists, "check_item", return_value=True) as check:
            out = ah._handle_list(self.a, "check item 3")
        check.assert_called_once_with("shopping", 3)
        self.assertIn("checked off shopping list", out)

    def test_check_item_missing(self):
        with mock.patch.object(lists, "check_item", return_value=False):
            out = ah._handle_list(self.a, "check item 3")
        self.assertIn("nahi mila", out)

    def test_check_item_no_id(self):
        out = ah._handle_list(self.a, "check item")
        self.assertIn("Kaunsa item", out)

    def test_uncheck_item_calls_check_item_false(self):
        # BUG FIXED: "uncheck" contains "check", so the old order routed this
        # into check_item(checked=True) and toggled the item the WRONG way.
        with mock.patch.object(lists, "check_item", return_value=True) as check:
            out = ah._handle_list(self.a, "uncheck item 3")
        check.assert_called_once_with("shopping", 3, False)
        self.assertIn("unchecked", out)

    def test_undone_also_unchecks(self):
        with mock.patch.object(lists, "check_item", return_value=True) as check:
            out = ah._handle_list(self.a, "undone item 3")
        check.assert_called_once_with("shopping", 3, False)
        self.assertIn("unchecked", out)

    def test_uncheck_without_id(self):
        out = ah._handle_list(self.a, "uncheck item")
        self.assertIn("Kaunsa item", out)

    def test_remove_item(self):
        with mock.patch.object(lists, "remove_item", return_value=True) as remove:
            out = ah._handle_list(self.a, "remove item 2")
        remove.assert_called_once_with("shopping", 2)
        self.assertIn("removed from shopping", out)

    def test_remove_item_missing(self):
        with mock.patch.object(lists, "remove_item", return_value=False):
            out = ah._handle_list(self.a, "remove item 2")
        self.assertIn("nahi mila", out)

    def test_remove_item_no_id(self):
        out = ah._handle_list(self.a, "remove item")
        self.assertIn("ID batao", out)

    def test_delete_list_success(self):
        with mock.patch.object(lists, "delete_list", return_value=True) as delete:
            out = ah._handle_list(self.a, "delete grocery list")
        delete.assert_called_once_with("grocery")
        self.assertIn("delete kar di", out)

    def test_delete_list_missing_reports_failure(self):
        # BUG FIXED: delete_list's False return used to be ignored, so deleting
        # a nonexistent list still claimed success.
        with mock.patch.object(lists, "delete_list", return_value=False) as delete:
            out = ah._handle_list(self.a, "delete zzz list")
        delete.assert_called_once_with("shopping")  # zzz is not a known name
        self.assertIn("nahi mili", out)

    def test_add_via_fallback_adds_items_from_text(self):
        # "add ..." has no dedicated branch — it flows through the generic
        # fallback that strips keywords and calls add_items_from_text.
        with mock.patch.object(
            lists, "add_items_from_text", return_value=[{"text": "milk"}]
        ) as add:
            out = ah._handle_list(self.a, "add milk to shopping list")
        add.assert_called_once_with("shopping", "milk to")
        self.assertIn("1 item(s)", out)

    def test_fallback_add_multiple_items(self):
        with mock.patch.object(
            lists, "add_items_from_text",
            return_value=[{"text": "milk"}, {"text": "eggs"}],
        ) as add:
            out = ah._handle_list(self.a, "daal milk and eggs in grocery list")
        add.assert_called_once_with("grocery", "milk and eggs in")
        self.assertIn("2 item(s)", out)

    def test_fallback_without_text_shows_list(self):
        with mock.patch.object(
            lists, "format_list", return_value="empty"
        ) as fmt:
            out = ah._handle_list(self.a, "list")
        fmt.assert_called_once_with("shopping")
        self.assertIn("Kya add karun?", out)


class TestCountdown(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_show_events(self):
        with mock.patch("orbit.orbit.countdowns.format_events", return_value="events"):
            out = ah._handle_countdown(self.a, "show countdown events")
        self.assertEqual(out, "events")

    def test_delete_event(self):
        with mock.patch("orbit.orbit.countdowns.delete", return_value=True) as delete:
            out = ah._handle_countdown(self.a, "delete event 2")
        delete.assert_called_once_with(2)
        self.assertIn("Event #2 delete", out)

    def test_delete_missing(self):
        with mock.patch("orbit.orbit.countdowns.delete", return_value=False):
            out = ah._handle_countdown(self.a, "delete event 2")
        self.assertIn("nahi mila", out)

    def test_delete_without_id(self):
        out = ah._handle_countdown(self.a, "remove event")
        self.assertIn("ID batao", out)

    def test_search_hit(self):
        with mock.patch("orbit.orbit.countdowns.search", return_value=[{"id": 1}]) as search, \
                mock.patch("orbit.orbit.countdowns.format_events", return_value="hits"):
            out = ah._handle_countdown(self.a, "search event birthday")
        search.assert_called_once_with("birthday")
        self.assertEqual(out, "hits")

    def test_search_miss(self):
        with mock.patch("orbit.orbit.countdowns.search", return_value=[]):
            out = ah._handle_countdown(self.a, "find event zzz")
        self.assertIn("koi event nahi mila", out)

    def test_fallback_parse_and_add(self):
        with mock.patch(
            "orbit.orbit.countdowns.parse_and_add", return_value="added"
        ) as parse:
            out = ah._handle_countdown(self.a, "countdown to diwali in 5 days")
        parse.assert_called_once_with("countdown to diwali in 5 days")
        self.assertEqual(out, "added")


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_show_all(self):
        with mock.patch("orbit.orbit.journal.get_all", return_value=[{"id": 1}]) as ga, \
                mock.patch("orbit.orbit.journal.format_entries", return_value="all") as fmt:
            out = ah._handle_journal(self.a, "show journal")
        ga.assert_called_once_with()
        fmt.assert_called_once_with([{"id": 1}], "All Entries")
        self.assertEqual(out, "all")

    def test_show_today(self):
        with mock.patch("orbit.orbit.journal.get_today", return_value=[]) as gt, \
                mock.patch("orbit.orbit.journal.format_entries", return_value="today"):
            out = ah._handle_journal(self.a, "journal aaj")
        gt.assert_called_once_with()
        fmt_args = out
        self.assertEqual(fmt_args, "today")

    def test_search(self):
        with mock.patch("orbit.orbit.journal.search", return_value=[{"id": 2}]) as search, \
                mock.patch("orbit.orbit.journal.format_entries", return_value="hits") as fmt:
            out = ah._handle_journal(self.a, "search journal meeting")
        search.assert_called_once_with("meeting")
        fmt.assert_called_once_with([{"id": 2}], "'meeting' results")
        self.assertEqual(out, "hits")

    def test_search_empty_query(self):
        out = ah._handle_journal(self.a, "find journal")
        self.assertIn("Kya search karun?", out)

    def test_stats(self):
        with mock.patch(
            "orbit.orbit.journal.stats",
            return_value={"total": 10, "days": 4, "streak": 2, "avg_words": 30},
        ):
            out = ah._handle_journal(self.a, "journal stats")
        self.assertIn("Total entries: 10", out)
        self.assertIn("Active days: 4", out)
        self.assertIn("Current streak: 2d", out)
        self.assertIn("Avg words/entry: 30", out)

    def test_delete_entry(self):
        with mock.patch("orbit.orbit.journal.delete", return_value=True) as delete:
            out = ah._handle_journal(self.a, "delete journal entry 5")
        delete.assert_called_once_with(5)
        self.assertIn("entry #5 delete", out)

    def test_delete_missing(self):
        with mock.patch("orbit.orbit.journal.delete", return_value=False):
            out = ah._handle_journal(self.a, "delete journal 5")
        self.assertIn("nahi mila", out)

    def test_delete_without_id(self):
        out = ah._handle_journal(self.a, "remove journal entry")
        self.assertIn("ID batao", out)

    def test_add_entry(self):
        # NOTE: "aaj" would hit the today branch first — use a plain entry.
        with mock.patch(
            "orbit.orbit.journal.add_entry",
            return_value={"id": 9, "text": "bahut kaam kiya"},
        ) as add:
            out = ah._handle_journal(self.a, "journal bahut kaam kiya")
        add.assert_called_once_with("bahut kaam kiya")
        self.assertIn("Journal entry #9 add", out)

    def test_add_entry_empty_falls_to_help(self):
        out = ah._handle_journal(self.a, "journal")
        self.assertIn("Kya likhna hai?", out)


class TestSimpleWrappers(unittest.TestCase):
    """Thin handlers: module.parse_* (text)['result'] is passed straight back."""

    def _check(self, handler, module_name, parse_fn, text):
        a = make_assistant()
        sentinel = {"result": "WRAPPED"}
        with mock.patch(f"{module_name}.{parse_fn}", return_value=sentinel) as parse:
            out = handler(a, text)
        parse.assert_called_once_with(text)
        self.assertEqual(out, "WRAPPED")

    def test_random(self):
        a = make_assistant()
        with mock.patch("orbit.orbit.random_utils.parse_text", return_value={"n": 3}) as parse, \
                mock.patch("orbit.orbit.random_utils.format_result", return_value="got 3") as fmt:
            out = ah._handle_random(a, "roll dice")
        parse.assert_called_once_with("roll dice")
        fmt.assert_called_once_with({"n": 3})
        self.assertEqual(out, "🎲 got 3")

    def test_text(self):
        self._check(ah._handle_text, "orbit.orbit.text_utils", "parse_and_handle", "reverse hello")

    def test_password(self):
        a = make_assistant()
        with mock.patch("orbit.orbit.password_gen.parse_text", return_value={"n": 8}) as parse, \
                mock.patch("orbit.orbit.password_gen.format_result", return_value="Abc123") as fmt:
            out = ah._handle_password(a, "password 16")
        parse.assert_called_once_with("password 16")
        fmt.assert_called_once_with({"n": 8})
        self.assertEqual(out, "🔑 Abc123")

    def test_json(self):
        self._check(ah._handle_json, "orbit.orbit.json_tools", "parse_and_handle", "format json")

    def test_baseconv(self):
        self._check(ah._handle_baseconv, "orbit.orbit.baseconv", "parse_and_handle",
                    "convert 10 to binary")

    def test_emoji(self):
        self._check(ah._handle_emoji, "orbit.orbit.emoji", "parse_text", "emoji happy")

    def test_color(self):
        self._check(ah._handle_color, "orbit.orbit.colorconv", "parse_and_handle", "color red")

    def test_music(self):
        self._check(ah._handle_music, "orbit.orbit.music_ctrl", "parse_text", "play song")

    def test_files(self):
        self._check(ah._handle_files, "orbit.orbit.file_tools", "parse_text", "open file x")

    def test_timer(self):
        self._check(ah._handle_timer, "orbit.orbit.timer", "parse_text", "timer 5")

    def test_decision(self):
        self._check(ah._handle_decision, "orbit.orbit.decisions", "parse_text", "decide yes or no")

    def test_websearch(self):
        self._check(ah._handle_websearch, "orbit.orbit.websearch", "parse_text", "search python")

    def test_share(self):
        self._check(ah._handle_share, "orbit.orbit.share", "parse_text", "share https://x.com")

    def test_quote(self):
        self._check(ah._handle_quote, "orbit.orbit.quotes", "parse_text", "quote of the day")


class TestStopwatch(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_start(self):
        with mock.patch("orbit.orbit.stopwatch.start") as start:
            out = ah._handle_stopwatch(self.a, "start stopwatch")
        start.assert_called_once_with()
        self.assertIn("start!", out)

    def test_lap(self):
        with mock.patch("orbit.orbit.stopwatch.lap", return_value=1.5) as lap, \
                mock.patch("orbit.orbit.stopwatch.status", return_value={"laps": 2}), \
                mock.patch("orbit.orbit.stopwatch.format_time", return_value="0:01.5"):
            out = ah._handle_stopwatch(self.a, "lap")
        lap.assert_called_once_with()
        self.assertIn("Lap #2", out)

    def test_stop(self):
        with mock.patch("orbit.orbit.stopwatch.stop", return_value=3.0) as stop, \
                mock.patch("orbit.orbit.stopwatch.format_time", return_value="0:03.0"):
            out = ah._handle_stopwatch(self.a, "stop stopwatch")
        stop.assert_called_once_with()
        self.assertIn("stopped", out)

    def test_reset(self):
        with mock.patch("orbit.orbit.stopwatch.reset") as reset:
            out = ah._handle_stopwatch(self.a, "reset stopwatch")
        reset.assert_called_once_with()
        self.assertIn("reset", out)

    def test_status_fallback(self):
        with mock.patch("orbit.orbit.stopwatch.format_status", return_value="idle"):
            out = ah._handle_stopwatch(self.a, "stopwatch")
        self.assertEqual(out, "idle")


class TestSysinfo(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_battery(self):
        with mock.patch.object(sysinfo, "format_battery", return_value="🔋 90%"):
            out = ah._handle_sysinfo(self.a, "battery level")
        self.assertEqual(out, "🔋 90%")

    def test_battery_charge_returns_none(self):
        with mock.patch.object(sysinfo, "format_battery") as fb:
            out = ah._handle_sysinfo(self.a, "battery charge status")
        fb.assert_not_called()
        self.assertIsNone(out)

    def test_cpu(self):
        with mock.patch.object(sysinfo, "format_cpu", return_value="cpu 10%"):
            out = ah._handle_sysinfo(self.a, "cpu usage")
        self.assertEqual(out, "cpu 10%")

    def test_default_info(self):
        with mock.patch.object(sysinfo, "format_info", return_value="sysinfo"):
            out = ah._handle_sysinfo(self.a, "system info")
        self.assertEqual(out, "sysinfo")


class TestNetworkAndBriefing(unittest.TestCase):
    def test_network_format_info(self):
        with mock.patch("orbit.orbit.network.format_info", return_value="net") as fi:
            out = ah._handle_network(make_assistant(), "network")
        fi.assert_called_once_with()
        self.assertEqual(out, "net")

    def test_briefing_format_briefing(self):
        with mock.patch.object(briefing, "format_briefing", return_value="brief") as fb:
            out = ah._handle_briefing(make_assistant(), "morning briefing")
        fb.assert_called_once_with()
        self.assertEqual(out, "brief")


class TestFlashcard(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_add_card(self):
        with mock.patch.object(
            flashcards, "parse_add_text",
            return_value={"id": 1, "deck": "general", "front": "Q?", "back": "A"},
        ) as parse:
            out = ah._handle_flashcard(self.a, "add card Q? / A")
        parse.assert_called_once_with("add card Q? / A")
        self.assertIn("Card #1 added", out)

    def test_add_card_bad_format(self):
        with mock.patch.object(flashcards, "parse_add_text", return_value=None):
            out = ah._handle_flashcard(self.a, "add card nonsense")
        self.assertIn("Format:", out)

    def test_show_deck(self):
        with mock.patch.object(
            flashcards, "_KNOWN_DECKS", ["python"]
        ), mock.patch.object(
            flashcards, "get_all", return_value=[{"id": 1}]
        ) as ga, mock.patch.object(
            flashcards, "format_cards", return_value="cards"
        ) as fmt:
            out = ah._handle_flashcard(self.a, "show python deck")
        ga.assert_called_once_with("python")
        fmt.assert_called_once_with([{"id": 1}], "Deck: python")
        self.assertEqual(out, "cards")

    def test_show_defaults_to_general(self):
        with mock.patch.object(
            flashcards, "_KNOWN_DECKS", ["python"]
        ), mock.patch.object(
            flashcards, "get_all", return_value=[]
        ) as ga, mock.patch.object(flashcards, "format_cards", return_value="c"):
            ah._handle_flashcard(self.a, "show cards")
        ga.assert_called_once_with("general")

    def test_due_cards(self):
        with mock.patch.object(
            flashcards, "_KNOWN_DECKS", ["python"]
        ), mock.patch.object(
            flashcards, "get_due", return_value=[{"id": 2}]
        ) as gd, mock.patch.object(flashcards, "format_cards", return_value="due"):
            out = ah._handle_flashcard(self.a, "study python due cards")
        gd.assert_called_once_with("python")
        self.assertEqual(out, "due")

    def test_stats(self):
        with mock.patch.object(
            flashcards, "get_stats",
            return_value={"total": 9, "due": 3, "mastered": 4, "avg_correct": 80},
        ):
            out = ah._handle_flashcard(self.a, "flashcard stats")
        self.assertIn("9 cards", out)
        self.assertIn("3 due", out)
        self.assertIn("4 mastered", out)

    def test_delete_card(self):
        with mock.patch.object(flashcards, "delete", return_value=True) as delete:
            out = ah._handle_flashcard(self.a, "delete card 5")
        delete.assert_called_once_with(5)
        self.assertIn("Card #5 delete", out)

    def test_delete_missing(self):
        with mock.patch.object(flashcards, "delete", return_value=False):
            out = ah._handle_flashcard(self.a, "remove card 5")
        self.assertIn("nahi mila", out)

    def test_delete_without_id(self):
        out = ah._handle_flashcard(self.a, "delete card")
        self.assertIn("ID batao", out)

    def test_study_session_with_cards(self):
        with mock.patch.object(
            flashcards, "_KNOWN_DECKS", ["python"]
        ), mock.patch.object(
            flashcards, "study_session", return_value=[{"id": 3}]
        ) as study, mock.patch.object(
            flashcards, "format_cards", return_value="session"
        ):
            out = ah._handle_flashcard(self.a, "flashcard")
        study.assert_called_once_with("")
        self.assertEqual(out, "session")

    def test_study_session_empty(self):
        with mock.patch.object(flashcards, "_KNOWN_DECKS", []), \
                mock.patch.object(flashcards, "study_session", return_value=[]):
            out = ah._handle_flashcard(self.a, "flashcard")
        self.assertIn("Sarre cards revise", out)

    def test_study_session_specific_deck(self):
        # covers the fallback deck-detection loop (line ~643)
        with mock.patch.object(
            flashcards, "_KNOWN_DECKS", ["python", "math"]
        ), mock.patch.object(
            flashcards, "study_session", return_value=[{"id": 4}]
        ) as study, mock.patch.object(flashcards, "format_cards", return_value="s"):
            out = ah._handle_flashcard(self.a, "flashcard python")
        study.assert_called_once_with("python")
        self.assertEqual(out, "s")


class TestExpense(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_today(self):
        with mock.patch.object(expenses, "format_today", return_value="today-spent"):
            out = ah._handle_expense(self.a, "expense today")
        self.assertEqual(out, "today-spent")

    def test_month(self):
        with mock.patch.object(expenses, "format_month", return_value="month-spent") as fm:
            out = ah._handle_expense(self.a, "expenses this month")
        self.assertEqual(out, "month-spent")
        self.assertEqual(fm.call_count, 1)
        year, month = fm.call_args.args
        self.assertIsInstance(year, int)
        self.assertIsInstance(month, int)

    def test_delete_expense(self):
        with mock.patch.object(expenses, "delete", return_value=True) as delete:
            out = ah._handle_expense(self.a, "delete expense 3")
        delete.assert_called_once_with(3)
        self.assertIn("Expense #3 delete", out)

    def test_delete_missing(self):
        with mock.patch.object(expenses, "delete", return_value=False):
            out = ah._handle_expense(self.a, "delete expense 3")
        self.assertIn("nahi mila", out)

    def test_delete_without_id(self):
        out = ah._handle_expense(self.a, "remove expense")
        self.assertIn("ID batao", out)

    def test_fallback_parse_and_add(self):
        with mock.patch.object(
            expenses, "parse_and_add", return_value="added"
        ) as parse:
            out = ah._handle_expense(self.a, "spent 200 on lunch")
        parse.assert_called_once_with("spent 200 on lunch")
        self.assertEqual(out, "added")


class TestScreen(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_capture_failure(self):
        with mock.patch.object(screen, "capture_screen", return_value=None):
            out = ah._handle_screen(self.a, "what's on screen")
        self.assertIn("Screenshot nahi le paya", out)
        self.a._emit_status.assert_called_once_with("thinking", "Capturing screen...")

    def test_analysis_dict(self):
        with mock.patch.object(screen, "capture_screen", return_value="C:\\s.png") as cap, \
                mock.patch.object(
                    screen, "analyze_screenshot", return_value={"text": "a window"}
                ) as ana, mock.patch.object(screen, "cleanup") as cleanup:
            out = ah._handle_screen(self.a, "describe screen")
        cap.assert_called_once_with()
        ana.assert_called_once_with("C:\\s.png", "describe screen")
        cleanup.assert_called_once_with("C:\\s.png")
        self.assertEqual(out, "a window")

    def test_analysis_string(self):
        with mock.patch.object(screen, "capture_screen", return_value="p.png"), \
                mock.patch.object(screen, "analyze_screenshot", return_value="plain text"), \
                mock.patch.object(screen, "cleanup"):
            out = ah._handle_screen(self.a, "read screen")
        self.assertEqual(out, "plain text")

    def test_analysis_dict_without_text_key(self):
        with mock.patch.object(screen, "capture_screen", return_value="p.png"), \
                mock.patch.object(screen, "analyze_screenshot", return_value={"other": 1}), \
                mock.patch.object(screen, "cleanup"):
            out = ah._handle_screen(self.a, "x")
        self.assertEqual(out, "")


class TestScreenShare(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_stop(self):
        with mock.patch.object(screen_sharing, "stop") as stop:
            out = ah._handle_screen_share(self.a, "stop screen sharing")
        stop.assert_called_once_with()
        self.assertIn("band kar diya", out)

    def test_already_active(self):
        with mock.patch.object(screen_sharing, "is_active", return_value=True):
            out = ah._handle_screen_share(self.a, "start screen sharing")
        self.assertIn("already active", out)

    def test_start(self):
        with mock.patch.object(screen_sharing, "is_active", return_value=False), \
                mock.patch.object(screen_sharing, "start") as start:
            out = ah._handle_screen_share(self.a, "share my screen")
        start.assert_called_once_with(quality=60, fps=2)
        self.assertIn("start kar diya", out)


class TestDictation(unittest.TestCase):
    def test_static_help(self):
        out = ah._handle_dictation(make_assistant(), "dictate")
        self.assertIn("Ctrl+Alt+D", out)


class TestSchedule(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_clear_all(self):
        with mock.patch.object(
            scheduler, "list_tasks", return_value=[{"id": 1}, {"id": 2}]
        ) as lt, mock.patch.object(scheduler, "delete_task", return_value=True) as dt:
            out = ah._handle_schedule(self.a, "sab delete schedule")
        lt.assert_called_once_with()
        self.assertEqual(dt.call_count, 2)
        self.assertIn("Saare tasks delete", out)

    def test_delete_task_by_id(self):
        with mock.patch.object(scheduler, "delete_task", return_value=True) as dt:
            out = ah._handle_schedule(self.a, "delete task 3")
        dt.assert_called_once_with(3)
        self.assertIn("Task #3 delete", out)

    def test_delete_task_missing(self):
        with mock.patch.object(scheduler, "delete_task", return_value=False):
            out = ah._handle_schedule(self.a, "delete task 3")
        self.assertIn("nahi mila", out)

    def test_delete_prompts_with_pending_tasks(self):
        with mock.patch.object(
            scheduler, "list_tasks",
            return_value=[{"id": 1, "title": "Pay bills"}],
        ):
            out = ah._handle_schedule(self.a, "delete task")
        self.assertIn("#1 - Pay bills", out)

    def test_delete_prompts_empty(self):
        with mock.patch.object(scheduler, "list_tasks", return_value=[]):
            out = ah._handle_schedule(self.a, "clear tasks")
        self.assertIn("Koi task nahi", out)

    def test_complete_task(self):
        with mock.patch.object(
            scheduler, "update_task", return_value={"title": "Pay bills"}
        ) as upd:
            out = ah._handle_schedule(self.a, "task 2 done")
        upd.assert_called_once_with(2, status="done")
        self.assertIn("done! 🎉", out)

    def test_complete_task_missing(self):
        with mock.patch.object(scheduler, "update_task", return_value=None):
            out = ah._handle_schedule(self.a, "mark task 2 complete")
        self.assertIn("nahi mila", out)

    def test_complete_without_id(self):
        out = ah._handle_schedule(self.a, "task done")
        self.assertIn("Task # batao", out)

    def test_show_summary(self):
        with mock.patch.object(scheduler, "get_summary", return_value="summary"):
            out = ah._handle_schedule(self.a, "show tasks")
        self.assertEqual(out, "summary")

    def test_create_from_natural(self):
        with mock.patch.object(
            scheduler, "parse_natural", return_value={"title": "Standup"}
        ) as parse, mock.patch.object(
            scheduler, "create_task",
            return_value={"id": 7, "title": "Standup", "due": None},
        ) as create:
            out = ah._handle_schedule(self.a, "remind me to standup at 5pm")
        parse.assert_called_once_with("remind me to standup at 5pm")
        create.assert_called_once_with(title="Standup")
        self.assertIn("Task #7 create", out)

    def test_create_with_due_date_formats(self):
        with mock.patch.object(
            scheduler, "parse_natural", return_value={"title": "X"}
        ), mock.patch.object(
            scheduler, "create_task",
            return_value={"id": 8, "title": "X", "due": "2026-11-24T17:00:00"},
        ):
            out = ah._handle_schedule(self.a, "remind X at 5pm")
        self.assertIn("24 Nov 05:00 PM", out)

    def test_create_with_unparseable_due_falls_back(self):
        with mock.patch.object(
            scheduler, "parse_natural", return_value={"title": "X"}
        ), mock.patch.object(
            scheduler, "create_task",
            return_value={"id": 9, "title": "X", "due": "not-a-date"},
        ):
            out = ah._handle_schedule(self.a, "remind X at 5pm")
        self.assertIn("(not-a-date)", out)

    def test_unknown_text_shows_help(self):
        with mock.patch.object(scheduler, "parse_natural", return_value=None):
            out = ah._handle_schedule(self.a, "zzz nothing")
        self.assertIn("Schedule commands", out)


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_success_returns_result(self):
        with mock.patch(
            "orbit.orbit.agents.orchestrator.PipelineOrchestrator"
        ) as orch_cls:
            orch_cls.return_value.run.return_value = {"result": "done"}
            out = ah._handle_pipeline(self.a, "do something")
        orch_cls.assert_called_once_with(assistant=self.a)
        orch_cls.return_value.run.assert_called_once_with("do something")
        self.assertEqual(out, "done")

    def test_missing_result_key(self):
        with mock.patch(
            "orbit.orbit.agents.orchestrator.PipelineOrchestrator"
        ) as orch_cls:
            orch_cls.return_value.run.return_value = {}
            out = ah._handle_pipeline(self.a, "x")
        self.assertIn("no result", out)

    def test_exception_is_contained(self):
        with mock.patch(
            "orbit.orbit.agents.orchestrator.PipelineOrchestrator",
            side_effect=RuntimeError("kaputt"),
        ):
            out = ah._handle_pipeline(self.a, "x")
        self.assertIn("[Pipeline error: kaputt]", out)


class TestMeetingJoin(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_join_without_url(self):
        with mock.patch("orbit.orbit.meeting.join_meeting") as join:
            out = ah._handle_meeting(self.a, "join the call")
        join.assert_not_called()
        self.assertIn("Pehle URL share karo, Sir!", out)

    def test_join_success(self):
        with mock.patch("orbit.orbit.meeting.join_meeting", return_value=True) as join:
            out = ah._handle_meeting(self.a, "join https://zoom.us/j/123")
        join.assert_called_once_with("https://zoom.us/j/123")
        self.assertIn("Meeting link open kiya", out)

    def test_join_failure(self):
        with mock.patch("orbit.orbit.meeting.join_meeting", return_value=False):
            out = ah._handle_meeting(self.a, "join https://bad.example")
        self.assertIn("Link open nahi ho payi", out)

    def test_join_and_record_success(self):
        with mock.patch("orbit.orbit.meeting.join_meeting", return_value=True), \
                mock.patch(
                    "orbit.orbit.meeting.start_meeting",
                    return_value={"success": True},
                ) as start:
            out = ah._handle_meeting(self.a, "join https://x.me/1 and record")
        start.assert_called_once_with()
        self.assertIn("recording start", out)

    def test_join_and_record_failure(self):
        with mock.patch("orbit.orbit.meeting.join_meeting", return_value=True), \
                mock.patch(
                    "orbit.orbit.meeting.start_meeting",
                    return_value={"success": False, "error": "mic busy"},
                ):
            out = ah._handle_meeting(self.a, "join https://x.me/1 and record")
        self.assertIn("recording start nahi ho payi: mic busy", out)


class TestMeetingRecord(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_start_meeting_with_title(self):
        with mock.patch(
            "orbit.orbit.meeting.start_meeting",
            return_value={"success": True, "title": "standup"},
        ) as start:
            out = ah._handle_meeting(self.a, "start meeting standup")
        start.assert_called_once_with(title="standup")
        self.assertIn("Title: standup", out)

    def test_start_meeting_without_title(self):
        with mock.patch(
            "orbit.orbit.meeting.start_meeting",
            return_value={"success": True, "title": "General"},
        ) as start:
            ah._handle_meeting(self.a, "start meeting")
        start.assert_called_once_with(title=None)

    def test_record_meeting_extracts_title(self):
        with mock.patch(
            "orbit.orbit.meeting.start_meeting",
            return_value={"success": True, "title": "budget"},
        ) as start:
            out = ah._handle_meeting(self.a, "record meeting budget")
        start.assert_called_once_with(title="budget")
        self.assertIn("recording start", out)

    def test_listen_starts_without_title(self):
        with mock.patch(
            "orbit.orbit.meeting.start_meeting",
            return_value={"success": True, "title": "General"},
        ) as start:
            ah._handle_meeting(self.a, "listen to the meeting")
        start.assert_called_once_with(title=None)

    def test_start_failure(self):
        with mock.patch(
            "orbit.orbit.meeting.start_meeting",
            return_value={"success": False, "error": "no mic"},
        ):
            out = ah._handle_meeting(self.a, "start meeting")
        self.assertIn("Status: no mic", out)


class TestMeetingStop(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_stop_with_summary(self):
        with mock.patch(
            "orbit.orbit.meeting.stop_meeting",
            return_value={
                "success": True,
                "meeting": {"title": "Standup", "summary": "discussed X"},
            },
        ):
            out = ah._handle_meeting(self.a, "stop meeting")
        self.assertIn("Meeting Logged!", out)
        self.assertIn("Standup", out)
        self.assertIn("discussed X", out)

    def test_stop_without_transcript(self):
        with mock.patch(
            "orbit.orbit.meeting.stop_meeting", return_value={"success": True}
        ):
            out = ah._handle_meeting(self.a, "stop meeting")
        self.assertIn("transcript was empty", out)

    def test_stop_failure(self):
        with mock.patch(
            "orbit.orbit.meeting.stop_meeting",
            return_value={"success": False, "error": "nothing running"},
        ):
            out = ah._handle_meeting(self.a, "end meeting")
        self.assertIn("Error: nothing running", out)


class TestMeetingSimulateBriefStatus(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_simulate_with_topic(self):
        with mock.patch(
            "orbit.orbit.meeting.simulate_meeting",
            return_value={"success": True, "meeting": {"summary": "sim summary"}},
        ) as sim:
            out = ah._handle_meeting(self.a, "simulate meeting on product sync")
        sim.assert_called_once_with("product sync")
        self.assertIn("Simulated Meeting on product sync", out)
        self.assertIn("sim summary", out)

    def test_simulate_default_topic(self):
        with mock.patch(
            "orbit.orbit.meeting.simulate_meeting",
            return_value={"success": True, "meeting": {"summary": "s"}},
        ) as sim:
            ah._handle_meeting(self.a, "simulate meeting")
        sim.assert_called_once_with("General Sync")

    def test_simulate_failure(self):
        with mock.patch(
            "orbit.orbit.meeting.simulate_meeting",
            return_value={"success": False, "error": "no llm"},
        ):
            out = ah._handle_meeting(self.a, "simulate meeting on x")
        self.assertIn("Simulation error: no llm", out)

    def test_brief_with_topic(self):
        with mock.patch(
            "orbit.orbit.meeting.generate_meeting_brief",
            return_value={"brief": "agenda..."},
        ) as brief:
            out = ah._handle_meeting(self.a, "generate meeting brief for roadmap")
        brief.assert_called_once_with("roadmap")
        self.assertIn("Meeting Brief: roadmap", out)
        self.assertIn("agenda...", out)

    def test_brief_default_topic(self):
        with mock.patch(
            "orbit.orbit.meeting.generate_meeting_brief",
            return_value={"brief": "b"},
        ) as brief:
            ah._handle_meeting(self.a, "make meeting brief")
        brief.assert_called_once_with("General Meeting")

    def test_status_active(self):
        with mock.patch(
            "orbit.orbit.meeting.get_status",
            return_value={"active": True, "title": "Standup", "transcript_count": 7},
        ):
            out = ah._handle_meeting(self.a, "meeting status")
        self.assertIn("Recording active", out)
        self.assertIn("Standup", out)
        self.assertIn("Lines captured: 7", out)

    def test_status_inactive(self):
        # NOTE: avoid "record" here — it would hit the start branch first.
        with mock.patch(
            "orbit.orbit.meeting.get_status", return_value={"active": False}
        ):
            out = ah._handle_meeting(self.a, "chal raha meeting")
        self.assertIn("Koi active meeting recording nahi", out)


class TestMeetingSearchExport(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_search_hit(self):
        with mock.patch(
            "orbit.orbit.meeting.search_meetings", return_value=[{"id": 1}]
        ) as search, mock.patch(
            "orbit.orbit.meeting.format_meetings", return_value="list"
        ):
            out = ah._handle_meeting(self.a, "search meeting budget")
        search.assert_called_once_with("budget")
        self.assertIn("1 match", out)

    def test_search_miss(self):
        with mock.patch("orbit.orbit.meeting.search_meetings", return_value=[]):
            out = ah._handle_meeting(self.a, "search meeting zzz")
        self.assertIn("koi meeting nahi mila", out)

    def test_search_empty_query_skips_search(self):
        # BUG FIXED: search_meetings("") used to run before the empty check.
        with mock.patch("orbit.orbit.meeting.search_meetings") as search:
            out = ah._handle_meeting(self.a, "search meeting")
        search.assert_not_called()
        self.assertIn("Kya dhundhna hai", out)

    def test_export_all_to_file_success(self):
        with mock.patch(
            "orbit.orbit.meeting.export_all_meetings_to_file",
            return_value={"success": True, "path": "C:\\m.md"},
        ) as exp:
            out = ah._handle_meeting(self.a, "export all meetings to file")
        exp.assert_called_once_with()
        self.assertIn("C:\\m.md", out)

    def test_export_all_to_file_failure(self):
        with mock.patch(
            "orbit.orbit.meeting.export_all_meetings_to_file",
            return_value={"success": False},
        ):
            out = ah._handle_meeting(self.a, "export all meetings to file")
        self.assertIn("Export fail", out)

    def test_export_all_markdown(self):
        with mock.patch(
            "orbit.orbit.meeting.export_all_meetings", return_value="# md"
        ) as exp:
            out = ah._handle_meeting(self.a, "export all meetings")
        exp.assert_called_once_with()
        self.assertIn("All Meetings export", out)
        self.assertIn("# md", out)

    def test_export_one_to_file(self):
        with mock.patch(
            "orbit.orbit.meeting.export_meeting_to_file",
            return_value={"success": True, "path": "C:\\3.md"},
        ) as exp:
            out = ah._handle_meeting(self.a, "export meeting #3 to file")
        exp.assert_called_once_with(3)
        self.assertIn("Meeting #3 file mein save", out)

    def test_export_one_to_file_failure(self):
        with mock.patch(
            "orbit.orbit.meeting.export_meeting_to_file",
            return_value={"success": False, "error": "missing"},
        ):
            out = ah._handle_meeting(self.a, "export meeting #3 to file")
        self.assertIn("missing", out)

    def test_export_one_markdown(self):
        with mock.patch(
            "orbit.orbit.meeting.export_meeting", return_value="# one"
        ) as exp:
            out = ah._handle_meeting(self.a, "export meeting #3")
        exp.assert_called_once_with(3)
        self.assertIn("Meeting #3 export", out)

    def test_export_one_missing(self):
        with mock.patch("orbit.orbit.meeting.export_meeting", return_value=None):
            out = ah._handle_meeting(self.a, "export meeting #9")
        self.assertIn("Meeting #9 nahi mila", out)

    def test_export_without_id(self):
        out = ah._handle_meeting(self.a, "export meeting")
        self.assertIn("Kaunsa meeting export karun?", out)


class TestMeetingNotesActionsStats(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_save_to_notes_success(self):
        with mock.patch(
            "orbit.orbit.meeting.save_meeting_to_notes",
            return_value={"success": True, "note_id": 12},
        ) as save:
            out = ah._handle_meeting(self.a, "meeting #3 save to notes")
        save.assert_called_once_with(3)
        self.assertIn("note #12", out)

    def test_save_to_notes_failure(self):
        with mock.patch(
            "orbit.orbit.meeting.save_meeting_to_notes",
            return_value={"success": False, "error": "no notes"},
        ):
            out = ah._handle_meeting(self.a, "meeting #3 save to notes")
        self.assertIn("no notes", out)

    def test_save_to_notes_without_id(self):
        out = ah._handle_meeting(self.a, "save meeting to notes")
        self.assertIn("Kaunsa meeting notes mein save karun?", out)

    def test_action_items_created(self):
        with mock.patch(
            "orbit.orbit.meeting.add_action_items_to_tasks",
            return_value={
                "success": True,
                "created": [{"id": 1, "title": "Do X", "assignee": "Rahul"}],
                "message": "1 task added",
            },
        ) as act:
            out = ah._handle_meeting(self.a, "meeting #3 action items to tasks")
        act.assert_called_once_with(3)
        self.assertIn("1 task added", out)
        self.assertIn("Task #1: Do X (Rahul)", out)

    def test_action_items_none_created(self):
        with mock.patch(
            "orbit.orbit.meeting.add_action_items_to_tasks",
            return_value={"success": True, "created": [], "message": "0 new tasks"},
        ):
            out = ah._handle_meeting(self.a, "meeting #3 action items")
        self.assertEqual(out, "0 new tasks")

    def test_action_items_failure(self):
        with mock.patch(
            "orbit.orbit.meeting.add_action_items_to_tasks",
            return_value={"success": False, "error": "scheduler down"},
        ):
            out = ah._handle_meeting(self.a, "meeting #3 action items")
        self.assertIn("scheduler down", out)

    def test_action_items_without_id(self):
        out = ah._handle_meeting(self.a, "add action items to tasks")
        self.assertIn("Kaunsi meeting ke action items", out)

    def test_stats(self):
        with mock.patch(
            "orbit.orbit.meeting.get_stats",
            return_value={"total": 4, "total_action_items": 9, "last_meeting": "yesterday"},
        ):
            out = ah._handle_meeting(self.a, "meeting stats")
        self.assertIn("Total meetings: 4", out)
        self.assertIn("Total action items: 9", out)
        self.assertIn("yesterday", out)

    def test_stats_no_last_meeting(self):
        with mock.patch(
            "orbit.orbit.meeting.get_stats",
            return_value={"total": 0, "total_action_items": 0, "last_meeting": None},
        ):
            out = ah._handle_meeting(self.a, "show meeting statistics")
        self.assertIn("Last meeting: None", out)


class TestMeetingScheduleDeleteShow(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_schedule_success(self):
        with mock.patch(
            "orbit.orbit.meeting.schedule_meeting",
            return_value={"success": True, "meeting": {"when": "2026-11-24T17:00:00"}},
        ) as sched:
            out = ah._handle_meeting(self.a, "schedule meeting standup at 5pm")
        sched.assert_called_once_with("standup", "5pm")
        self.assertIn("Meeting scheduled: **standup**", out)
        self.assertIn("24 Nov 2026 05:00 PM", out)

    def test_schedule_failure(self):
        with mock.patch(
            "orbit.orbit.meeting.schedule_meeting",
            return_value={"success": False, "error": "slot taken"},
        ):
            out = ah._handle_meeting(self.a, "schedule meeting standup at 5pm")
        self.assertIn("slot taken", out)

    def test_schedule_bad_format(self):
        out = ah._handle_meeting(self.a, "schedule meeting now")
        self.assertIn("Format:", out)

    def test_upcoming_meetings_list(self):
        with mock.patch(
            "orbit.orbit.meeting.format_scheduled_meetings", return_value="upcoming"
        ):
            out = ah._handle_meeting(self.a, "show upcoming meetings")
        self.assertEqual(out, "upcoming")

    def test_cancel_scheduled_meeting(self):
        with mock.patch(
            "orbit.orbit.meeting.delete_scheduled_meeting", return_value=True
        ) as delete:
            out = ah._handle_meeting(self.a, "cancel upcoming meetings 2")
        delete.assert_called_once_with(2)
        self.assertIn("Scheduled meeting #2 cancel", out)

    def test_cancel_scheduled_missing(self):
        with mock.patch(
            "orbit.orbit.meeting.delete_scheduled_meeting", return_value=False
        ):
            out = ah._handle_meeting(self.a, "cancel upcoming meetings 2")
        self.assertIn("nahi mila", out)

    def test_cancel_scheduled_without_id(self):
        out = ah._handle_meeting(self.a, "cancel upcoming meetings")
        self.assertIn("ID batao", out)

    def test_delete_meeting(self):
        with mock.patch(
            "orbit.orbit.meeting.delete_meeting", return_value=True
        ) as delete:
            out = ah._handle_meeting(self.a, "delete meeting 4")
        delete.assert_called_once_with(4)
        self.assertIn("Meeting #4 delete", out)

    def test_delete_meeting_missing(self):
        with mock.patch("orbit.orbit.meeting.delete_meeting", return_value=False):
            out = ah._handle_meeting(self.a, "delete meeting 4")
        self.assertIn("nahi mila", out)

    def test_delete_meeting_without_id(self):
        out = ah._handle_meeting(self.a, "remove meeting")
        self.assertIn("Meeting # batao", out)

    def test_show_meetings(self):
        with mock.patch(
            "orbit.orbit.meeting.list_meetings", return_value=[{"id": 1}]
        ) as lm, mock.patch(
            "orbit.orbit.meeting.format_meetings", return_value="all meetings"
        ) as fmt:
            out = ah._handle_meeting(self.a, "show meetings")
        lm.assert_called_once_with()
        fmt.assert_called_once_with([{"id": 1}])
        self.assertEqual(out, "all meetings")

    def test_show_meeting_detail_by_id(self):
        with mock.patch(
            "orbit.orbit.meeting.format_meeting_detail", return_value="detail"
        ) as fmt:
            out = ah._handle_meeting(self.a, "show meeting #5")
        fmt.assert_called_once_with(5)
        self.assertEqual(out, "detail")

    def test_fallback_with_existing_meetings(self):
        with mock.patch(
            "orbit.orbit.meeting.list_meetings", return_value=[{"id": 1}]
        ) as lm, mock.patch(
            "orbit.orbit.meeting.format_meetings", return_value="listed"
        ):
            out = ah._handle_meeting(self.a, "hello there")
        lm.assert_called_once_with()
        self.assertEqual(out, "listed")

    def test_fallback_without_meetings(self):
        with mock.patch("orbit.orbit.meeting.list_meetings", return_value=[]):
            out = ah._handle_meeting(self.a, "hello there")
        self.assertIn("Meeting helper", out)
