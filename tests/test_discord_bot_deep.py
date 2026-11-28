"""Deep tests for orbit/orbit/core/discord_bot.py (Loop 20/3)."""

import json
import os
import threading
import time
import unittest
from unittest import mock

from orbit.orbit.core import discord_bot as db

class _ResetMixin:
    def setUp(self):
        db.DiscordBot._instance = None




class DiscordMessageTests(_ResetMixin, unittest.TestCase):
    def test_defaults(self):
        m = db.DiscordMessage(channel_id=1, guild_id=2, user_id=3,
                              username="u", content="hi", message_id=4)
        self.assertEqual(m.timestamp, 0)
        self.assertEqual(m.channel_id, 1)


class InitTests(_ResetMixin, unittest.TestCase):
    def test_init_no_token(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            b = db.DiscordBot()
        self.assertEqual(b._token, "")
        self.assertEqual(b._allowed_guilds, [])
        self.assertEqual(b._allowed_users, [])
        self.assertFalse(b._running)
        self.assertIsNone(b._message_handler)
        self.assertEqual(b._stats["messages_received"], 0)
        self.assertEqual(b._history, [])
        self.assertEqual(b._max_history, 200)

    def test_init_with_token_and_guilds_users(self):
        with mock.patch.dict(os.environ, {
                "DISCORD_BOT_TOKEN": "tok",
                "DISCORD_ALLOWED_GUILDS": "123, 456, abc",
                "DISCORD_ALLOWED_USERS": "789"}):
            b = db.DiscordBot()
        self.assertEqual(b._token, "tok")
        self.assertEqual(b._allowed_guilds, [123, 456])
        self.assertEqual(b._allowed_users, [789])

    def test_init_singleton_new_each_call(self):
        # get_discord_bot creates new instance each time
        with mock.patch.dict(os.environ, {}, clear=True):
            a = db.get_discord_bot()
            b = db.get_discord_bot()
        self.assertIs(a, b)


class SetMessageHandlerTests(_ResetMixin, unittest.TestCase):
    def test_set(self):
        b = db.DiscordBot()
        cb = lambda x: x
        b.set_message_handler(cb)
        self.assertIs(b._message_handler, cb)


class StartStopTests(_ResetMixin, unittest.TestCase):
    def test_start_no_token(self):
        b = db.DiscordBot()
        self.assertEqual(b.start(), {"error": "DISCORD_BOT_TOKEN not set"})
        self.assertFalse(b._running)

    def test_start_already_running(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        self.assertEqual(b.start(), {"status": "already_running"})

    def test_start_success(self):
        b = db.DiscordBot()
        b._token = "tok"
        with mock.patch.object(b, "_run_bot"):
            r = b.start()
        self.assertEqual(r, {"status": "started"})
        self.assertTrue(b._running)
        self.assertGreater(b._stats["start_time"], 0)
        self.assertIsNotNone(b._thread)
        # cleanup
        b._running = False

    def test_stop(self):
        b = db.DiscordBot()
        b._running = True
        ws = mock.MagicMock()
        b._ws = ws
        r = b.stop()
        self.assertEqual(r, {"status": "stopped"})
        self.assertFalse(b._running)
        ws.close.assert_called_once()
        self.assertIsNone(b._ws)

    def test_stop_ws_close_exception(self):
        b = db.DiscordBot()
        b._running = True
        ws = mock.MagicMock()
        ws.close.side_effect = Exception("boom")
        b._ws = ws
        r = b.stop()
        self.assertEqual(r, {"status": "stopped"})
        self.assertIsNone(b._ws)

    def test_stop_no_ws(self):
        b = db.DiscordBot()
        b._running = True
        b._ws = None
        r = b.stop()
        self.assertEqual(r, {"status": "stopped"})


class RunBotTests(_ResetMixin, unittest.TestCase):
    def test_import_error_websocket(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        gateway_resp = mock.MagicMock()
        gateway_resp.read.return_value = b'{"url": "wss://gw"}'
        gateway_cm = mock.MagicMock()
        gateway_cm.__enter__ = mock.MagicMock(return_value=gateway_resp)
        gateway_cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=gateway_cm), \
                mock.patch.dict("sys.modules", {"websocket": None}), \
                mock.patch.object(db, "logger") as lg:
            b._run_bot()
        self.assertFalse(b._running)
        lg.error.assert_called()
        self.assertIn("websocket-client not installed", lg.error.call_args.args[0])

    def test_gateway_exception(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        # make urllib.request.urlopen raise
        with mock.patch("urllib.request.urlopen", side_effect=Exception("net down")), \
                mock.patch.object(db, "logger") as lg:
            b._run_bot()
        self.assertFalse(b._running)
        self.assertEqual(b._stats["errors"], 1)
        lg.error.assert_called()

    def test_bot_message_ignored(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        msg = {"author": {"id": "1", "bot": True}, "content": "hi",
               "channel_id": "1", "guild_id": "1"}
        b._on_message(msg)
        self.assertEqual(b._stats["messages_received"], 0)

    def test_allowed_users_filter(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._allowed_users = [999]
        msg = {"author": {"id": "123", "username": "u", "bot": False},
               "guild_id": "456", "channel_id": "789", "content": "hi",
               "id": "1"}
        b._on_message(msg)
        self.assertEqual(b._stats["messages_received"], 0)

    def test_allowed_guilds_filter(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._allowed_guilds = [999]
        msg = {"author": {"id": "123", "username": "u", "bot": False},
               "guild_id": "456", "channel_id": "789", "content": "hi",
               "id": "1"}
        b._on_message(msg)
        self.assertEqual(b._stats["messages_received"], 0)

    def test_empty_content_ignored(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        msg = {"author": {"id": "123", "username": "u", "bot": False},
               "guild_id": "456", "channel_id": "789", "content": "",
               "id": "1"}
        b._on_message(msg)
        self.assertEqual(b._stats["messages_received"], 0)

    def test_no_handler_sends_backend_not_connected(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._message_handler = None
        msg = {"author": {"id": "123", "username": "u", "bot": False},
               "guild_id": "456", "channel_id": "789", "content": "hi",
               "id": "1"}
        with mock.patch.object(b, "send_message", return_value=True) as sm:
            b._on_message(msg)
        sm.assert_called_once_with(789, "ORBIT backend not connected.")

    def test_handler_exception_sends_error_message(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._message_handler = mock.MagicMock(side_effect=RuntimeError("boom"))
        msg = {"author": {"id": "123", "username": "u", "bot": False},
               "guild_id": "456", "channel_id": "789", "content": "hi",
               "id": "1"}
        with mock.patch.object(b, "send_message", return_value=True) as sm, \
                mock.patch.object(db, "logger") as lg:
            b._on_message(msg)
        self.assertEqual(b._stats["errors"], 1)
        lg.error.assert_called_once()
        # error message sent
        calls = [c.args for c in sm.call_args_list]
        self.assertTrue(any("An error occurred" in str(c) for c in calls))

    def test_handler_no_response_no_send(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._message_handler = mock.MagicMock(return_value=None)
        msg = {"author": {"id": "123", "username": "u", "bot": False},
               "guild_id": "456", "channel_id": "789", "content": "hi",
               "id": "1"}
        with mock.patch.object(b, "send_message", return_value=True) as sm:
            b._on_message(msg)
        sm.assert_not_called()

    def test_history_cap_200(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._message_handler = mock.MagicMock(return_value=None)
        for i in range(205):
            msg = {"author": {"id": "123", "username": "u", "bot": False},
                   "guild_id": "456", "channel_id": "789", "content": f"hi{i}",
                   "id": str(i)}
            b._on_message(msg)
        self.assertEqual(len(b._history), 200)

    def test_handle_gateway_event_message_create(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        with mock.patch.object(b, "_on_message") as om:
            b._handle_gateway_event({"op": 0, "t": "MESSAGE_CREATE", "d": {"x": 1}})
        om.assert_called_once_with({"x": 1})

    def test_handle_gateway_event_other(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        with mock.patch.object(b, "_on_message") as om:
            b._handle_gateway_event({"op": 10, "t": "HELLO", "d": {}})
        om.assert_not_called()

    def test_heartbeat_exception_breaks(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        ws = mock.MagicMock()
        ws.send.side_effect = Exception("boom")
        b._ws = ws
        b._heartbeat(0.5)  # should not raise, breaks loop

    def test_heartbeat_no_ws(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._ws = None
        # while condition: self._running and self._ws -> False -> exits immediately
        b._heartbeat(0.5)


class SendMessageTests(_ResetMixin, unittest.TestCase):
    def test_no_token(self):
        b = db.DiscordBot()
        b._token = ""
        self.assertFalse(b.send_message(1, "hi"))

    def test_success_200(self):
        b = db.DiscordBot()
        b._token = "tok"
        resp = mock.MagicMock(status=200)
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=cm):
            r = b.send_message(123, "hello")
        self.assertTrue(r)
        self.assertEqual(b._stats["messages_sent"], 1)

    def test_success_201(self):
        b = db.DiscordBot()
        b._token = "tok"
        resp = mock.MagicMock(status=201)
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=cm):
            r = b.send_message(123, "hello")
        self.assertTrue(r)

    def test_non_success_status(self):
        b = db.DiscordBot()
        b._token = "tok"
        resp = mock.MagicMock(status=400)
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=cm):
            r = b.send_message(123, "hello")
        self.assertFalse(r)

    def test_exception(self):
        b = db.DiscordBot()
        b._token = "tok"
        with mock.patch("urllib.request.urlopen", side_effect=Exception("net")), \
                mock.patch.object(db, "logger") as lg:
            r = b.send_message(123, "hello")
        self.assertFalse(r)
        self.assertEqual(b._stats["errors"], 1)
        lg.error.assert_called_once()

    def test_text_truncated_2000(self):
        b = db.DiscordBot()
        b._token = "tok"
        resp = mock.MagicMock(status=200)
        cm = mock.MagicMock()
        cm.__enter__ = mock.MagicMock(return_value=resp)
        cm.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=cm) as ur:
            b.send_message(1, "x" * 3000)
        body = ur.call_args.args[0].data
        import json
        self.assertEqual(len(json.loads(body)["content"]), 2000)


class GetStatusHistoryTests(_ResetMixin, unittest.TestCase):
    def test_get_status(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._allowed_guilds = [1, 2]
        b._allowed_users = [3]
        b._stats["messages_received"] = 5
        b._history = [{"a": 1}]
        s = b.get_status()
        self.assertTrue(s["running"])
        self.assertTrue(s["token_set"])
        self.assertEqual(s["allowed_guilds"], 2)
        self.assertEqual(s["allowed_users"], 1)
        self.assertEqual(s["stats"]["messages_received"], 5)
        self.assertEqual(s["history_count"], 1)

    def test_get_history(self):
        b = db.DiscordBot()
        b._history = [{"i": i} for i in range(10)]
        self.assertEqual(len(b.get_history(3)), 3)
        self.assertEqual(b.get_history(3)[0]["i"], 7)

    def test_get_history_default_50(self):
        b = db.DiscordBot()
        b._history = [{"i": i} for i in range(60)]
        self.assertEqual(len(b.get_history()), 50)

    def test_set_allowed_users(self):
        b = db.DiscordBot()
        b.set_allowed_users([1, 2, 3])
        self.assertEqual(b._allowed_users, [1, 2, 3])


    def test_run_bot_heartbeat_thread_exception_in_recv(self):
        # bytes message skipped
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        gateway_resp = mock.MagicMock()
        gateway_resp.read.return_value = b'{"url": "wss://gw"}'
        gateway_cm = mock.MagicMock()
        gateway_cm.__enter__ = mock.MagicMock(return_value=gateway_resp)
        gateway_cm.__exit__ = mock.MagicMock(return_value=False)

        ws = mock.MagicMock()
        call_count = {"n": 0}

        def recv_side():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return b"bytes-msg"  # bytes -> continue
            if call_count["n"] == 2:
                return json.dumps({"op": 0, "t": "MESSAGE_CREATE", "d": {
                    "author": {"id": "1", "username": "u", "bot": False},
                    "guild_id": "1", "channel_id": "1", "content": "hi",
                    "id": "1"}})
            raise Exception("exit")

        ws.recv.side_effect = recv_side

        websocket_mod = mock.MagicMock()
        websocket_mod.create_connection.return_value = ws
        websocket_mod.WebSocketTimeoutError = Exception

        b._message_handler = mock.MagicMock(return_value=None)
        fake_thread = mock.MagicMock()
        with mock.patch("urllib.request.urlopen", return_value=gateway_cm), \
                mock.patch.dict("sys.modules", {"websocket": websocket_mod}), \
                mock.patch("threading.Thread", return_value=fake_thread), \
                mock.patch.object(b, "send_message", return_value=True):
            b._run_bot()

    def test_handler_error_line_215(self):
        b = db.DiscordBot()
        b._token = "tok"
        b._running = True
        b._message_handler = mock.MagicMock(side_effect=RuntimeError("boom"))
        msg = {"author": {"id": "123", "username": "u", "bot": False},
               "guild_id": "456", "channel_id": "789", "content": "hi",
               "id": "1"}
        with mock.patch.object(b, "send_message", return_value=True) as sm, \
                mock.patch.object(db, "logger"):
            b._on_message(msg)
        # the error-message send
        calls = [c.args for c in sm.call_args_list]
        self.assertTrue(any("An error occurred" in str(c) for c in calls))
