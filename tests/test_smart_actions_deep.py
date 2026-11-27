"""Deep tests for orbit/orbit/smart_actions.py (clipboard smart actions) (Loop 14/2)."""

import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit import smart_actions as sa


def _make_counter():
    c = {"n": 0}

    def f():
        c["n"] += 1
        return c["n"] >= 2

    return f


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = sa.HISTORY_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "clipboard_history.json"
        sa.HISTORY_FILE = self._path
        sa._clipboard_history = []
        self.addCleanup(setattr, sa, "HISTORY_FILE", self._orig)
        self.addCleanup(setattr, sa, "_clipboard_history", [])

    def test_load_missing(self):
        sa._load()
        self.assertEqual(sa._clipboard_history, [])

    def test_load_valid(self):
        self._path.write_text('[{"text":"hi"}]', encoding="utf-8")
        sa._load()
        self.assertEqual(sa._clipboard_history, [{"text": "hi"}])

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        sa._clipboard_history = [{"old": 1}]
        sa._load()
        self.assertEqual(sa._clipboard_history, [])

    def test_load_caps_at_max(self):
        data = [{"text": f"t{i}"} for i in range(60)]
        self._path.write_text(json.dumps(data), encoding="utf-8")
        sa._load()
        self.assertEqual(len(sa._clipboard_history), 50)

    def test_save_success(self):
        sa._clipboard_history = [{"text": "hi"}]
        ok = sa._save()
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = sa._save()
        self.assertFalse(ok)


class SetOnActionTests(unittest.TestCase):
    def test_set_on_action(self):
        cb = lambda x: x
        sa.set_on_action(cb)
        self.assertIs(sa._on_action, cb)
        sa._on_action = None


class AnalyzeTests(unittest.TestCase):
    def test_url(self):
        r = sa.analyze("visit https://example.com/path")
        self.assertTrue(r["has_actions"])
        self.assertEqual(r["actions"][0]["type"], "url")
        self.assertEqual(r["actions"][0]["data"], ["https://example.com/path"])
        self.assertIn("Open URL (1)", r["actions"][0]["label"])

    def test_url_multiple(self):
        r = sa.analyze("https://a.com https://b.com")
        self.assertEqual(r["actions"][0]["data"], ["https://a.com", "https://b.com"])
        self.assertIn("(2)", r["actions"][0]["label"])

    def test_file_path(self):
        r = sa.analyze(r"open C:\Users\foo\bar.txt")
        types = [a["type"] for a in r["actions"]]
        self.assertIn("file", types)

    def test_email(self):
        r = sa.analyze("mail me at a@b.com")
        types = [a["type"] for a in r["actions"]]
        self.assertIn("email", types)
        email_action = [a for a in r["actions"] if a["type"] == "email"][0]
        self.assertEqual(email_action["data"], "mail me at a@b.com")

    def test_code(self):
        r = sa.analyze("def foo():\n    pass")
        types = [a["type"] for a in r["actions"]]
        self.assertIn("code", types)

    def test_code_import(self):
        r = sa.analyze("import os")
        self.assertIn("code", [a["type"] for a in r["actions"]])

    def test_note_for_long_text(self):
        r = sa.analyze("this is a long enough text")
        types = [a["type"] for a in r["actions"]]
        self.assertIn("note", types)

    def test_no_actions_short_text(self):
        r = sa.analyze("hi")
        self.assertFalse(r["has_actions"])
        self.assertEqual(r["actions"], [])
        self.assertEqual(r["preview"], "hi")

    def test_preview_truncated(self):
        r = sa.analyze("x" * 200)
        self.assertEqual(len(r["preview"]), 100)

    def test_combined(self):
        r = sa.analyze("check https://x.com and code def f(): pass email a@b.com " + "p" * 20)
        types = [a["type"] for a in r["actions"]]
        self.assertIn("url", types)
        self.assertIn("code", types)
        self.assertIn("email", types)
        self.assertIn("note", types)

    def test_code_keyword_select(self):
        r = sa.analyze("SELECT * FROM users")
        self.assertIn("code", [a["type"] for a in r["actions"]])

    def test_code_keyword_create(self):
        r = sa.analyze("CREATE TABLE t (id int)")
        self.assertIn("code", [a["type"] for a in r["actions"]])


class AddToHistoryTests(unittest.TestCase):
    def setUp(self):
        self._orig = sa.HISTORY_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = __import__("pathlib").Path(self._d) / "clipboard_history.json"
        sa.HISTORY_FILE = self._path
        sa._clipboard_history = []
        self.addCleanup(setattr, sa, "HISTORY_FILE", self._orig)
        self.addCleanup(setattr, sa, "_clipboard_history", [])

    def test_adds_entry(self):
        with mock.patch.object(sa, "_on_action", None):
            sa.add_to_history("hello world text")
        self.assertEqual(len(sa._clipboard_history), 1)
        e = sa._clipboard_history[0]
        self.assertEqual(e["text"], "hello world text")
        self.assertIn("timestamp", e)
        self.assertIn("analyzed", e)

    def test_dedup_consecutive(self):
        with mock.patch.object(sa, "_on_action", None):
            sa.add_to_history("same text here")
            sa.add_to_history("same text here")
        self.assertEqual(len(sa._clipboard_history), 1)

    def test_dedup_only_top(self):
        with mock.patch.object(sa, "_on_action", None):
            sa.add_to_history("first message here")
            sa.add_to_history("second message here")
            sa.add_to_history("first message here")
        self.assertEqual(len(sa._clipboard_history), 3)

    def test_loads_existing(self):
        self._path.write_text('[{"text":"old"}]', encoding="utf-8")
        with mock.patch.object(sa, "_on_action", None):
            sa.add_to_history("new message here")
        self.assertEqual(sa._clipboard_history[0]["text"], "new message here")
        self.assertEqual(sa._clipboard_history[1]["text"], "old")

    def test_on_action_not_called_when_no_actions(self):
        cb = mock.MagicMock()
        with mock.patch.object(sa, "_on_action", cb):
            sa.add_to_history("hi")
        cb.assert_not_called()

    def test_on_action_none_no_crash(self):
        with mock.patch.object(sa, "_on_action", None):
            sa.add_to_history("https://x.com " + "x" * 20)

    def test_save_called(self):
        with mock.patch.object(sa, "_on_action", None), \
                mock.patch.object(sa, "_save") as sv:
            sa.add_to_history("hello world text")
        sv.assert_called_once()


class GetHistoryTests(unittest.TestCase):
    def setUp(self):
        self._orig = sa.HISTORY_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = __import__("pathlib").Path(self._d) / "clipboard_history.json"
        sa.HISTORY_FILE = self._path
        sa._clipboard_history = []
        self.addCleanup(setattr, sa, "HISTORY_FILE", self._orig)
        self.addCleanup(setattr, sa, "_clipboard_history", [])

    def test_get_history_loads_and_slices(self):
        data = [{"text": f"t{i}"} for i in range(5)]
        self._path.write_text(json.dumps(data), encoding="utf-8")
        r = sa.get_history(2)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["text"], "t0")

    def test_get_history_default_limit_20(self):
        data = [{"text": f"t{i}"} for i in range(30)]
        self._path.write_text(json.dumps(data), encoding="utf-8")
        r = sa.get_history()
        self.assertEqual(len(r), 20)


class ClearHistoryTests(unittest.TestCase):
    def setUp(self):
        self._orig = sa.HISTORY_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = __import__("pathlib").Path(self._d) / "clipboard_history.json"
        sa.HISTORY_FILE = self._path
        sa._clipboard_history = [{"text": "x"}]
        self.addCleanup(setattr, sa, "HISTORY_FILE", self._orig)
        self.addCleanup(setattr, sa, "_clipboard_history", [])

    def test_clear(self):
        with mock.patch.object(sa, "_save") as sv:
            sa.clear_history()
        self.assertEqual(sa._clipboard_history, [])
        sv.assert_called_once()


class PollClipboardTests(unittest.TestCase):
    def test_no_pyperclip_passes(self):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "pyperclip":
                raise ImportError("no pyperclip")
            return real_import(name, *a, **k)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            sa._poll_clipboard()

    def test_with_pyperclip_pastes(self):
        pyperclip = mock.MagicMock()
        pyperclip.paste.side_effect = ["hello world text", "hello world text"]
        sa._watcher_running.clear()
        c = {"n": 0}

        def is_set():
            c["n"] += 1
            return c["n"] >= 2

        sa._watcher_running.is_set = is_set
        sa._watcher_running.wait = mock.MagicMock()
        with mock.patch.dict("sys.modules", {"pyperclip": pyperclip}), \
                mock.patch.object(sa, "add_to_history") as addh, \
                mock.patch.object(sa, "analyze", return_value={"has_actions": False}):
            sa._poll_clipboard()
        self.assertTrue(addh.called)
        sa._watcher_running = threading.Event()

    def test_on_action_called_when_has_actions(self):
        pyperclip = mock.MagicMock()
        pyperclip.paste.side_effect = ["https://x.com " + "y" * 20]
        sa._watcher_running.clear()
        c = {"n": 0}

        def is_set():
            c["n"] += 1
            return c["n"] >= 2

        sa._watcher_running.is_set = is_set
        sa._watcher_running.wait = mock.MagicMock()
        cb = mock.MagicMock()
        sa._on_action = cb
        with mock.patch.dict("sys.modules", {"pyperclip": pyperclip}), \
                mock.patch.object(sa, "add_to_history"), \
                mock.patch.object(sa, "analyze", return_value={"has_actions": True}):
            sa._poll_clipboard()
        cb.assert_called_once()
        sa._on_action = None
        sa._watcher_running = threading.Event()

    def test_paste_exception_logged(self):
        pyperclip = mock.MagicMock()
        pyperclip.paste.side_effect = RuntimeError("paste fail")
        sa._watcher_running.clear()
        c = {"n": 0}

        def is_set():
            c["n"] += 1
            return c["n"] >= 2

        sa._watcher_running.is_set = is_set
        sa._watcher_running.wait = mock.MagicMock()
        with mock.patch.dict("sys.modules", {"pyperclip": pyperclip}), \
                mock.patch.object(sa, "logger") as lg:
            sa._poll_clipboard()
        lg.exception.assert_called()
        sa._watcher_running = threading.Event()

    def test_empty_paste_skipped(self):
        pyperclip = mock.MagicMock()
        pyperclip.paste.return_value = ""
        sa._watcher_running.clear()
        c = {"n": 0}

        def is_set():
            c["n"] += 1
            return c["n"] >= 2

        sa._watcher_running.is_set = is_set
        sa._watcher_running.wait = mock.MagicMock()
        with mock.patch.dict("sys.modules", {"pyperclip": pyperclip}), \
                mock.patch.object(sa, "add_to_history") as addh:
            sa._poll_clipboard()
        addh.assert_not_called()
        sa._watcher_running = threading.Event()


class StartStopWatcherTests(unittest.TestCase):
    def setUp(self):
        sa._watcher_thread = None
        sa._watcher_running.clear()
        self.addCleanup(setattr, sa, "_watcher_thread", None)

    def test_start_watcher_starts_thread(self):
        sa.start_watcher()
        self.assertIsNotNone(sa._watcher_thread)
        sa.stop_watcher()

    def test_start_watcher_noop_if_alive(self):
        t = mock.MagicMock()
        t.is_alive.return_value = True
        sa._watcher_thread = t
        sa.start_watcher()
        self.assertIs(sa._watcher_thread, t)
        sa._watcher_thread = None

    def test_stop_watcher(self):
        t = mock.MagicMock()
        sa._watcher_thread = t
        sa.stop_watcher()
        t.join.assert_called_once_with(timeout=3)

    def test_stop_watcher_none_thread(self):
        sa._watcher_thread = None
        sa.stop_watcher()


class FormatHistoryTests(unittest.TestCase):
    def test_empty(self):
        with mock.patch.object(sa, "get_history", return_value=[]):
            self.assertEqual(sa.format_history(), "📋 Clipboard history khali hai.")

    def test_default_calls_get_history_10(self):
        with mock.patch.object(sa, "get_history", return_value=[]) as gh:
            sa.format_history()
        gh.assert_called_once_with(10)

    def test_items_provided(self):
        items = [{"text": "hello world"}, {"text": "second"}]
        out = sa.format_history(items)
        self.assertIn("📋 **Clipboard History:**", out)
        self.assertIn("1. hello world", out)
        self.assertIn("2. second", out)

    def test_preview_truncated_and_newline_replaced(self):
        items = [{"text": "a" * 80 + "\n" + "b"}]
        out = sa.format_history(items)
        self.assertIn("1. " + ("a" * 60), out)

    def test_items_none_calls_get_history(self):
        with mock.patch.object(sa, "get_history", return_value=[{"text": "x"}]) as gh:
            out = sa.format_history(None)
        gh.assert_called_once_with(10)
        self.assertIn("1. x", out)


if __name__ == "__main__":
    unittest.main()
