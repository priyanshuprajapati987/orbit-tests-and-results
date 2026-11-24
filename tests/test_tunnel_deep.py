"""Deep coverage tests for orbit/orbit/tunnel.py (782 lines).

test_phase1_hardening.py only covers the token helpers. This file targets
everything else: HMAC key caching, callback plumbing, _broadcast client
pruning, the full _handle_client auth/state machine (server-full, no-auth,
bad token, good token, bad JSON, timeout, OSError), every one of the ~50
_process_request dispatch branches, and start/_accept_loop/stop with a real
localhost round-trip.

Sub-modules (notes, habits, timer, ...) are injected as fakes via
fake_sub() so no real file/network side effects happen and no heavy module
import is required.
"""

import json
import os
import socket
import sys
import time
import types
import unittest
from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import orbit.orbit as orbit_pkg  # noqa: E402
from orbit.orbit import tunnel as tn  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def fake_sub(name, **attrs):
    """Make `from . import <name>` inside tunnel resolve to a fake module."""
    full = f"orbit.orbit.{name}"
    fake = types.ModuleType(full)
    fake.__file__ = f"<fake {full}>"
    for key, val in attrs.items():
        setattr(fake, key, val)
    old_mod = sys.modules.get(full)
    had_attr = hasattr(orbit_pkg, name)
    old_attr = getattr(orbit_pkg, name, None)
    sys.modules[full] = fake
    setattr(orbit_pkg, name, fake)
    try:
        yield fake
    finally:
        if old_mod is None:
            sys.modules.pop(full, None)
        else:
            sys.modules[full] = old_mod
        if had_attr:
            setattr(orbit_pkg, name, old_attr)
        else:
            try:
                delattr(orbit_pkg, name)
            except AttributeError:
                pass


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeConn:
    """Scripted stand-in for a socket: each script item is bytes to return
    from recv(), or an Exception instance to raise."""

    def __init__(self, *script):
        self.script = list(script)
        self.sent = []
        self.closed = False
        self.timeout = None

    def settimeout(self, t):
        self.timeout = t

    def recv(self, n):
        if not self.script:
            return b""
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True

    @property
    def lines(self):
        out = []
        for chunk in self.sent:
            for raw in chunk.split(b"\n"):
                if raw.strip():
                    out.append(json.loads(raw.decode("utf-8")))
        return out


def line(obj):
    return (json.dumps(obj) + "\n").encode("utf-8")


class TunnelBase(unittest.TestCase):
    def setUp(self):
        self._saved = (tn._server, tn._server_thread, list(tn._clients),
                       tn._on_message, tn._on_client_change)
        tn._server = None
        tn._server_thread = None
        tn._clients.clear()
        tn._on_message = None
        tn._on_client_change = None

    def tearDown(self):
        (tn._server, tn._server_thread, clients, tn._on_message,
         tn._on_client_change) = self._saved
        tn._clients.clear()
        tn._clients.extend(clients)

    # -- convenience --------------------------------------------------------
    @staticmethod
    def proc(cmd, args=None, sub=None, **attrs):
        stack_cm = fake_sub(sub, **attrs) if sub else None
        try:
            if stack_cm is not None:
                stack_cm.__enter__()
            return tn._process_request(
                {"cmd": cmd, "args": args or {}}, ("127.0.0.1", 1))
        finally:
            if stack_cm is not None:
                stack_cm.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Module state: HMAC key, callbacks, constants
# ---------------------------------------------------------------------------


class TestModuleState(TunnelBase):
    def test_constants(self):
        self.assertEqual(tn.TUNNEL_HOST, "127.0.0.1")
        self.assertEqual(tn.TUNNEL_PORT, 9876)
        self.assertEqual(tn.MAX_CLIENTS, 10)

    def test_get_hmac_key_caches(self):
        saved = tn._TUNNEL_HMAC_KEY
        try:
            tn._TUNNEL_HMAC_KEY = ""
            k1 = tn._get_hmac_key()
            self.assertTrue(k1)
            self.assertEqual(len(k1), 64)  # token_hex(32)
            # second call must reuse the cached key, not regenerate
            self.assertIs(tn._get_hmac_key(), k1)
            # wipe -> a fresh key is generated
            tn._TUNNEL_HMAC_KEY = ""
            k2 = tn._get_hmac_key()
            self.assertEqual(len(k2), 64)
            self.assertNotEqual(k1, k2)
        finally:
            tn._TUNNEL_HMAC_KEY = saved

    def test_set_callbacks(self):
        fn = MagicMock()
        tn.set_callbacks(on_message=fn)
        self.assertIs(tn._on_message, fn)
        tn.set_callbacks(on_client_change=fn)
        self.assertIs(tn._on_client_change, fn)
        tn.set_callbacks()
        self.assertIsNone(tn._on_message)
        self.assertIsNone(tn._on_client_change)

    def test_get_client_count(self):
        self.assertEqual(tn.get_client_count(), 0)
        tn._clients.extend([FakeConn(), FakeConn()])
        self.assertEqual(tn.get_client_count(), 2)


# ---------------------------------------------------------------------------
# _broadcast
# ---------------------------------------------------------------------------


class TestBroadcast(TunnelBase):
    def test_broadcast_sends_json_line_to_all(self):
        a, b = FakeConn(), FakeConn()
        tn._clients.extend([a, b])
        tn.send_to_clients({"event": "hello", "text": "नमस्ते"})
        for c in (a, b):
            self.assertEqual(c.lines, [{"event": "hello", "text": "नमस्ते"}])
            self.assertTrue(c.sent[0].endswith(b"\n"))

    def test_broadcast_removes_dead_client(self):
        alive = FakeConn()

        class Dead(FakeConn):
            def sendall(self, data):
                raise BrokenPipeError("gone")

        dead = Dead()
        tn._clients.extend([alive, dead])
        with self.assertLogs(tn.logger, level="ERROR"):
            tn._broadcast({"x": 1})
        self.assertEqual(tn._clients, [alive])
        self.assertTrue(dead.closed)
        self.assertEqual(alive.lines, [{"x": 1}])

    def test_broadcast_close_failure_is_logged_not_fatal(self):
        class DeadNoClose(FakeConn):
            def sendall(self, data):
                raise RuntimeError("send failed")

            def close(self):
                raise RuntimeError("close failed")

        dead = DeadNoClose()
        tn._clients.append(dead)
        with self.assertLogs(tn.logger, level="ERROR"):
            tn._broadcast({"x": 1})
        self.assertEqual(tn._clients, [])

    def test_broadcast_client_removed_by_close_is_tolerated(self):
        class SelfRemoving(FakeConn):
            def sendall(self, data):
                raise RuntimeError("send failed")

            def close(self):
                tn._clients.clear()  # simulates concurrent removal

        c = SelfRemoving()
        tn._clients.append(c)
        tn._broadcast({"x": 1})  # ValueError path must not raise
        self.assertEqual(tn._clients, [])


# ---------------------------------------------------------------------------
# _process_request — simple pass-through commands
# ---------------------------------------------------------------------------


class TestSimpleCommands(TunnelBase):
    # (cmd, fake module, function) -> resp["data"] is the function result
    DIRECT = [
        ("sysinfo", "sysinfo", "get_info"),
        ("password", "password_gen", "parse_text"),
        ("text", "text_utils", "parse_and_handle"),
        ("random", "random_utils", "parse_text"),
        ("calculate", "calculator", "calculate"),
        ("json", "json_tools", "parse_and_handle"),
        ("baseconv", "baseconv", "parse_and_handle"),
        ("emoji", "emoji", "parse_text"),
        ("color", "colorconv", "parse_and_handle"),
        ("music", "music_ctrl", "parse_text"),
        ("network", "network", "get_info"),
        ("files", "file_tools", "analyze_dir"),
        ("briefing", "briefing", "format_briefing"),
        ("websearch", "websearch", "parse_text"),
        ("habit_list", "habits", "get_all"),
        ("clipboard_history", "smart_actions", "get_history"),
        ("bookmark_list", "bookmarks", "get_all"),
        ("bookmark_search", "bookmarks", "search"),
        ("list_all", "lists", "list_names"),
        ("focus_status", "focus_timer", "status"),
        ("focus_today", "focus_timer", "today_stats"),
    ]

    def test_direct_passthrough_commands(self):
        sentinel = {"payload": [1, 2, 3]}
        for cmd, sub, func in self.DIRECT:
            with self.subTest(cmd=cmd):
                mock = MagicMock(return_value=sentinel)
                out = self.proc(cmd, sub=sub, **{func: mock})
                self.assertEqual(out["status"], "ok", out)
                self.assertIs(out["data"], sentinel)
                mock.assert_called_once()

    def test_direct_commands_error_path(self):
        for cmd, sub, func in self.DIRECT:
            with self.subTest(cmd=cmd):
                mock = MagicMock(side_effect=RuntimeError("kaput"))
                out = self.proc(cmd, sub=sub, **{func: mock})
                self.assertEqual(out, {"status": "error", "msg": "kaput"})

    def test_ping(self):
        out = self.proc("ping")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"], "pong")
        self.assertIn("ts", out)

    def test_unknown_command(self):
        out = self.proc("definitely_not_a_command")
        self.assertEqual(out["status"], "error")
        self.assertIn("Unknown command: definitely_not_a_command",
                      out["msg"])

    def test_notes_list_slices_to_20(self):
        notes = list(range(25))
        mock = MagicMock(return_value=notes)
        out = self.proc("notes_list", sub="notes", get_all=mock)
        self.assertEqual(out["data"], list(range(20)))

    def test_clipboard_clear(self):
        mock = MagicMock()
        out = self.proc("clipboard_clear", sub="smart_actions",
                        clear_history=mock)
        mock.assert_called_once()
        self.assertEqual(out, {"status": "ok", "msg": "Cleared"})

    def test_focus_stop(self):
        mock = MagicMock()
        out = self.proc("focus_stop", sub="focus_timer", stop=mock)
        mock.assert_called_once()
        self.assertEqual(out["msg"], "Focus stopped")


# ---------------------------------------------------------------------------
# _process_request — exec / notify / status / screen sharing
# ---------------------------------------------------------------------------


class TestExecNotifyStatus(TunnelBase):
    def test_exec_no_text(self):
        out = self.proc("exec", {"text": ""})
        self.assertEqual(out, {"status": "error", "msg": "No text provided"})

    def test_exec_missing_args_key(self):
        out = self.proc("exec")
        self.assertEqual(out["msg"], "No text provided")

    def test_exec_calls_handler(self):
        handler = MagicMock()
        tn.set_callbacks(on_message=handler)
        out = self.proc("exec", {"text": "do it"})
        handler.assert_called_once_with("do it")
        self.assertEqual(out, {"status": "ok", "msg": "Executed: do it"})

    def test_exec_handler_raises(self):
        tn.set_callbacks(on_message=MagicMock(side_effect=ValueError("nope")))
        out = self.proc("exec", {"text": "x"})
        self.assertEqual(out, {"status": "error", "msg": "nope"})

    def test_exec_without_handler(self):
        out = self.proc("exec", {"text": "x"})
        self.assertEqual(out["msg"], "No handler registered")

    def test_notify_calls_handler_with_bracketed_title(self):
        handler = MagicMock()
        tn.set_callbacks(on_message=handler)
        out = self.proc("notify", {"title": "Orbit", "body": "hi"})
        handler.assert_called_once_with("[Orbit] hi")
        self.assertEqual(out["msg"], "Notification sent to Orbit")

    def test_notify_default_title(self):
        handler = MagicMock()
        tn.set_callbacks(on_message=handler)
        self.proc("notify", {"body": "b"})
        handler.assert_called_once_with("[Edith] b")

    def test_notify_without_handler(self):
        out = self.proc("notify", {"body": "b"})
        self.assertEqual(out, {"status": "error", "msg": "No handler"})

    def test_status_reports_clients_and_sharing(self):
        tn._clients.extend([FakeConn(), FakeConn()])
        sharing = MagicMock(return_value=True)
        out = self.proc("status", sub="screen_sharing",
                        is_active=sharing)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data"]["clients"], 2)
        self.assertTrue(out["data"]["sharing"])
        self.assertIn("ts", out["data"])

    def test_status_sharing_false_on_import_error(self):
        out = self.proc("status", sub="screen_sharing",
                        is_active=MagicMock(side_effect=RuntimeError("x")))
        self.assertFalse(out["data"]["sharing"])

    def test_screen_share_start_success(self):
        start = MagicMock(return_value=True)
        out = self.proc("screen_share_start", {"fps": 5, "quality": 30},
                        sub="screen_sharing", start=start)
        start.assert_called_once_with(quality=30, fps=5)
        self.assertEqual(out, {"status": "ok",
                               "msg": "Screen sharing started"})

    def test_screen_share_start_defaults_and_already_active(self):
        start = MagicMock(return_value=False)
        out = self.proc("screen_share_start", sub="screen_sharing",
                        start=start)
        start.assert_called_once_with(quality=60, fps=2)
        self.assertEqual(out, {"status": "error", "msg": "Already active"})

    def test_screen_share_start_exception(self):
        out = self.proc("screen_share_start", sub="screen_sharing",
                        start=MagicMock(side_effect=RuntimeError("no display")))
        self.assertEqual(out["status"], "error")
        self.assertIn("Screen sharing not available: no display", out["msg"])

    def test_screen_share_stop_success_and_error(self):
        stop = MagicMock()
        out = self.proc("screen_share_stop", sub="screen_sharing",
                        stop=stop)
        stop.assert_called_once()
        self.assertEqual(out["msg"], "Screen sharing stopped")

        out = self.proc("screen_share_stop", sub="screen_sharing",
                        stop=MagicMock(side_effect=RuntimeError("busy")))
        self.assertEqual(out["status"], "error")
        self.assertIn("busy", out["msg"])

    def test_screen_share_status_active_flag(self):
        out = self.proc("screen_share_status", sub="screen_sharing",
                        is_active=MagicMock(return_value=True))
        self.assertEqual(out, {"status": "ok", "data": {"active": True}})

        out = self.proc("screen_share_status", sub="screen_sharing",
                        is_active=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out, {"status": "ok", "data": {"active": False}})


# ---------------------------------------------------------------------------
# _process_request — notes / bookmarks / habits / focus
# ---------------------------------------------------------------------------


class TestNotesBookmarksHabits(TunnelBase):
    def test_notes_add_passes_args_with_defaults(self):
        add = MagicMock(return_value={"id": 1})
        out = self.proc("notes_add", sub="notes", add=add)
        add.assert_called_once_with("Untitled", "", None)
        self.assertEqual(out["data"], {"id": 1})

        add2 = MagicMock(return_value={"id": 2})
        self.proc("notes_add", {"title": "T", "body": "B", "tags": ["x"]},
                  sub="notes", add=add2)
        add2.assert_called_once_with("T", "B", ["x"])

    def test_notes_delete_true_false_and_error(self):
        out = self.proc("notes_delete", {"id": 3}, sub="notes",
                        delete=MagicMock(return_value=True))
        self.assertEqual(out["msg"], "Deleted")
        out = self.proc("notes_delete", {"id": 3}, sub="notes",
                        delete=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        self.assertEqual(out["msg"], "Not found")
        out = self.proc("notes_delete", sub="notes",
                        delete=MagicMock(side_effect=RuntimeError("db")))
        self.assertEqual(out["msg"], "db")

    def test_focus_start_default_and_custom_minutes(self):
        start, status = MagicMock(), MagicMock(return_value={"on": True})
        out = self.proc("focus_start", sub="focus_timer", start=start,
                        status=status)
        start.assert_called_once_with(25)
        self.assertEqual(out["data"], {"on": True})

        start2 = MagicMock()
        self.proc("focus_start", {"minutes": 50}, sub="focus_timer",
                  start=start2, status=status)
        start2.assert_called_once_with(50)

    def test_focus_start_error(self):
        out = self.proc("focus_start", sub="focus_timer",
                        start=MagicMock(side_effect=RuntimeError("busy")))
        self.assertEqual(out["status"], "error")

    def test_focus_status_and_today_error_paths(self):
        for cmd in ("focus_status", "focus_today"):
            with self.subTest(cmd=cmd):
                out = self.proc(cmd, sub="focus_timer",
                                **{cmd.split("_")[1] if cmd != "focus_today"
                                   else "today_stats":
                                   MagicMock(side_effect=RuntimeError("x"))})
                self.assertEqual(out["status"], "error")

    def test_bookmark_add_requires_url(self):
        out = self.proc("bookmark_add", {"title": "no url"},
                        sub="bookmarks", add=MagicMock())
        self.assertEqual(out["status"], "error")
        self.assertIn("url", out["msg"])

    def test_bookmark_add_passes_all_fields(self):
        add = MagicMock(return_value={"id": 9})
        out = self.proc("bookmark_add",
                        {"url": "https://a.com", "title": "A",
                         "tags": ["t"], "folder": "dev"},
                        sub="bookmarks", add=add)
        add.assert_called_once_with("https://a.com", "A", ["t"], "dev")
        self.assertEqual(out["data"], {"id": 9})

    def test_bookmark_delete_true_false_error(self):
        out = self.proc("bookmark_delete", {"id": 1}, sub="bookmarks",
                        delete=MagicMock(return_value=True))
        self.assertEqual(out["msg"], "Deleted")
        out = self.proc("bookmark_delete", {"id": 1}, sub="bookmarks",
                        delete=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        out = self.proc("bookmark_delete", sub="bookmarks",
                        delete=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_bookmark_list_and_search_error_paths(self):
        for cmd, fn in (("bookmark_list", "get_all"),
                        ("bookmark_search", "search")):
            with self.subTest(cmd=cmd):
                out = self.proc(cmd, sub="bookmarks",
                                **{fn: MagicMock(
                                    side_effect=RuntimeError("boom"))})
                self.assertEqual(out["msg"], "boom")

    def test_habit_add_defaults_and_custom(self):
        add = MagicMock(return_value={"id": 1})
        out = self.proc("habit_add", sub="habits", add=add)
        add.assert_called_once_with("Untitled", "daily", None)
        self.assertEqual(out["data"], {"id": 1})

        add2 = MagicMock()
        self.proc("habit_add", {"name": "run", "frequency": "weekly",
                                "tags": ["health"]},
                  sub="habits", add=add2)
        add2.assert_called_once_with("run", "weekly", ["health"])

    def test_habit_log_and_delete_boolean_results(self):
        out = self.proc("habit_log", {"id": 1}, sub="habits",
                        log=MagicMock(return_value=True))
        self.assertEqual(out["msg"], "Logged")
        out = self.proc("habit_log", {"id": 1}, sub="habits",
                        log=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        self.assertIn("Already done", out["msg"])

        out = self.proc("habit_delete", {"id": 1}, sub="habits",
                        delete=MagicMock(return_value=True))
        self.assertEqual(out["msg"], "Deleted")
        out = self.proc("habit_delete", {"id": 1}, sub="habits",
                        delete=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")

    def test_habit_error_paths(self):
        for cmd, fn in (("habit_list", "get_all"), ("habit_add", "add"),
                        ("habit_log", "log"), ("habit_delete", "delete")):
            with self.subTest(cmd=cmd):
                out = self.proc(cmd, sub="habits",
                                **{fn: MagicMock(
                                    side_effect=RuntimeError("x"))})
                self.assertEqual(out["msg"], "x")


# ---------------------------------------------------------------------------
# _process_request — stopwatch / timer / search / text-ish
# ---------------------------------------------------------------------------


class TestStopwatchTimerSearch(TunnelBase):
    def test_stopwatch_all_actions(self):
        for action, fn in (("start", "start"), ("stop", "stop"),
                           ("lap", "lap"), ("reset", "reset"),
                           ("status", "status"), ("bogus", "status")):
            with self.subTest(action=action):
                mocks = {name: MagicMock() for name in
                         ("start", "stop", "lap", "reset")}
                mocks["status"] = MagicMock(return_value={"t": 1})
                out = self.proc("stopwatch", {"action": action},
                                sub="stopwatch", **mocks)
                self.assertEqual(out["data"], {"t": 1})
                if fn in ("start", "stop", "lap", "reset"):
                    mocks[fn].assert_called_once()
                else:
                    # default action == status; no mutating call made
                    for name in ("start", "stop", "lap", "reset"):
                        mocks[name].assert_not_called()

    def test_stopwatch_default_action_is_status(self):
        status = MagicMock(return_value={"t": 2})
        out = self.proc("stopwatch", sub="stopwatch", status=status,
                        start=MagicMock())
        self.assertEqual(out["data"], {"t": 2})

    def test_stopwatch_error_path(self):
        out = self.proc("stopwatch", sub="stopwatch",
                        status=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_timer_start_stop_status(self):
        start, stop, status = MagicMock(), MagicMock(), \
            MagicMock(return_value={"left": 10})
        out = self.proc("timer", {"action": "start", "duration": 42},
                        sub="timer", start=start, stop=stop, status=status)
        start.assert_called_once_with(42)
        self.assertEqual(out["msg"], "Timer started")

        out = self.proc("timer", {"action": "stop"}, sub="timer",
                        start=start, stop=stop, status=status)
        stop.assert_called_once()
        self.assertEqual(out["msg"], "Timer stopped")

        out = self.proc("timer", {"action": "whatever"}, sub="timer",
                        start=start, stop=stop, status=status)
        self.assertEqual(out["data"], {"left": 10})

    def test_timer_error_path(self):
        out = self.proc("timer", sub="timer",
                        status=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_search_without_query_returns_stats(self):
        stats = MagicMock(return_value={"docs": 7})
        out = self.proc("search", sub="conv_search", stats=stats,
                        search=MagicMock())
        stats.assert_called_once()
        # source wraps stats under a "stats" key
        self.assertEqual(out["data"], {"stats": {"docs": 7}})

    def test_search_with_query(self):
        search = MagicMock(return_value={"hits": 2})
        out = self.proc("search", {"q": "hello"}, sub="conv_search",
                        stats=MagicMock(), search=search)
        search.assert_called_once_with("hello")
        self.assertEqual(out["data"], {"hits": 2})

    def test_search_error_path(self):
        out = self.proc("search", sub="conv_search",
                        stats=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_password_text_random_calculate_error_paths(self):
        for cmd, sub, fn in (("password", "password_gen", "parse_text"),
                             ("text", "text_utils", "parse_and_handle"),
                             ("random", "random_utils", "parse_text"),
                             ("calculate", "calculator", "calculate")):
            with self.subTest(cmd=cmd):
                out = self.proc(cmd, sub=sub,
                                **{fn: MagicMock(
                                    side_effect=RuntimeError("bad input"))})
                self.assertEqual(out["msg"], "bad input")


# ---------------------------------------------------------------------------
# _process_request — lists / countdowns / journal / decisions
# ---------------------------------------------------------------------------


class TestListsCountdownsJournal(TunnelBase):
    def test_list_add_check_uncheck_remove_delete_show(self):
        m = dict(add_items_from_text=MagicMock(return_value=[{"i": 1}]),
                 check_item=MagicMock(return_value=True),
                 remove_item=MagicMock(return_value=True),
                 delete_list=MagicMock(return_value=True),
                 get_list=MagicMock(return_value=["milk"]))
        out = self.proc("list", {"action": "add", "name": "shop",
                                 "item": "milk, eggs"},
                        sub="lists", **m)
        m["add_items_from_text"].assert_called_once_with("shop",
                                                         "milk, eggs")
        self.assertEqual(out["data"], [{"i": 1}])

        out = self.proc("list", {"action": "check", "name": "shop",
                                 "id": 2}, sub="lists", **m)
        m["check_item"].assert_called_once_with("shop", 2, True)
        self.assertEqual(out["msg"], "Checked")

        out = self.proc("list", {"action": "uncheck", "name": "shop",
                                 "id": 2}, sub="lists", **m)
        m["check_item"].assert_called_with("shop", 2, False)
        self.assertEqual(out["msg"], "Unchecked")

        out = self.proc("list", {"action": "remove", "name": "shop",
                                 "id": 2}, sub="lists", **m)
        m["remove_item"].assert_called_once_with("shop", 2)
        self.assertEqual(out["msg"], "Removed")

        out = self.proc("list", {"action": "delete", "name": "shop"},
                        sub="lists", **m)
        m["delete_list"].assert_called_once_with("shop")
        self.assertEqual(out["msg"], "Deleted")

        out = self.proc("list", {"name": "shop"}, sub="lists", **m)
        m["get_list"].assert_called_once_with("shop")
        self.assertEqual(out["data"], ["milk"])

    def test_list_boolean_false_branches(self):
        m = dict(check_item=MagicMock(return_value=False),
                 remove_item=MagicMock(return_value=False),
                 delete_list=MagicMock(return_value=False))
        for action in ("check", "uncheck", "remove", "delete"):
            with self.subTest(action=action):
                out = self.proc("list", {"action": action, "name": "s"},
                                sub="lists", **m)
                self.assertEqual(out["status"], "error")

    def test_list_error_path(self):
        out = self.proc("list", sub="lists",
                        get_list=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_list_all_error_path(self):
        out = self.proc("list_all", sub="lists",
                        list_names=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_countdown_add_uses_parse_date_result(self):
        when = date(2030, 7, 15)
        parse_date = MagicMock(return_value=when)
        add_event = MagicMock(return_value={"id": 1})
        out = self.proc("countdown", {"action": "add", "name": "Bday",
                                      "date": "July 15"},
                        sub="countdowns", parse_date=parse_date,
                        add_event=add_event)
        parse_date.assert_called_once_with("July 15")
        add_event.assert_called_once_with("Bday", when)
        self.assertEqual(out["data"], {"id": 1})

    def test_countdown_add_falls_back_to_today(self):
        parse_date = MagicMock(return_value=None)
        add_event = MagicMock(return_value={"id": 2})
        self.proc("countdown", {"action": "add"}, sub="countdowns",
                  parse_date=parse_date, add_event=add_event)
        called_with = add_event.call_args.args[1]
        self.assertEqual(called_with, date.today())

    def test_countdown_delete_search_and_default(self):
        out = self.proc("countdown", {"action": "delete", "id": 1},
                        sub="countdowns",
                        delete=MagicMock(return_value=True))
        self.assertEqual(out["msg"], "Deleted")
        out = self.proc("countdown", {"action": "delete", "id": 1},
                        sub="countdowns",
                        delete=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")

        search = MagicMock(return_value=[])
        out = self.proc("countdown", {"action": "search", "q": "x"},
                        sub="countdowns", search=search)
        search.assert_called_once_with("x")

        get_all = MagicMock(return_value=[{"id": 1}])
        out = self.proc("countdown", sub="countdowns", get_all=get_all,
                        parse_date=MagicMock())
        self.assertEqual(out["data"], [{"id": 1}])

    def test_countdown_error_path(self):
        out = self.proc("countdown", sub="countdowns",
                        get_all=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_journal_all_actions(self):
        mocks = dict(get_today=MagicMock(return_value=["e1"]),
                     add_entry=MagicMock(return_value={"id": 1}),
                     search=MagicMock(return_value=[]),
                     stats=MagicMock(return_value={"n": 3}),
                     delete=MagicMock(return_value=True),
                     get_all=MagicMock(return_value=["a", "b"]))
        out = self.proc("journal", {"action": "today"}, sub="journal",
                        **mocks)
        self.assertEqual(out["data"], ["e1"])

        out = self.proc("journal", {"action": "add", "text": "hi"},
                        sub="journal", **mocks)
        mocks["add_entry"].assert_called_with("hi")
        self.assertEqual(out["data"], {"id": 1})

        out = self.proc("journal", {"action": "search", "q": "q"},
                        sub="journal", **mocks)
        mocks["search"].assert_called_with("q")

        out = self.proc("journal", {"action": "stats"}, sub="journal",
                        **mocks)
        self.assertEqual(out["data"], {"n": 3})

        out = self.proc("journal", {"action": "delete", "id": 4},
                        sub="journal", **mocks)
        self.assertEqual(out["msg"], "Deleted")

        out = self.proc("journal", {"action": "other"}, sub="journal",
                        **mocks)
        self.assertEqual(out["data"], ["a", "b"])

    def test_journal_delete_false_and_error(self):
        out = self.proc("journal", {"action": "delete"}, sub="journal",
                        delete=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        out = self.proc("journal", sub="journal",
                        get_all=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_decision_all_actions(self):
        mocks = dict(create=MagicMock(return_value={"id": 1}),
                     add_pro=MagicMock(return_value=True),
                     add_con=MagicMock(return_value=True),
                     delete=MagicMock(return_value=True),
                     get_all=MagicMock(return_value=[]))
        out = self.proc("decision", {"action": "create", "question": "q?"},
                        sub="decisions", **mocks)
        mocks["create"].assert_called_with("q?")
        self.assertEqual(out["data"], {"id": 1})

        out = self.proc("decision", {"action": "add_pro", "id": 1,
                                     "text": "yes"}, sub="decisions",
                        **mocks)
        self.assertEqual(out["msg"], "Pro added")

        out = self.proc("decision", {"action": "add_con", "id": 1,
                                     "text": "no"}, sub="decisions",
                        **mocks)
        self.assertEqual(out["msg"], "Con added")

        out = self.proc("decision", {"action": "delete", "id": 1},
                        sub="decisions", **mocks)
        self.assertEqual(out["msg"], "Deleted")

        out = self.proc("decision", sub="decisions", **mocks)
        self.assertEqual(out["data"], [])

    def test_decision_false_and_error_paths(self):
        out = self.proc("decision", {"action": "add_pro"}, sub="decisions",
                        add_pro=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        out = self.proc("decision", sub="decisions",
                        get_all=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")


# ---------------------------------------------------------------------------
# _process_request — flashcards / expenses / share / quotes
# ---------------------------------------------------------------------------


class TestFlashcardsExpensesShareQuotes(TunnelBase):
    def test_flashcard_all_actions(self):
        mocks = dict(add=MagicMock(return_value={"id": 1}),
                     get_all=MagicMock(return_value=[]),
                     get_due=MagicMock(return_value=[]),
                     delete=MagicMock(return_value=True),
                     review=MagicMock(return_value=True),
                     get_stats=MagicMock(return_value={"seen": 5}),
                     study_session=MagicMock(return_value={"card": 1}))
        out = self.proc("flashcard", {"action": "add", "front": "f",
                                      "back": "b"}, sub="flashcards",
                        **mocks)
        mocks["add"].assert_called_with("f", "b", "general")
        self.assertEqual(out["data"], {"id": 1})

        out = self.proc("flashcard", {"action": "list"}, sub="flashcards",
                        **mocks)
        self.assertEqual(out["data"], [])

        out = self.proc("flashcard", {"action": "due"}, sub="flashcards",
                        **mocks)
        self.assertEqual(out["data"], [])

        out = self.proc("flashcard", {"action": "delete", "id": 1},
                        sub="flashcards", **mocks)
        self.assertEqual(out["msg"], "Deleted")

        out = self.proc("flashcard", {"action": "review", "id": 1,
                                      "correct": False},
                        sub="flashcards", **mocks)
        mocks["review"].assert_called_with(1, False)
        self.assertEqual(out["msg"], "Reviewed")

        out = self.proc("flashcard", {"action": "stats"},
                        sub="flashcards", **mocks)
        self.assertEqual(out["data"], {"seen": 5})

        out = self.proc("flashcard", {"action": "study", "deck": "d"},
                        sub="flashcards", **mocks)
        mocks["study_session"].assert_called_with("d")
        self.assertEqual(out["data"], {"card": 1})

        out = self.proc("flashcard", {"action": "unknown"},
                        sub="flashcards", **mocks)
        self.assertEqual(out["data"], [])

    def test_flashcard_false_branches_and_error(self):
        out = self.proc("flashcard", {"action": "delete"}, sub="flashcards",
                        delete=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        out = self.proc("flashcard", {"action": "review"}, sub="flashcards",
                        review=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        out = self.proc("flashcard", sub="flashcards",
                        get_all=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_flashcard_custom_deck(self):
        get_all = MagicMock(return_value=[])
        self.proc("flashcard", {"action": "list", "deck": "spanish"},
                  sub="flashcards", get_all=get_all)
        get_all.assert_called_with("spanish")

    def test_expense_all_actions(self):
        mocks = dict(add=MagicMock(return_value={"id": 1}),
                     get_today=MagicMock(return_value=[{"a": 1}]),
                     total_today=MagicMock(return_value=250.0),
                     total_month=MagicMock(return_value=900.0),
                     delete=MagicMock(return_value=True),
                     get_all=MagicMock(return_value=[]))
        out = self.proc("expense", {"action": "add", "amount": 10,
                                    "category": "food", "note": "lunch"},
                        sub="expenses", **mocks)
        mocks["add"].assert_called_with(10, "food", "lunch")
        self.assertEqual(out["data"], {"id": 1})

        out = self.proc("expense", {"action": "today"}, sub="expenses",
                        **mocks)
        self.assertEqual(out["data"],
                         {"entries": [{"a": 1}], "total": 250.0})

        out = self.proc("expense", {"action": "month", "year": 2026,
                                    "month": 11}, sub="expenses", **mocks)
        mocks["total_month"].assert_called_with(2026, 11)
        self.assertEqual(out["data"], 900.0)

        out = self.proc("expense", {"action": "month"}, sub="expenses",
                        **mocks)
        mocks["total_month"].assert_called_with(date.today().year,
                                                date.today().month)

        out = self.proc("expense", {"action": "delete", "id": 1},
                        sub="expenses", **mocks)
        self.assertEqual(out["msg"], "Deleted")

        out = self.proc("expense", sub="expenses", **mocks)
        self.assertEqual(out["data"], [])

    def test_expense_false_and_error(self):
        out = self.proc("expense", {"action": "delete"}, sub="expenses",
                        delete=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        out = self.proc("expense", sub="expenses",
                        get_all=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_share_actions(self):
        share = MagicMock(return_value={"status": "ok", "url": "u"})
        out = self.proc("share", {"action": "share", "text": "hello"},
                        sub="share", share=share, get_history=MagicMock(),
                        clear_history=MagicMock(), get_last=MagicMock())
        share.assert_called_once_with("hello")
        self.assertEqual(out["url"], "u")  # share() result passes through

        history = MagicMock(return_value=[1, 2])
        out = self.proc("share", {"action": "history", "limit": 5},
                        sub="share", share=share, get_history=history,
                        clear_history=MagicMock(), get_last=MagicMock())
        history.assert_called_once_with(5)
        self.assertEqual(out["data"], [1, 2])

        clear = MagicMock()
        out = self.proc("share", {"action": "clear"}, sub="share",
                        share=share, get_history=MagicMock(),
                        clear_history=clear, get_last=MagicMock())
        clear.assert_called_once()
        self.assertEqual(out["msg"], "History cleared")

        last = MagicMock(return_value={"last": 1})
        out = self.proc("share", {"action": "whatever"}, sub="share",
                        share=share, get_history=MagicMock(),
                        clear_history=MagicMock(), get_last=last)
        self.assertEqual(out["data"], {"last": 1})

    def test_share_error_path(self):
        out = self.proc("share", sub="share",
                        share=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")

    def test_quote_actions(self):
        mocks = dict(add=MagicMock(return_value={"id": 1}),
                     search=MagicMock(return_value=[]),
                     delete=MagicMock(return_value=True),
                     get_all=MagicMock(return_value=[]),
                     get_random=MagicMock(return_value={"q": "hi"}))
        out = self.proc("quote", {"action": "add", "text": "t",
                                  "author": "a"}, sub="quotes", **mocks)
        mocks["add"].assert_called_with("t", "a")
        self.assertEqual(out["data"], {"id": 1})

        out = self.proc("quote", {"action": "search", "q": "x"},
                        sub="quotes", **mocks)
        self.assertEqual(out["data"], [])

        out = self.proc("quote", {"action": "delete", "id": 1},
                        sub="quotes", **mocks)
        self.assertEqual(out["msg"], "Deleted")

        out = self.proc("quote", {"action": "all"}, sub="quotes", **mocks)
        self.assertEqual(out["data"], [])

        out = self.proc("quote", sub="quotes", **mocks)
        self.assertEqual(out["data"], {"q": "hi"})

    def test_quote_false_and_error(self):
        out = self.proc("quote", {"action": "delete"}, sub="quotes",
                        delete=MagicMock(return_value=False))
        self.assertEqual(out["status"], "error")
        out = self.proc("quote", sub="quotes",
                        get_random=MagicMock(side_effect=RuntimeError("x")))
        self.assertEqual(out["msg"], "x")


# ---------------------------------------------------------------------------
# _process_request — remaining error paths
# ---------------------------------------------------------------------------


class TestRemainingErrorPaths(TunnelBase):
    ERRORS = [
        ("sysinfo", "sysinfo", "get_info"),
        ("json", "json_tools", "parse_and_handle"),
        ("baseconv", "baseconv", "parse_and_handle"),
        ("emoji", "emoji", "parse_text"),
        ("color", "colorconv", "parse_and_handle"),
        ("music", "music_ctrl", "parse_text"),
        ("network", "network", "get_info"),
        ("files", "file_tools", "analyze_dir"),
        ("briefing", "briefing", "format_briefing"),
        ("websearch", "websearch", "parse_text"),
        ("clipboard_history", "smart_actions", "get_history"),
        ("clipboard_clear", "smart_actions", "clear_history"),
    ]

    def test_error_paths(self):
        for cmd, sub, fn in self.ERRORS:
            with self.subTest(cmd=cmd):
                out = self.proc(cmd, sub=sub,
                                **{fn: MagicMock(
                                    side_effect=RuntimeError("kaput"))})
                self.assertEqual(out, {"status": "error", "msg": "kaput"})


# ---------------------------------------------------------------------------
# _handle_client — auth state machine
# ---------------------------------------------------------------------------


class TestHandleClient(TunnelBase):
    ADDR = ("127.0.0.1", 5555)

    @staticmethod
    def auth_line(token):
        return line({"cmd": "auth", "args": {"token": token}})

    def test_sets_socket_timeout(self):
        conn = FakeConn()
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(conn.timeout, 5.0)

    def test_rejects_when_server_full(self):
        for _ in range(tn.MAX_CLIENTS):
            tn._clients.append(FakeConn())
        conn = FakeConn()
        tn._handle_client(conn, self.ADDR)
        self.assertTrue(conn.closed)
        self.assertEqual(conn.lines[0]["msg"], "Server full")
        # rejected client never joined the pool
        self.assertEqual(len(tn._clients), tn.MAX_CLIENTS)

    def test_command_before_auth_rejected(self):
        conn = FakeConn(line({"cmd": "ping"}))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(conn.lines[0]["status"], "error")
        self.assertIn("Not authenticated", conn.lines[0]["msg"])
        self.assertTrue(conn.closed)
        self.assertEqual(tn._clients, [])

    def test_invalid_token_rejected(self):
        conn = FakeConn(self.auth_line("not-a-real-token"))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(conn.lines[0], {"status": "error",
                                         "msg": "Invalid token"})
        self.assertEqual(tn._clients, [])

    def test_auth_missing_token_rejected(self):
        conn = FakeConn(line({"cmd": "auth", "args": {}}))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(conn.lines[0]["msg"], "Invalid token")

    def test_valid_auth_then_ping_roundtrip(self):
        token = tn.generate_tunnel_token()
        conn = FakeConn(self.auth_line(token),
                        line({"cmd": "ping"}))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(conn.lines[0],
                         {"status": "ok", "msg": "Authenticated"})
        self.assertEqual(conn.lines[1]["data"], "pong")
        self.assertEqual(conn.lines[1]["status"], "ok")

    def test_auth_ack_is_not_overwritten_by_dispatch(self):
        # regression: falling through after auth used to let
        # _process_request answer "Unknown command: auth"
        token = tn.generate_tunnel_token()
        conn = FakeConn(self.auth_line(token))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(len(conn.lines), 1)
        self.assertEqual(conn.lines[0]["msg"], "Authenticated")

    def test_malformed_json_and_blank_lines_skipped(self):
        token = tn.generate_tunnel_token()
        conn = FakeConn(b"this is not json\n", b"\n", b"   \n",
                        self.auth_line(token), line({"cmd": "ping"}))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(conn.lines[0]["msg"], "Authenticated")
        self.assertEqual(conn.lines[1]["data"], "pong")

    def test_timeout_on_recv_continues_loop(self):
        token = tn.generate_tunnel_token()
        conn = FakeConn(self.auth_line(token), TimeoutError("slow"),
                        line({"cmd": "ping"}))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(conn.lines[0]["msg"], "Authenticated")
        self.assertEqual(conn.lines[1]["data"], "pong")

    def test_oserror_on_recv_breaks_loop(self):
        token = tn.generate_tunnel_token()
        conn = FakeConn(self.auth_line(token), OSError("reset"))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(conn.lines[0]["msg"], "Authenticated")
        self.assertTrue(conn.closed)
        self.assertEqual(tn._clients, [])

    def test_unexpected_exception_is_logged(self):
        conn = FakeConn(ValueError("weird"))
        with self.assertLogs(tn.logger, level="ERROR"):
            tn._handle_client(conn, self.ADDR)
        self.assertTrue(conn.closed)
        self.assertEqual(tn._clients, [])

    def test_client_change_callback_fires_on_join_and_leave(self):
        changes = []
        tn.set_callbacks(on_client_change=changes.append)
        token = tn.generate_tunnel_token()
        conn = FakeConn(self.auth_line(token))  # then EOF
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(changes, [1, 0])

    def test_client_change_callback_not_fired_when_rejected(self):
        changes = []
        for _ in range(tn.MAX_CLIENTS):
            tn._clients.append(FakeConn())
        tn.set_callbacks(on_client_change=changes.append)
        tn._handle_client(FakeConn(), self.ADDR)
        self.assertEqual(changes, [])

    def test_client_count_reflects_live_clients(self):
        token = tn.generate_tunnel_token()
        conn = FakeConn(self.auth_line(token))
        tn._handle_client(conn, self.ADDR)
        self.assertEqual(tn.get_client_count(), 0)  # cleaned up on EOF


# ---------------------------------------------------------------------------
# start / _accept_loop / stop
# ---------------------------------------------------------------------------


class TestServerLifecycle(TunnelBase):
    def test_start_noop_when_already_running(self):
        tn._server = object()
        with patch.object(tn.socket, "socket") as sock_cls:
            tn.start()
        sock_cls.assert_not_called()

    def test_start_skips_when_not_desktop(self):
        with patch.object(tn, "is_desktop", return_value=False), \
             patch.object(tn.socket, "socket") as sock_cls, \
             self.assertLogs(tn.logger, level="WARNING"):
            tn.start()
        sock_cls.assert_not_called()
        self.assertIsNone(tn._server)

    def test_start_bind_failure_resets_server(self):
        sock = MagicMock()
        sock.bind.side_effect = OSError("address in use")
        with patch.object(tn, "is_desktop", return_value=True), \
             patch.object(tn.socket, "socket", return_value=sock), \
             self.assertLogs(tn.logger, level="ERROR"):
            tn.start()
        self.assertIsNone(tn._server)

    def test_start_success_spawns_accept_thread(self):
        sock = MagicMock()
        with patch.object(tn, "is_desktop", return_value=True), \
             patch.object(tn.socket, "socket", return_value=sock), \
             patch.object(tn.threading, "Thread") as thread_cls:
            tn.start()
            self.assertIs(tn._server, sock)
            sock.setsockopt.assert_called_once()
            sock.bind.assert_called_once_with((tn.TUNNEL_HOST,
                                               tn.TUNNEL_PORT))
            sock.listen.assert_called_once_with(5)
            thread_cls.assert_called_once_with(target=tn._accept_loop,
                                               daemon=True)
            thread_cls.return_value.start.assert_called_once()
            # second call is a no-op
            tn.start()
            self.assertEqual(thread_cls.call_count, 1)
        tn._server = None

    def test_accept_loop_timeout_then_exit(self):
        srv = MagicMock()
        srv.accept.side_effect = [TimeoutError("t"), RuntimeError("bye")]
        tn._server = srv
        tn._accept_loop()  # must return, not hang
        self.assertEqual(srv.accept.call_count, 2)

    def test_accept_loop_spawns_client_thread(self):
        conn = FakeConn()
        srv = MagicMock()
        srv.accept.side_effect = [(conn, ("1.2.3.4", 1)),
                                  RuntimeError("done")]
        tn._server = srv
        tn._accept_loop()
        # give the spawned handler a moment to finish (EOF immediately)
        deadline = time.time() + 2.0
        while tn.get_client_count() and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(tn.get_client_count(), 0)

    def test_stop_closes_clients_and_server(self):
        ok = FakeConn()

        class BadClose(FakeConn):
            def close(self):
                raise RuntimeError("already closed")

        bad = BadClose()
        srv = MagicMock()
        srv.close.side_effect = RuntimeError("sock gone")
        tn._clients.extend([ok, bad])
        tn._server = srv
        with self.assertLogs(tn.logger, level="ERROR"):
            tn.stop()
        self.assertTrue(ok.closed)
        self.assertEqual(tn._clients, [])
        self.assertIsNone(tn._server)

    def test_stop_without_server(self):
        tn.stop()  # must not raise
        self.assertIsNone(tn._server)
        self.assertEqual(tn._clients, [])

    def test_real_start_auth_and_ping_roundtrip(self):
        port = free_port()
        with patch.object(tn, "TUNNEL_PORT", port), \
             patch.object(tn, "is_desktop", return_value=True):
            tn.start()
            self.assertIsNotNone(tn._server)
            try:
                client = self._connect(port)
                try:
                    buf = bytearray()
                    token = tn.generate_tunnel_token()
                    client.sendall(self._auth_line(token))
                    self.assertEqual(self._read_line(client, buf)["msg"],
                                     "Authenticated")
                    client.sendall(self._ping_line())
                    resp = self._read_line(client, buf)
                    self.assertEqual(resp["status"], "ok")
                    self.assertEqual(resp["data"], "pong")
                finally:
                    client.close()
            finally:
                tn.stop()
        self.assertIsNone(tn._server)
        self.assertEqual(tn.get_client_count(), 0)

    def test_real_server_rejects_bad_token(self):
        port = free_port()
        with patch.object(tn, "TUNNEL_PORT", port), \
             patch.object(tn, "is_desktop", return_value=True):
            tn.start()
            try:
                client = self._connect(port)
                try:
                    buf = bytearray()
                    client.sendall(self._auth_line("bogus-token"))
                    resp = self._read_line(client, buf)
                    self.assertEqual(resp["msg"], "Invalid token")
                finally:
                    client.close()
            finally:
                tn.stop()

    # -- socket helpers -----------------------------------------------------
    @staticmethod
    def _connect(port):
        last = None
        for _ in range(60):
            try:
                return socket.create_connection(("127.0.0.1", port),
                                               timeout=3.0)
            except OSError as e:  # Windows loopback can drop first SYN
                last = e
                time.sleep(0.05)
        raise last

    @staticmethod
    def _auth_line(token):
        return (json.dumps({"cmd": "auth",
                            "args": {"token": token}}) + "\n").encode()

    @staticmethod
    def _ping_line():
        return (json.dumps({"cmd": "ping"}) + "\n").encode()

    @staticmethod
    def _read_line(sock, buf):
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)
        if b"\n" not in buf:
            raise AssertionError("no line received")
        raw, _, rest = bytes(buf).partition(b"\n")
        buf.clear()
        buf.extend(rest)
        return json.loads(raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
