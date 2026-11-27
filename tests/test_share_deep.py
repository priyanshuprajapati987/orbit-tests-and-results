"""Deep tests for orbit/orbit/share.py (Loop 13/1)."""

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit import share as sh


class LoadSaveLogTests(unittest.TestCase):
    def test_load_log_missing(self):
        sl = mock.MagicMock()
        sl.exists.return_value = False
        with mock.patch.object(sh, "SHARE_LOG", sl):
            self.assertEqual(sh._load_log(), [])

    def test_load_log_valid(self):
        sl = mock.MagicMock()
        sl.exists.return_value = True
        sl.read_text.return_value = '[{"text":"hi"}]'
        with mock.patch.object(sh, "SHARE_LOG", sl):
            self.assertEqual(sh._load_log(), [{"text": "hi"}])

    def test_load_log_corrupt(self):
        sl = mock.MagicMock()
        sl.exists.return_value = True
        sl.read_text.return_value = "{bad"
        with mock.patch.object(sh, "SHARE_LOG", sl):
            self.assertEqual(sh._load_log(), [])

    def test_save_log_success(self):
        tmp = mock.MagicMock()
        sl = mock.MagicMock()
        sl.parent = mock.MagicMock()
        sl.with_suffix.return_value = tmp
        with mock.patch.object(sh, "SHARE_LOG", sl):
            ok = sh._save_log([{"a": 1}])
        self.assertIsNone(ok)
        sl.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        tmp.write_text.assert_called_once()
        tmp.replace.assert_called_once_with(sl)

    def test_save_log_failure(self):
        tmp = mock.MagicMock()
        tmp.write_text.side_effect = OSError("disk full")
        sl = mock.MagicMock()
        sl.parent = mock.MagicMock()
        sl.with_suffix.return_value = tmp
        with mock.patch.object(sh, "SHARE_LOG", sl):
            ok = sh._save_log([{"a": 1}])
        self.assertFalse(ok)


class ShareTests(unittest.TestCase):
    def setUp(self):
        self._saved_last = sh._last_shared
        self._saved_recent = list(sh._recent)
        sh._last_shared = ""
        sh._recent.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        sh._last_shared = self._saved_last
        sh._recent[:] = self._saved_recent

    def test_share_sets_last_shared(self):
        with mock.patch.object(sh, "_load_log", return_value=[]), \
                mock.patch.object(sh, "_save_log", return_value=True), \
                mock.patch.object(sh, "_get_client_count", return_value=0), \
                mock.patch("orbit.orbit.tunnel", mock.MagicMock(), create=True):
            r = sh.share("hello")
        self.assertEqual(sh.get_last(), "hello")
        self.assertEqual(r["text"], "hello")
        self.assertEqual(r["clients"], 0)

    def test_share_appends_log_and_caps_200(self):
        big = [{"text": f"t{i}"} for i in range(205)]
        with mock.patch.object(sh, "_load_log", return_value=list(big)), \
                mock.patch.object(sh, "_save_log") as save, \
                mock.patch.object(sh, "_get_client_count", return_value=0), \
                mock.patch("orbit.orbit.tunnel", mock.MagicMock(), create=True):
            sh.share("new")
        saved = save.call_args.args[0]
        self.assertEqual(len(saved), 200)
        self.assertEqual(saved[-1]["text"], "new")

    def test_share_recent_grows_then_pops_one(self):
        sh._recent[:] = [f"r{i}" for i in range(25)]
        with mock.patch.object(sh, "_load_log", return_value=[]), \
                mock.patch.object(sh, "_save_log", return_value=True), \
                mock.patch.object(sh, "_get_client_count", return_value=0), \
                mock.patch("orbit.orbit.tunnel", mock.MagicMock(), create=True):
            sh.share("new")
        # one pop per share call
        self.assertEqual(len(sh._recent), 25)

    def test_share_recent_caps_at_20_over_many_calls(self):
        with mock.patch.object(sh, "_load_log", return_value=[]), \
                mock.patch.object(sh, "_save_log", return_value=True), \
                mock.patch.object(sh, "_get_client_count", return_value=0), \
                mock.patch("orbit.orbit.tunnel", mock.MagicMock(), create=True):
            for i in range(25):
                sh.share(f"m{i}")
        self.assertEqual(len(sh._recent), 20)

    def test_share_tunnel_broadcast_success(self):
        tun = mock.MagicMock()
        with mock.patch.object(sh, "_load_log", return_value=[]), \
                mock.patch.object(sh, "_save_log", return_value=True), \
                mock.patch.object(sh, "_get_client_count", return_value=3), \
                mock.patch("orbit.orbit.tunnel", tun, create=True):
            sh.share("hi")
        tun.send_to_clients.assert_called_once()
        payload = tun.send_to_clients.call_args.args[0]
        self.assertEqual(payload["type"], "share")
        self.assertEqual(payload["text"], "hi")

    def test_share_tunnel_broadcast_failure_logged(self):
        tun = mock.MagicMock()
        tun.send_to_clients.side_effect = RuntimeError("tunnel down")
        with mock.patch.object(sh, "_load_log", return_value=[]), \
                mock.patch.object(sh, "_save_log", return_value=True), \
                mock.patch.object(sh, "_get_client_count", return_value=0), \
                mock.patch("orbit.orbit.tunnel", tun, create=True), \
                mock.patch.object(sh, "logger") as lg:
            r = sh.share("hi")
        self.assertEqual(r["text"], "hi")
        lg.exception.assert_called()

    def test_get_client_count_success(self):
        tun = mock.MagicMock()
        tun.get_client_count.return_value = 5
        with mock.patch("orbit.orbit.tunnel", tun, create=True):
            self.assertEqual(sh._get_client_count(), 5)

    def test_get_client_count_failure(self):
        # Force ImportError by setting tunnel module to None in sys.modules
        with mock.patch.dict("sys.modules", {"orbit.orbit.tunnel": None}):
            self.assertEqual(sh._get_client_count(), 0)


class GetLastHistoryClearTests(unittest.TestCase):
    def setUp(self):
        self._saved_last = sh._last_shared
        sh._last_shared = "LAST"
        self.addCleanup(setattr, sh, "_last_shared", self._saved_last)

    def test_get_last(self):
        self.assertEqual(sh.get_last(), "LAST")

    def test_get_history_reverse_and_limit(self):
        log = [{"text": f"t{i}", "time": "2026-01-01T10:00:00"} for i in range(5)]
        with mock.patch.object(sh, "_load_log", return_value=log):
            h = sh.get_history(2)
        self.assertEqual(len(h), 2)
        self.assertEqual(h[0]["text"], "t4")
        self.assertEqual(h[1]["text"], "t3")

    def test_get_history_default_limit(self):
        log = [{"text": f"t{i}", "time": "x"} for i in range(15)]
        with mock.patch.object(sh, "_load_log", return_value=log):
            self.assertEqual(len(sh.get_history()), 10)

    def test_clear_history(self):
        with mock.patch.object(sh, "_save_log", return_value=True) as save:
            sh._recent[:] = ["a", "b"]
            sh.clear_history()
        save.assert_called_once_with([])
        self.assertEqual(sh._recent, [])


class ParseTextTests(unittest.TestCase):
    def setUp(self):
        self._saved_last = sh._last_shared
        sh._last_shared = ""
        self.addCleanup(setattr, sh, "_last_shared", self._saved_last)

    def test_clear_branch(self):
        with mock.patch.object(sh, "clear_history") as ch:
            r = sh.parse_text("clear history")
        ch.assert_called_once()
        self.assertEqual(r, {"type": "action", "result": "🗑 Share history cleared!"})

    def test_clear_via_delete(self):
        with mock.patch.object(sh, "clear_history"):
            r = sh.parse_text("delete all")
        self.assertEqual(r["type"], "action")

    def test_clear_via_saf(self):
        with mock.patch.object(sh, "clear_history"):
            r = sh.parse_text("saf karo")
        self.assertEqual(r["type"], "action")

    def test_clear_via_reset(self):
        with mock.patch.object(sh, "clear_history"):
            r = sh.parse_text("reset")
        self.assertEqual(r["type"], "action")

    def test_history_branch_empty(self):
        with mock.patch.object(sh, "get_history", return_value=[]):
            r = sh.parse_text("history")
        self.assertEqual(r, {"type": "info", "result": "📤 Koi share history nahi hai."})

    def test_history_branch_with_entries(self):
        hist = [{"text": "hello world", "time": "2026-01-01T10:30:45"}]
        with mock.patch.object(sh, "get_history", return_value=hist):
            r = sh.parse_text("purane shares")
        self.assertEqual(r["type"], "info")
        self.assertIn("**Recent Shares** (1):", r["result"])
        self.assertIn("[2026-01-01T10:30:45]", r["result"])
        self.assertIn("hello world", r["result"])

    def test_history_time_short(self):
        hist = [{"text": "hi", "time": "short"}]
        with mock.patch.object(sh, "get_history", return_value=hist):
            r = sh.parse_text("log")
        self.assertIn("[short]", r["result"])

    def test_last_branch_with_shared(self):
        sh._last_shared = "last thing"
        r = sh.parse_text("last")
        self.assertEqual(r["type"], "info")
        self.assertEqual(r["result"], "📤 Last shared: last thing")

    def test_last_branch_empty(self):
        sh._last_shared = ""
        r = sh.parse_text("aakhri")
        self.assertEqual(r["result"], "📤 Kuch shared nahi hai abhi.")

    def test_last_via_akhir(self):
        sh._last_shared = "x"
        r = sh.parse_text("akhir")
        self.assertIn("Last shared", r["result"])

    def test_short_text(self):
        r = sh.parse_text("a")
        self.assertEqual(r, {"type": "info",
                             "result": "📤 Kya share karun? 'share hello everyone' bolo."})

    def test_short_text_empty(self):
        r = sh.parse_text("")
        self.assertEqual(r["type"], "info")

    def test_share_with_clients(self):
        with mock.patch.object(sh, "share", return_value={
                "text": "hi", "time": "t", "clients": 2}):
            r = sh.parse_text("share hi")
        self.assertEqual(r["type"], "action")
        self.assertIn("Shared!", r["result"])
        self.assertIn("2 devices connected", r["result"])
        self.assertEqual(r["data"]["clients"], 2)

    def test_share_no_clients(self):
        with mock.patch.object(sh, "share", return_value={
                "text": "hi", "time": "t", "clients": 1}):
            r = sh.parse_text("share hi")
        self.assertIn("1 device connected", r["result"])

    def test_share_zero_clients(self):
        with mock.patch.object(sh, "share", return_value={
                "text": "hi", "time": "t", "clients": 0}):
            r = sh.parse_text("share hi")
        self.assertIn("No devices connected", r["result"])

    def test_share_strips_command_words(self):
        with mock.patch.object(sh, "share", return_value={
                "text": "hello", "time": "t", "clients": 0}) as sm:
            sh.parse_text("share hello")
        sm.assert_called_once_with("hello")

    def test_share_empty_clean_falls_back_to_text(self):
        with mock.patch.object(sh, "share", return_value={
                "text": "share", "time": "t", "clients": 0}) as sm:
            sh.parse_text("share")
        sm.assert_called_once_with("share")

    def test_share_text_truncated_in_msg(self):
        long = "x" * 100
        with mock.patch.object(sh, "share", return_value={
                "text": long, "time": "t", "clients": 0}):
            r = sh.parse_text(f"broadcast {long}")
        self.assertIn(long[:80], r["result"])


if __name__ == "__main__":
    unittest.main()
