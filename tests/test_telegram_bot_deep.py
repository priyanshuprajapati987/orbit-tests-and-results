"""Deep tests for orbit/orbit/core/telegram_bot.py (Loop 21/2)."""

import json
import os
import threading
import time
import unittest
from unittest import mock

from orbit.orbit.core import telegram_bot as tg

class _ResetMixin:
    def setUp(self):
        tg.TelegramBot._instance = None




class TelegramMessageTests(_ResetMixin, unittest.TestCase):
    def test_defaults(self):
        m = tg.TelegramMessage(chat_id=1, user_id=2, username="u",
                               text="hi", message_id=3)
        self.assertEqual(m.timestamp, 0)
        self.assertIsNone(m.reply_to)


class InitTests(_ResetMixin, unittest.TestCase):
    def test_init_no_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            b = tg.TelegramBot()
        self.assertEqual(b._token, "")
        self.assertEqual(b._allowed_users, [])
        self.assertFalse(b._running)
        self.assertIsNone(b._message_handler)
        self.assertEqual(b._stats["messages_received"], 0)
        self.assertEqual(b._history, [])
        self.assertEqual(b._max_history, 200)
        self.assertEqual(b._offset, 0)

    def test_init_with_token_and_users(self):
        with mock.patch.dict(os.environ, {
                "TELEGRAM_BOT_TOKEN": "tok",
                "TELEGRAM_ALLOWED_USERS": "123, 456, abc"}):
            b = tg.TelegramBot()
        self.assertEqual(b._token, "tok")
        self.assertEqual(b._allowed_users, [123, 456])

    def test_init_no_allowed_users(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok"}):
            b = tg.TelegramBot()
        self.assertEqual(b._allowed_users, [])

    def test_get_telegram_bot_creates_new(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            a = tg.get_telegram_bot()
            b = tg.get_telegram_bot()
        self.assertIs(a, b)


class SetMessageHandlerTests(_ResetMixin, unittest.TestCase):
    def test_set(self):
        b = tg.TelegramBot()
        cb = lambda x: x
        b.set_message_handler(cb)
        self.assertIs(b._message_handler, cb)


class StartStopTests(_ResetMixin, unittest.TestCase):
    def test_start_no_token(self):
        b = tg.TelegramBot()
        self.assertEqual(b.start(), {"error": "TELEGRAM_BOT_TOKEN not set"})

    def test_start_already_running(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        self.assertEqual(b.start(), {"status": "already_running"})

    def test_start_success(self):
        b = tg.TelegramBot()
        b._token = "tok"
        with mock.patch.object(b, "_poll_loop"):
            r = b.start()
        self.assertEqual(r, {"status": "started"})
        self.assertTrue(b._running)
        self.assertIsNotNone(b._thread)
        b._running = False

    def test_stop(self):
        b = tg.TelegramBot()
        b._running = True
        t = mock.MagicMock()
        b._thread = t
        r = b.stop()
        self.assertEqual(r, {"status": "stopped"})
        self.assertFalse(b._running)
        t.join.assert_called_once_with(timeout=5)


class SendPhotoTests(_ResetMixin, unittest.TestCase):
    def test_no_token(self):
        b = tg.TelegramBot()
        b._token = ""
        self.assertFalse(b.send_photo(1, "/tmp/x.png"))

    def test_file_missing(self):
        b = tg.TelegramBot()
        b._token = "tok"
        with mock.patch("os.path.exists", return_value=False):
            self.assertFalse(b.send_photo(1, "/tmp/nope.png"))

    def test_file_too_large(self):
        b = tg.TelegramBot()
        b._token = "tok"
        with mock.patch("os.path.exists", return_value=True), \
                mock.patch("os.path.getsize", return_value=20 * 1024 * 1024), \
                mock.patch.object(tg, "logger") as lg:
            self.assertFalse(b.send_photo(1, "/tmp/big.png"))
        lg.error.assert_called()

    def test_read_failure(self):
        b = tg.TelegramBot()
        b._token = "tok"
        with mock.patch("os.path.exists", return_value=True), \
                mock.patch("os.path.getsize", return_value=100), \
                mock.patch("builtins.open", side_effect=OSError("read fail")), \
                mock.patch.object(tg, "logger") as lg:
            self.assertFalse(b.send_photo(1, "/tmp/x.png"))
        lg.error.assert_called()

    def test_success(self):
        b = tg.TelegramBot()
        b._token = "tok"
        resp = mock.MagicMock()
        resp.read.return_value = b'{"ok": true}'
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("os.path.exists", return_value=True), \
                mock.patch("os.path.getsize", return_value=100), \
                mock.patch("os.path.basename", return_value="x.png"), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"imgdata")), \
                mock.patch("urllib.request.urlopen", return_value=cm):
            self.assertTrue(b.send_photo(1, "/tmp/x.png", caption="cap"))

    def test_exception(self):
        b = tg.TelegramBot()
        b._token = "tok"
        with mock.patch("os.path.exists", return_value=True), \
                mock.patch("os.path.getsize", return_value=100), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"img")), \
                mock.patch("urllib.request.urlopen", side_effect=Exception("net")), \
                mock.patch.object(tg, "logger") as lg:
            self.assertFalse(b.send_photo(1, "/tmp/x.png"))
        self.assertEqual(b._stats["errors"], 1)
        lg.error.assert_called()


class SendPhotoTruncateTests(_ResetMixin, unittest.TestCase):
    def test_caption_truncated(self):
        b = tg.TelegramBot()
        b._token = "tok"
        resp = mock.MagicMock()
        resp.read.return_value = b'{"ok": true}'
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("os.path.exists", return_value=True), \
                mock.patch("os.path.getsize", return_value=10), \
                mock.patch("os.path.basename", return_value="x.png"), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"img")), \
                mock.patch("urllib.request.urlopen", return_value=cm) as ur:
            b.send_photo(1, "/tmp/x.png", caption="c" * 2000)
        body = ur.call_args.args[0].data
        self.assertIn(b"c" * 1024, body)


class SendMessageTests(_ResetMixin, unittest.TestCase):
    def test_no_token(self):
        b = tg.TelegramBot()
        b._token = ""
        self.assertFalse(b.send_message(1, "hi"))

    def test_success(self):
        b = tg.TelegramBot()
        b._token = "tok"
        resp = mock.MagicMock()
        resp.read.return_value = b'{"ok": true}'
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=cm):
            self.assertTrue(b.send_message(123, "hi"))
        self.assertEqual(b._stats["messages_sent"], 1)

    def test_plain_fallback(self):
        b = tg.TelegramBot()
        b._token = "tok"
        resp1 = mock.MagicMock()
        resp1.read.return_value = b'{"ok": false}'
        cm1 = mock.MagicMock()
        cm1.__enter__ = mock.MagicMock(return_value=resp1)
        cm1.__exit__ = mock.MagicMock(return_value=False)
        resp2 = mock.MagicMock()
        resp2.read.return_value = b'{"ok": true}'
        cm2 = mock.MagicMock()
        cm2.__enter__ = mock.MagicMock(return_value=resp2)
        cm2.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", side_effect=[cm1, cm2]):
            self.assertTrue(b.send_message(123, "hi"))
        self.assertEqual(b._stats["messages_sent"], 1)

    def test_plain_fallback_fail(self):
        b = tg.TelegramBot()
        b._token = "tok"
        resp1 = mock.MagicMock()
        resp1.read.return_value = b'{"ok": false}'
        cm1 = mock.MagicMock()
        cm1.__enter__ = mock.MagicMock(return_value=resp1)
        cm1.__exit__ = mock.MagicMock(return_value=False)
        resp2 = mock.MagicMock()
        resp2.read.return_value = b'{"ok": false}'
        cm2 = mock.MagicMock()
        cm2.__enter__ = mock.MagicMock(return_value=resp2)
        cm2.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", side_effect=[cm1, cm2]):
            self.assertFalse(b.send_message(123, "hi"))

    def test_parse_mode_none_no_fallback(self):
        b = tg.TelegramBot()
        b._token = "tok"
        resp1 = mock.MagicMock()
        resp1.read.return_value = b'{"ok": false}'
        cm1 = mock.MagicMock()
        cm1.__enter__ = mock.MagicMock(return_value=resp1)
        cm1.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=cm1):
            self.assertFalse(b.send_message(123, "hi", parse_mode=None))

    def test_exception(self):
        b = tg.TelegramBot()
        b._token = "tok"
        with mock.patch("urllib.request.urlopen", side_effect=Exception("net")), \
                mock.patch.object(tg, "logger") as lg:
            self.assertFalse(b.send_message(123, "hi"))
        self.assertEqual(b._stats["errors"], 1)
        lg.error.assert_called_once()

    def test_truncate_4096(self):
        b = tg.TelegramBot()
        b._token = "tok"
        resp = mock.MagicMock()
        resp.read.return_value = b'{"ok": true}'
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=cm) as ur:
            b.send_message(1, "x" * 5000)
        import json
        body = ur.call_args.args[0].data
        self.assertEqual(len(json.loads(body)["text"]), 4096)


class HandleUpdateTests(_ResetMixin, unittest.TestCase):
    def test_no_message(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._handle_update({})  # no crash
        self.assertEqual(b._stats["messages_received"], 0)

    def test_no_text(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._handle_update({"message": {"chat": {"id": 1}, "from": {"id": 2}}})
        self.assertEqual(b._stats["messages_received"], 0)

    def test_no_allowed_users_denies(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = []
        with mock.patch.object(b, "send_message", return_value=True) as sm:
            b._handle_update({"message": {"chat": {"id": 5}, "from": {"id": 2,
                             "is_bot": False, "username": "u"}, "text": "hi",
                             "message_id": 10}})
        sm.assert_called_once_with(5, "Access denied. Bot allowlist not configured.")
        self.assertEqual(b._stats["messages_received"], 0)

    def test_unauthorized_user(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [999]
        with mock.patch.object(b, "send_message", return_value=True) as sm:
            b._handle_update({"message": {"chat": {"id": 5}, "from": {"id": 2,
                             "is_bot": False, "username": "u"}, "text": "hi",
                             "message_id": 10}})
        sm.assert_called_once_with(5, "Access denied. Your user ID is not authorized.")
        self.assertEqual(b._stats["messages_received"], 0)

    def test_success_with_handler(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [123]
        b._message_handler = mock.MagicMock(return_value="reply")
        with mock.patch.object(b, "send_message", return_value=True) as sm:
            b._handle_update({"message": {"chat": {"id": 5}, "from": {"id": 123,
                             "is_bot": False, "username": "u"}, "text": "hi",
                             "message_id": 10, "date": 12345}})
        self.assertEqual(b._stats["messages_received"], 1)
        self.assertEqual(len(b._history), 1)
        self.assertEqual(b._history[0]["chat_id"], 5)
        self.assertEqual(b._history[0]["text"], "hi")
        sm.assert_called_once_with(5, "reply")

    def test_success_handler_no_response(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [123]
        b._message_handler = mock.MagicMock(return_value=None)
        with mock.patch.object(b, "send_message", return_value=True) as sm:
            b._handle_update({"message": {"chat": {"id": 5}, "from": {"id": 123,
                             "is_bot": False, "username": "u"}, "text": "hi",
                             "message_id": 10}})
        sm.assert_not_called()

    def test_handler_exception(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [123]
        b._message_handler = mock.MagicMock(side_effect=RuntimeError("boom"))
        with mock.patch.object(b, "send_message", return_value=True) as sm, \
                mock.patch.object(tg, "logger") as lg:
            b._handle_update({"message": {"chat": {"id": 5}, "from": {"id": 123,
                             "is_bot": False, "username": "u"}, "text": "hi",
                             "message_id": 10}})
        self.assertEqual(b._stats["errors"], 1)
        lg.error.assert_called_once()
        calls = [c.args for c in sm.call_args_list]
        self.assertTrue(any("An error occurred" in str(c) for c in calls))

    def test_no_handler(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [123]
        b._message_handler = None
        with mock.patch.object(b, "send_message", return_value=True) as sm:
            b._handle_update({"message": {"chat": {"id": 5}, "from": {"id": 123,
                             "is_bot": False, "username": "u"}, "text": "hi",
                             "message_id": 10}})
        sm.assert_called_once_with(5, "ORBIT backend not connected. Use /status to check.")

    def test_history_cap_200(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [123]
        b._message_handler = mock.MagicMock(return_value=None)
        for i in range(205):
            b._handle_update({"message": {"chat": {"id": 5}, "from": {"id": 123,
                             "is_bot": False, "username": "u"}, "text": f"hi{i}",
                             "message_id": i}})
        self.assertEqual(len(b._history), 200)

    def test_handle_update_with_reply_to(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [123]
        b._message_handler = mock.MagicMock(return_value=None)
        b._handle_update({"message": {"chat": {"id": 5}, "from": {"id": 123,
                         "is_bot": False, "username": "u"}, "text": "hi",
                         "message_id": 10, "reply_to_message": {"message_id": 5}}})
        self.assertIsNone(b._history[0]["reply_to"])


class PollLoopTests(_ResetMixin, unittest.TestCase):
    def test_poll_loop_urllib_error(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        import urllib.error
        call_count = {"n": 0}

        def urlopen_side(*a, **k):
            call_count["n"] += 1
            if call_count["n"] >= 1:
                b._running = False
            raise urllib.error.URLError("net")

        with mock.patch("urllib.request.urlopen", side_effect=urlopen_side), \
                mock.patch("time.sleep"):
            b._poll_loop()

    def test_poll_loop_generic_exception(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        call_count = {"n": 0}

        def urlopen_side(*a, **k):
            call_count["n"] += 1
            if call_count["n"] >= 1:
                b._running = False
            raise RuntimeError("boom")

        with mock.patch("urllib.request.urlopen", side_effect=urlopen_side), \
                mock.patch("time.sleep"), \
                mock.patch.object(tg, "logger") as lg:
            b._poll_loop()
        self.assertEqual(b._stats["errors"], 1)
        lg.error.assert_called()

    def test_poll_loop_ok_no_updates(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        resp = mock.MagicMock()
        resp.read.return_value = b'{"ok": true, "result": []}'
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        call_count = {"n": 0}

        def urlopen_side(*a, **k):
            call_count["n"] += 1
            if call_count["n"] >= 1:
                b._running = False
            return cm

        with mock.patch("urllib.request.urlopen", side_effect=urlopen_side):
            b._poll_loop()

    def test_poll_loop_processes_update(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [123]
        b._message_handler = mock.MagicMock(return_value=None)
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps({"ok": True, "result": [
            {"update_id": 5, "message": {"chat": {"id": 1}, "from": {"id": 123,
             "is_bot": False, "username": "u"}, "text": "hi", "message_id": 10}}]}).encode()
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        call_count = {"n": 0}

        def urlopen_side(*a, **k):
            call_count["n"] += 1
            if call_count["n"] >= 1:
                b._running = False
            return cm

        with mock.patch("urllib.request.urlopen", side_effect=urlopen_side):
            b._poll_loop()
        self.assertEqual(b._offset, 6)


class GetStatusHistoryTests(_ResetMixin, unittest.TestCase):
    def test_get_status(self):
        b = tg.TelegramBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [1, 2]
        b._stats["messages_received"] = 5
        b._history = [{"a": 1}]
        s = b.get_status()
        self.assertTrue(s["running"])
        self.assertTrue(s["token_set"])
        self.assertEqual(s["allowed_users"], 2)
        self.assertEqual(s["stats"]["messages_received"], 5)
        self.assertEqual(s["history_count"], 1)

    def test_get_history(self):
        b = tg.TelegramBot()
        b._history = [{"i": i} for i in range(10)]
        self.assertEqual(len(b.get_history(3)), 3)
        # invalid limit -> 50
        self.assertEqual(len(b.get_history("abc")), 10)  # capped at available

    def test_get_history_clamped(self):
        b = tg.TelegramBot()
        b._history = [{"i": i} for i in range(250)]
        r = b.get_history(300)
        self.assertEqual(len(r), 200)

    def test_get_history_min_1(self):
        b = tg.TelegramBot()
        b._history = [{"i": i} for i in range(5)]
        r = b.get_history(0)
        self.assertEqual(len(r), 1)

    def test_set_allowed_users(self):
        b = tg.TelegramBot()
        b.set_allowed_users([1, 2])
        self.assertEqual(b._allowed_users, [1, 2])


if __name__ == "__main__":
    unittest.main()
