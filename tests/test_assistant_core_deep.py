"""Deep tests for orbit/orbit/assistant.py — the central Assistant orchestrator.

Covers the entire runtime half of the module (lines ~897-1363 were 0%
covered): tunnel I/O, history cleanup, wake word, proactive messages,
emission callbacks, intent detection + disambiguation, LLM respond, quick
responses, talk-back formatting, ``_process`` orchestration (queen vs tool vs
LLM fallback), voice loop, and the singleton getter.

Construction is hermetic: ``make_assistant()`` patches tts/tools/queen/tunnel/
usage-tracker side effects, so no server starts and no audio device is touched.
"""

import builtins
import importlib
import threading
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from unittest import mock

from orbit.orbit import assistant as asst


def make_assistant():
    """Construct an Assistant with every import-time side effect patched."""
    with (
        mock.patch.object(asst, "tts"),
        mock.patch.object(asst, "ComputerTool"),
        mock.patch.object(asst, "NewsTool"),
        mock.patch.object(asst, "SecurityTool"),
        mock.patch.object(asst, "N8nTool"),
        mock.patch.object(asst, "QueenAgent"),
        mock.patch.object(asst, "AGENT_REGISTRY", {"ALPHA": mock.MagicMock()}),
        mock.patch.object(asst.usage_tracker, "start_session"),
        mock.patch.object(asst.tunnel, "set_callbacks"),
        mock.patch.object(asst.tunnel, "start"),
    ):
        return asst.Assistant()


class TestInit(unittest.TestCase):
    def test_default_state(self):
        a = make_assistant()
        self.assertEqual(a.model, asst.DEFAULT_OLLAMA_MODEL)
        self.assertEqual(a.history, [])
        self.assertFalse(a.listening)
        self.assertFalse(a.wake_word_enabled)
        self.assertFalse(a.girlfriend_mode)
        self.assertFalse(a.offline_mode)
        self.assertFalse(a.force_offline)
        self.assertTrue(a.speak_responses)
        self.assertTrue(a._first_reply)
        self.assertEqual(a._last_intent, "chat")
        self.assertIsNone(a._on_message)
        self.assertIsNone(a._on_status)
        self.assertIsNone(a._on_agent_activate)
        self.assertIsNone(a._wake_word_detector)
        self.assertEqual(a.skill_counts.get("computer"), 0)
        self.assertEqual(a.skill_counts.get("meeting"), 0)
        self.assertGreaterEqual(len(a.skill_counts), 40)
        self.assertTrue(all(v == 0 for v in a.skill_counts.values()))

    def test_init_side_effects(self):
        with (
            mock.patch.object(asst, "tts") as tts_m,
            mock.patch.object(asst, "ComputerTool") as comp,
            mock.patch.object(asst, "NewsTool") as news,
            mock.patch.object(asst, "SecurityTool") as sec,
            mock.patch.object(asst, "N8nTool") as n8n,
            mock.patch.object(asst, "QueenAgent") as queen_cls,
            mock.patch.object(asst, "AGENT_REGISTRY", {"ALPHA": mock.MagicMock()}) as reg,
            mock.patch.object(asst.usage_tracker, "start_session") as sess,
            mock.patch.object(asst.tunnel, "set_callbacks") as tcb,
            mock.patch.object(asst.tunnel, "start") as tstart,
        ):
            a = asst.Assistant()
        tts_m.set_engine.assert_called_once_with(asst.TTS_ENGINE)
        sess.assert_called_once_with()
        tcb.assert_called_once_with(on_message=a._tunnel_message)
        tstart.assert_called_once_with()
        queen_cls.assert_called_once_with(assistant=a)
        self.assertEqual(list(a.queen.set_agents.call_args.args[0]), ["ALPHA"])
        self.assertIsInstance(a.computer_tool, type(comp.return_value))
        self.assertIsInstance(a.news_tool, type(news.return_value))
        self.assertIsInstance(a.security_tool, type(sec.return_value))
        self.assertIsInstance(a.n8n_tool, type(n8n.return_value))
        self.assertTrue(hasattr(a, "_history_lock"))

    def test_init_queen_sets_callback_when_already_set(self):
        a = make_assistant()
        cb = mock.Mock()
        a._on_agent_activate = cb
        with mock.patch.object(asst, "QueenAgent") as queen_cls:
            a._init_queen()
        queen_cls.return_value.set_callback.assert_called_once_with(cb)

    def test_init_queen_skips_callback_when_none(self):
        a = make_assistant()
        a._on_agent_activate = None
        with mock.patch.object(asst, "QueenAgent") as queen_cls:
            a._init_queen()
        queen_cls.return_value.set_callback.assert_not_called()


class TestTunnelIO(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_tunnel_message_spawns_daemon_thread(self):
        with mock.patch.object(asst.threading, "Thread") as th:
            self.a._tunnel_message("hello")
        th.assert_called_once_with(
            target=self.a._handle_tunnel, args=("hello",), daemon=True
        )
        th.return_value.start.assert_called_once_with()

    def test_handle_tunnel_forwards_reply(self):
        with mock.patch.object(self.a, "send_text", return_value="R"), \
                mock.patch.object(asst.tunnel, "send_to_clients") as send:
            self.a._handle_tunnel("cmd")
        send.assert_called_once_with(
            {"status": "reply", "data": "R", "cmd": "cmd"}
        )

    def test_handle_tunnel_contains_exception(self):
        with mock.patch.object(
            self.a, "send_text", side_effect=ValueError("boom")
        ), mock.patch.object(asst.tunnel, "send_to_clients") as send:
            self.a._handle_tunnel("cmd")
        payload = send.call_args.args[0]
        self.assertEqual(payload["status"], "reply")
        self.assertEqual(payload["cmd"], "cmd")
        self.assertIn("Error processing request: boom", payload["data"])

    def test_get_time_brief(self):
        with mock.patch.object(asst.usage_tracker, "get_brief", return_value="B"):
            self.assertEqual(self.a.get_time_brief(), "B")


class TestHistoryCleanup(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_keeps_fresh_drops_stale(self):
        now = datetime.now()
        self.a.history = [
            {"role": "user", "content": "fresh", "timestamp": now},
            {"role": "user", "content": "old", "timestamp": now - timedelta(hours=48)},
        ]
        self.a._cleanup_old_history()
        self.assertEqual([m["content"] for m in self.a.history], ["fresh"])

    def test_iso_string_timestamps_parsed(self):
        now = datetime.now()
        self.a.history = [
            {"content": "fresh-str", "timestamp": now.isoformat()},
            {"content": "old-str", "timestamp": (now - timedelta(hours=48)).isoformat()},
        ]
        self.a._cleanup_old_history()
        self.assertEqual([m["content"] for m in self.a.history], ["fresh-str"])

    def test_invalid_string_kept(self):
        self.a.history = [{"content": "bad-ts", "timestamp": "not-a-date"}]
        self.a._cleanup_old_history()
        self.assertEqual(len(self.a.history), 1)

    def test_missing_timestamp_dropped(self):
        self.a.history = [
            {"content": "no-ts"},
            {"content": "none-ts", "timestamp": None},
        ]
        self.a._cleanup_old_history()
        self.assertEqual(self.a.history, [])

    def test_non_datetime_timestamp_dropped(self):
        self.a.history = [{"content": "int-ts", "timestamp": 12345}]
        self.a._cleanup_old_history()
        self.assertEqual(self.a.history, [])

    def test_boundary_just_inside_24h_kept(self):
        now = datetime.now()
        self.a.history = [
            {"content": "edge", "timestamp": now - timedelta(hours=23, minutes=59)},
        ]
        self.a._cleanup_old_history()
        self.assertEqual(len(self.a.history), 1)


class TestWakeWord(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_enable_available(self):
        det = mock.MagicMock()
        det.is_available.return_value = True
        with mock.patch.object(
            asst.wake_word_module, "get_wake_word_detector", return_value=det
        ):
            self.a.set_wake_word(True)
        self.assertTrue(self.a.wake_word_enabled)
        det.start.assert_called_once_with(callback=self.a._on_wake_word_detected)
        self.assertIs(self.a._wake_word_detector, det)

    def test_enable_unavailable_disables(self):
        det = mock.MagicMock()
        det.is_available.return_value = False
        with mock.patch.object(
            asst.wake_word_module, "get_wake_word_detector", return_value=det
        ):
            self.a.set_wake_word(True)
        self.assertFalse(self.a.wake_word_enabled)
        det.start.assert_not_called()
        self.assertIsNone(self.a._wake_word_detector)

    def test_disable_stops_existing_detector(self):
        det = mock.MagicMock()
        self.a._wake_word_detector = det
        self.a.set_wake_word(False)
        self.assertFalse(self.a.wake_word_enabled)
        det.stop.assert_called_once_with()
        self.assertIsNone(self.a._wake_word_detector)

    def test_disable_without_detector_is_noop(self):
        self.a.set_wake_word(False)
        self.assertFalse(self.a.wake_word_enabled)

    def test_detected_while_listening_is_ignored(self):
        self.a.listening = True
        with mock.patch.object(asst.threading, "Thread") as th:
            self.a._on_wake_word_detected()
        th.assert_not_called()

    def test_detected_starts_listen_thread(self):
        self.a.listening = False
        with mock.patch.object(asst.threading, "Thread") as th:
            self.a._on_wake_word_detected()
        th.assert_called_once_with(
            target=self.a.listen_and_respond, daemon=True
        )
        th.return_value.start.assert_called_once_with()


class TestCallbacksAndEmits(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_set_callbacks_updates_and_forwards_to_queen(self):
        m1, m2, m3 = mock.Mock(), mock.Mock(), mock.Mock()
        self.a.set_callbacks(on_message=m1, on_status=m2, on_agent_activate=m3)
        self.assertIs(self.a._on_message, m1)
        self.assertIs(self.a._on_status, m2)
        self.assertIs(self.a._on_agent_activate, m3)
        self.a.queen.set_callback.assert_called_once_with(m3)

    def test_emits_fire_callbacks(self):
        m1, m2, m3 = mock.Mock(), mock.Mock(), mock.Mock()
        self.a.set_callbacks(on_message=m1, on_status=m2, on_agent_activate=m3)
        self.a._emit_message("user", "hi")
        self.a._emit_status("thinking", "...")
        self.a._emit_agent("TAS")
        m1.assert_called_once_with("user", "hi")
        m2.assert_called_once_with("thinking", "...")
        m3.assert_called_once_with("TAS")

    def test_emits_without_callbacks_are_noops(self):
        self.a._emit_message("user", "hi")
        self.a._emit_status("idle", "Ready")
        self.a._emit_agent("TAS")  # must not raise


class TestFuzzyMatch(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_substring_is_full_match(self):
        self.assertEqual(self.a._fuzzy_match("open notepad", "open"), 1.0)

    def test_single_word_miss_is_zero(self):
        self.assertEqual(self.a._fuzzy_match("nothing here", "open"), 0.0)

    def test_multi_word_all_matched(self):
        self.assertEqual(self.a._fuzzy_match("open the file", "open file"), 1.0)

    def test_multi_word_partial(self):
        # "open folder now" -> open+folder present, now absent = 2/3
        self.assertAlmostEqual(
            self.a._fuzzy_match("open folder", "open folder now"), 2 / 3
        )

    def test_word_match_is_case_insensitive(self):
        self.assertEqual(self.a._fuzzy_match("OPEN the FILE", "open file"), 1.0)


class TestProactive(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_no_message_returns_none(self):
        with mock.patch.object(
            asst.proactive, "get_proactive_message", return_value=None
        ):
            self.assertIsNone(self.a.send_proactive())

    def test_emits_and_speaks(self):
        with mock.patch.object(
            asst.proactive, "get_proactive_message", return_value="psst"
        ), mock.patch.object(self.a, "_emit_message") as em, \
                mock.patch.object(self.a, "_emit_status") as es, \
                mock.patch.object(asst.tts, "speak") as speak:
            self.a.tts_engine = "pyttsx3"  # not xtts/kokoro -> tts_voice used
            out = self.a.send_proactive()
        self.assertEqual(out, "psst")
        em.assert_called_once_with("assistant", "psst")
        es.assert_called_once_with("speaking", "Speaking...")
        speak.assert_called_once_with(
            "psst", self.a.tts_voice, self.a.tts_speed, offline=False
        )

    def test_speak_disabled_still_emits(self):
        self.a.speak_responses = False
        with mock.patch.object(
            asst.proactive, "get_proactive_message", return_value="psst"
        ), mock.patch.object(self.a, "_emit_message") as em, \
                mock.patch.object(self.a, "_emit_status") as es, \
                mock.patch.object(asst.tts, "speak") as speak:
            out = self.a.send_proactive()
        self.assertEqual(out, "psst")
        em.assert_called_once_with("assistant", "psst")
        es.assert_not_called()
        speak.assert_not_called()

    def test_tts_failure_does_not_raise(self):
        with mock.patch.object(
            asst.proactive, "get_proactive_message", return_value="psst"
        ), mock.patch.object(self.a, "_emit_message"), \
                mock.patch.object(self.a, "_emit_status"), \
                mock.patch.object(
                    asst.tts, "speak", side_effect=RuntimeError("no audio")
        ):
            out = self.a.send_proactive()
        self.assertEqual(out, "psst")

    def test_kokoro_voice_and_offline_flag(self):
        self.a.tts_engine = "kokoro"
        self.a.kokoro_voice = "kf_voice"
        self.a.offline_mode = True
        with mock.patch.object(
            asst.proactive, "get_proactive_message", return_value="m"
        ), mock.patch.object(self.a, "_emit_message"), \
                mock.patch.object(self.a, "_emit_status"), \
                mock.patch.object(asst.tts, "speak") as speak:
            self.a.send_proactive()
        speak.assert_called_once_with(
            "m", "kf_voice", self.a.tts_speed, offline=True
        )


class TestMeetingReminders(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_no_due_returns_none(self):
        with mock.patch.object(
            asst.meeting_module, "get_due_scheduled_meetings", return_value=[]
        ):
            self.assertIsNone(self.a.pop_meeting_reminders())

    def test_due_without_url(self):
        with mock.patch.object(
            asst.meeting_module,
            "get_due_scheduled_meetings",
            return_value=[{"title": "Standup"}],
        ):
            out = self.a.pop_meeting_reminders()
        self.assertIn("Meeting reminders", out)
        self.assertIn("📅 Standup", out)
        self.assertNotIn("—", out)

    def test_due_with_url(self):
        with mock.patch.object(
            asst.meeting_module,
            "get_due_scheduled_meetings",
            return_value=[{"title": "Sync", "url": "https://x.me/j"}],
        ):
            out = self.a.pop_meeting_reminders()
        self.assertIn("Sync — https://x.me/j", out)


class TestDetectIntent(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def _patch_defs(self, defs, hints=None):
        return (
            mock.patch.dict(asst.TOOL_DEFINITIONS, defs, clear=True),
            mock.patch.dict(asst.TOOL_CONTEXT_HINTS, hints or {}, clear=True),
        )

    def test_exact_keyword_match(self):
        d1, d2 = self._patch_defs(
            {"alpha": {"keywords": ["alpha"], "weight": 1.0}},
        )
        with d1, d2:
            self.assertEqual(self.a._detect_intent("run alpha now"), "alpha")
        self.assertEqual(self.a._last_intent, "alpha")

    def test_no_match_returns_chat_and_resets_memory(self):
        d1, d2 = self._patch_defs(
            {"alpha": {"keywords": ["alpha"], "weight": 1.0}},
        )
        self.a._last_intent = "alpha"
        with d1, d2:
            self.assertEqual(self.a._detect_intent("random words"), "chat")
        self.assertEqual(self.a._last_intent, "chat")

    def test_context_hint_bonus_scores(self):
        d1, d2 = self._patch_defs(
            {"alpha": {"keywords": ["alpha"], "weight": 1.0}},
            hints={"alpha": ["hintword"]},
        )
        with d1, d2:
            self.assertEqual(self.a._detect_intent("hintword"), "alpha")

    def test_fuzzy_typo_still_scores(self):
        # "alphq" vs "alpha": length-adjacent, SequenceMatcher ratio 0.8 > 0.7
        # (similarity is computed against the whole text, so keep it short)
        d1, d2 = self._patch_defs(
            {"alpha": {"keywords": ["alpha"], "weight": 1.0}},
        )
        with d1, d2:
            self.assertEqual(self.a._detect_intent("alphq"), "alpha")

    def test_low_similarity_rejected(self):
        d1, d2 = self._patch_defs(
            {"alpha": {"keywords": ["alpha"], "weight": 1.0}},
        )
        with d1, d2:
            self.assertEqual(self.a._detect_intent("zzzzz qqqqq"), "chat")

    def test_last_intent_boost_breaks_tie(self):
        d1, d2 = self._patch_defs(
            {
                "alpha": {"keywords": ["alpha"], "weight": 1.0},
                "beta": {"keywords": ["beta"], "weight": 1.0},
            },
        )
        # equal raw scores; remembered "beta" gets x1.2 and wins
        self.a._last_intent = "beta"
        mem = mock.MagicMock()
        mem.get_correction_pattern.return_value = None
        with d1, d2, mock.patch(
            "orbit.orbit.core.smart_memory.get_smart_memory", return_value=mem
        ):
            self.assertEqual(self.a._detect_intent("alpha beta"), "beta")

    def test_no_boost_when_last_is_chat(self):
        d1, d2 = self._patch_defs(
            {
                "alpha": {"keywords": ["alpha"], "weight": 1.0},
                "beta": {"keywords": ["beta"], "weight": 1.0},
            },
        )
        self.a._last_intent = "chat"
        mem = mock.MagicMock()
        mem.get_correction_pattern.return_value = None
        with d1, d2, mock.patch(
            "orbit.orbit.core.smart_memory.get_smart_memory", return_value=mem
        ):
            # max() on ties picks the first inserted key = alpha
            self.assertEqual(self.a._detect_intent("alpha beta"), "alpha")

    def test_real_dictionary_news(self):
        self.assertEqual(self.a._detect_intent("show me the news"), "news")

    def test_real_dictionary_chat(self):
        self.assertEqual(self.a._detect_intent("hello there buddy"), "chat")


class TestDisambiguate(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_single_score_passthrough(self):
        self.assertEqual(self.a._disambiguate("x", {"alpha": 1.0}, "alpha"), "alpha")

    def test_override_match_returns_first(self):
        scores = {"computer": 1.0, "security": 1.0}
        self.assertEqual(
            self.a._disambiguate("scan the ports", scores, "computer"), "computer"
        )

    def test_override_no_match_returns_second_when_not_lower(self):
        scores = {"computer": 1.0, "security": 1.0}
        self.assertEqual(
            self.a._disambiguate("hello world", scores, "computer"), "security"
        )

    def test_clear_margin_returns_best(self):
        scores = {"alpha": 2.0, "beta": 1.0}
        self.assertEqual(self.a._disambiguate("alpha", scores, "alpha"), "alpha")

    def test_close_tie_uses_smart_memory_correction(self):
        scores = {"alpha": 1.0, "beta": 0.9}
        mem = mock.MagicMock()
        mem.get_correction_pattern.return_value = "beta"
        with mock.patch(
            "orbit.orbit.core.smart_memory.get_smart_memory", return_value=mem
        ):
            out = self.a._disambiguate("alpha beta", scores, "alpha")
        mem.get_correction_pattern.assert_called_once_with("alpha beta")
        self.assertEqual(out, "beta")

    def test_close_tie_without_correction_returns_best(self):
        scores = {"alpha": 1.0, "beta": 0.9}
        mem = mock.MagicMock()
        mem.get_correction_pattern.return_value = None
        with mock.patch(
            "orbit.orbit.core.smart_memory.get_smart_memory", return_value=mem
        ):
            out = self.a._disambiguate("x", scores, "alpha")
        self.assertEqual(out, "alpha")

    def test_close_tie_memory_failure_returns_best(self):
        scores = {"alpha": 1.0, "beta": 0.9}
        with mock.patch(
            "orbit.orbit.core.smart_memory.get_smart_memory",
            side_effect=RuntimeError("down"),
        ):
            out = self.a._disambiguate("x", scores, "alpha")
        self.assertEqual(out, "alpha")

    def test_correction_outside_top5_ignored(self):
        scores = {"alpha": 1.0, "beta": 0.9}
        mem = mock.MagicMock()
        mem.get_correction_pattern.return_value = "zzz"  # not in top-5 keys
        with mock.patch(
            "orbit.orbit.core.smart_memory.get_smart_memory", return_value=mem
        ):
            out = self.a._disambiguate("x", scores, "alpha")
        self.assertEqual(out, "alpha")


class TestHandleTool(unittest.TestCase):
    def test_delegates_to_assistant_handlers(self):
        a = make_assistant()
        with mock.patch(
            "orbit.orbit.assistant_handlers._handle_tool", return_value="R"
        ) as h:
            out = a._handle_tool("news", "latest")
        h.assert_called_once_with(a, "news", "latest")
        self.assertEqual(out, "R")


class TestLLMRespond(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()
        self.a.history = [
            {"role": "user", "content": "old", "timestamp": datetime.now()}
        ]

    def test_quick_response_short_circuits_llm(self):
        with mock.patch.object(asst.llm_router, "generate") as gen:
            out = self.a._llm_respond("hello", None)
        gen.assert_not_called()
        self.assertIn("Hey Sir!", out)

    def test_online_generate_with_context(self):
        with mock.patch.object(
            asst.llm_router, "generate", return_value="R"
        ) as gen:
            out = self.a._llm_respond("tell me a story", "memctx")
        self.assertEqual(out, "R")
        args, kwargs = gen.call_args
        self.assertEqual(args[0], "tell me a story")
        self.assertEqual(args[1], self.a.model)
        self.assertEqual(args[2], self.a.history)
        extra = kwargs["extra_context"]
        self.assertIn("[Memory]\nmemctx", extra)
        self.assertIn("[Recent]", extra)
        self.assertIn("user: old", extra)
        self.assertIsNone(kwargs["system_prompt"])
        self.assertFalse(kwargs["force_offline"])

    def test_no_context_means_empty_extra(self):
        with mock.patch.object(asst.llm_router, "generate", return_value="R") as gen:
            self.a._llm_respond("tell me a story", None)
        self.assertEqual(gen.call_args.kwargs["extra_context"], "")

    def test_history_argument_is_a_copy(self):
        with mock.patch.object(asst.llm_router, "generate", return_value="R") as gen:
            self.a._llm_respond("tell me a story", None)
        hist = gen.call_args.args[2]
        self.assertEqual(hist, self.a.history)
        self.assertIsNot(hist, self.a.history)

    def test_girlfriend_mode_uses_system_prompt(self):
        self.a.girlfriend_mode = True
        with mock.patch.object(asst.llm_router, "generate", return_value="R") as gen:
            self.a._llm_respond("tell me a story", None)
        self.assertEqual(
            gen.call_args.kwargs["system_prompt"], asst.GIRLFRIEND_SYSTEM_PROMPT
        )

    def test_offline_mode_routes_to_generate_offline(self):
        self.a.offline_mode = True
        with mock.patch.object(asst.llm_router, "generate") as gen, \
                mock.patch.object(
                    asst.llm_router, "generate_offline", return_value="OFF"
        ) as off:
            out = self.a._llm_respond("tell me a story", None)
        self.assertEqual(out, "OFF")
        gen.assert_not_called()
        args, kwargs = off.call_args
        self.assertEqual(args[0], "tell me a story")
        self.assertEqual(args[1], self.a.model)
        self.assertIn("extra_context", kwargs)
        self.assertIn("system_prompt", kwargs)

    def test_force_offline_routes_to_generate_offline(self):
        self.a.force_offline = True
        with mock.patch.object(asst.llm_router, "generate") as gen, \
                mock.patch.object(
                    asst.llm_router, "generate_offline", return_value="OFF"
        ) as off:
            out = self.a._llm_respond("tell me a story", None)
        self.assertEqual(out, "OFF")
        gen.assert_not_called()
        off.assert_called_once()


class TestQuickResponses(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_core_entries(self):
        r = self.a._get_quick_responses()
        self.assertEqual(r["hello"], "Hey Sir! Ready to roll.")
        self.assertEqual(r["good night"], "Good night Sir. I'll be here when you wake.")
        self.assertEqual(r["thank you"], "Always, Sir.")
        self.assertIn("ORBIT", r["who are you"])
        self.assertEqual(r["status"], "All systems nominal. ORBIT 3.0 standing by.")

    def test_girlfriend_prefix(self):
        self.a.girlfriend_mode = True
        r = self.a._get_quick_responses()
        self.assertEqual(r["hello"], "Hey Baby! Ready to roll.")

    def test_cached_response_is_case_and_space_insensitive(self):
        self.assertEqual(
            self.a._get_cached_response("  HELLO "), self.a._get_quick_responses()["hello"]
        )

    def test_cached_response_unknown_is_none(self):
        self.assertIsNone(self.a._get_cached_response("quantum banana"))


class TestTalkBack(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()
        patcher_em = mock.patch.object(
            asst.emotions, "emotion_for_intent", return_value="joy"
        )
        patcher_face = mock.patch.object(asst.emotions, "get_emotion", return_value="X")
        self.addCleanup(patcher_em.stop)
        self.addCleanup(patcher_face.stop)
        patcher_em.start()
        patcher_face.start()

    def test_screen_returns_raw(self):
        self.assertEqual(self.a._talk_back("screen", "describe", "RES"), "RES")

    def test_screen_share_returns_raw(self):
        self.assertEqual(self.a._talk_back("screen_share", "share", "RES"), "RES")

    def test_computer_kill(self):
        out = self.a._talk_back("computer", "kill notepad", "done")
        self.assertEqual(out, "X Sir, process kill kar diya!")

    def test_computer_process(self):
        out = self.a._talk_back("computer", "show processes", "P1")
        self.assertIn("running processes:", out)
        self.assertIn("P1", out)

    def test_computer_files(self):
        out = self.a._talk_back("computer", "list files", "F1")
        self.assertIn("files:", out)

    def test_computer_system_info(self):
        out = self.a._talk_back("computer", "system info", "S1")
        self.assertIn("system info:", out)

    def test_computer_default(self):
        out = self.a._talk_back("computer", "do anything", "D1")
        self.assertIn("done!", out)

    def test_news(self):
        out = self.a._talk_back("news", "headlines", "N1")
        self.assertEqual(out, "X Sir, headlines:\nN1")

    def test_security_port(self):
        out = self.a._talk_back("security", "scan ports", "P")
        self.assertIn("open ports:", out)

    def test_security_firewall(self):
        out = self.a._talk_back("security", "firewall status", "F")
        self.assertIn("firewall:", out)

    def test_security_default(self):
        out = self.a._talk_back("security", "check", "S")
        self.assertIn("security:", out)

    def test_cai_n8n_memory_share_format(self):
        for intent in ("cai", "n8n", "memory"):
            out = self.a._talk_back(intent, "x", "R")
            self.assertEqual(out, f"X Sir:\nR", intent)

    def test_pipeline(self):
        out = self.a._talk_back("pipeline", "x", "R")
        self.assertIn("pipeline complete!", out)

    def test_unknown_intent_default(self):
        out = self.a._talk_back("quote", "x", "R")
        self.assertEqual(out, "X Sir:\nR")

    def test_girlfriend_prefix(self):
        self.a.girlfriend_mode = True
        out = self.a._talk_back("news", "x", "R")
        self.assertIn("Baby, headlines:", out)


class TestPrefix(unittest.TestCase):
    def test_default_title(self):
        self.assertEqual(make_assistant()._get_prefix(), "Sir")

    def test_girlfriend_mode(self):
        a = make_assistant()
        a.girlfriend_mode = True
        self.assertEqual(a._get_prefix(), "Baby")


class TestProcess(unittest.TestCase):
    """_process: queen orchestration -> tool fallback -> LLM, plus history,
    skill counters, pending-cleanup reminder and the speak path."""

    def setUp(self):
        self.a = make_assistant()

    def _stack(self, intent="chat", pending=0):
        s = ExitStack()
        m = {}
        m["track"] = s.enter_context(mock.patch.object(asst.usage_tracker, "track_message"))
        m["brief"] = s.enter_context(
            mock.patch.object(asst.usage_tracker, "get_brief", return_value="BRIEF")
        )
        s.enter_context(mock.patch.object(asst.proactive, "reset_cooldown"))
        s.enter_context(
            mock.patch.object(asst.memory_module, "get_context_str", return_value="ctx")
        )
        s.enter_context(mock.patch.object(asst.memory_module, "save_conversation"))
        m["pending"] = s.enter_context(
            mock.patch.object(
                asst.memory_module, "count_pending_cleanup", return_value=pending
            )
        )
        s.enter_context(mock.patch.object(asst.conv_module, "index_message"))
        s.enter_context(
            mock.patch.object(asst, "agent_label_for_intent", return_value="LBL")
        )
        m["emit_msg"] = s.enter_context(mock.patch.object(self.a, "_emit_message"))
        m["emit_status"] = s.enter_context(mock.patch.object(self.a, "_emit_status"))
        m["emit_agent"] = s.enter_context(mock.patch.object(self.a, "_emit_agent"))
        if intent is not None:
            m["detect"] = s.enter_context(
                mock.patch.object(self.a, "_detect_intent", return_value=intent)
            )
        return s, m

    def _queen(self, s, ok=True, output=None, exc=None):
        if exc is not None:
            return s.enter_context(
                mock.patch(
                    "orbit.orbit.core.agent_contract.run_agent_instance",
                    side_effect=exc,
                )
            )
        result = mock.MagicMock()
        result.ok = ok
        result.output = output
        return s.enter_context(
            mock.patch(
                "orbit.orbit.core.agent_contract.run_agent_instance",
                return_value=result,
            )
        )

    def test_queen_success_short_circuits_chat(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=True, output="QUEEN!")
            with mock.patch.object(self.a, "_handle_tool") as tool, \
                    mock.patch.object(self.a, "_llm_respond") as llm:
                reply = self.a._process("hello")
        self.assertEqual(reply, "QUEEN!")
        m["emit_agent"].assert_called_once_with("QNN")
        tool.assert_not_called()
        llm.assert_not_called()

    def test_queen_success_nonchat_emits_agent_label(self):
        stack, m = self._stack(intent="news")
        with stack:
            self._queen(stack, ok=True, output="Q")
            reply = self.a._process("news please")
        self.assertEqual(reply, "Q")
        m["emit_agent"].assert_called_once_with("LBL")

    def test_queen_failure_falls_back_to_tool(self):
        stack, m = self._stack(intent="news")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(
                self.a, "_handle_tool", return_value="HEAD"
            ) as tool, mock.patch.object(
                self.a, "_talk_back", return_value="TALKED"
            ) as talk, mock.patch.object(self.a, "_llm_respond") as llm:
                reply = self.a._process("news")
        tool.assert_called_once_with("news", "news")
        talk.assert_called_once_with("news", "news", "HEAD")
        llm.assert_not_called()
        self.assertEqual(reply, "TALKED")

    def test_queen_error_output_falls_back(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=True, output="[Error: kaputt]")
            with mock.patch.object(
                self.a, "_llm_respond", return_value="LLM"
            ) as llm:
                reply = self.a._process("hello")
        llm.assert_called_once()
        self.assertEqual(reply, "LLM")

    def test_queen_exception_falls_back(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, exc=RuntimeError("boom"))
            with mock.patch.object(
                self.a, "_llm_respond", return_value="LLM"
            ) as llm:
                reply = self.a._process("hello")
        llm.assert_called_once()
        self.assertEqual(reply, "LLM")

    def test_chat_intent_never_calls_tool(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_handle_tool") as tool, \
                    mock.patch.object(
                        self.a, "_llm_respond", return_value="LLM"
            ) as llm:
                reply = self.a._process("hello")
        tool.assert_not_called()
        llm.assert_called_once()
        self.assertEqual(reply, "LLM")

    def test_empty_tool_reply_uses_llm(self):
        stack, m = self._stack(intent="news")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_handle_tool", return_value=""), \
                    mock.patch.object(
                        self.a, "_llm_respond", return_value="LLM"
            ) as llm:
                reply = self.a._process("news")
        llm.assert_called_once()
        self.assertEqual(reply, "LLM")

    def test_none_reply_replaced_by_default(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_llm_respond", return_value="X"), \
                    mock.patch.object(self.a, "_check_model_error", return_value=None):
                reply = self.a._process("hello")
        self.assertEqual(reply, "⚠️ No response from model. Please try again.")

    def test_history_appended_and_trimmed_to_50(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_llm_respond", return_value="R"):
                self.a.history = [
                    {"role": "user", "content": f"m{i}", "timestamp": datetime.now()}
                    for i in range(50)
                ]
                self.a._first_reply = False  # avoid brief injection into content
                self.a._process("hello")
        self.assertEqual(len(self.a.history), 50)
        self.assertEqual(self.a.history[-1]["role"], "assistant")
        self.assertEqual(self.a.history[-1]["content"], "R")
        self.assertEqual(self.a.history[-2]["content"], "hello")

    def test_first_reply_injects_brief(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(
                        self.a, "_llm_respond", return_value="R"
            ) as llm:
                self.a._process("hello")
                self.a._process("hello again")
        first_text = llm.call_args_list[0].args[0]
        second_text = llm.call_args_list[1].args[0]
        self.assertEqual(first_text, "BRIEF\n\nUser: hello")
        self.assertEqual(second_text, "hello again")
        self.assertFalse(self.a._first_reply)

    def test_first_reply_not_consumed_for_non_chat(self):
        stack, m = self._stack(intent="news")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_handle_tool", return_value="N"), \
                    mock.patch.object(self.a, "_talk_back", return_value="T"):
                self.a._process("news")
        self.assertTrue(self.a._first_reply)

    def test_skill_counts_increment(self):
        stack, m = self._stack(intent="news")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_handle_tool", return_value="N"), \
                    mock.patch.object(self.a, "_talk_back", return_value="T"):
                self.a._process("news")
                self.a._process("news")
        self.assertEqual(self.a.skill_counts["news"], 2)
        self.assertEqual(self.a.skill_counts["voice"], 0)

    def test_voice_skill_counts_when_speaking(self):
        stack, m = self._stack(intent="news")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_handle_tool", return_value="N"), \
                    mock.patch.object(self.a, "_talk_back", return_value="T"):
                self.a._process("news", speak_it=True)
        self.assertEqual(self.a.skill_counts["voice"], 1)

    def test_unknown_skill_intent_does_not_crash(self):
        stack, m = self._stack(intent="not_a_skill")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_handle_tool", return_value="N"), \
                    mock.patch.object(self.a, "_talk_back", return_value="T"):
                reply = self.a._process("x")
        self.assertEqual(reply, "T")

    def test_pending_cleanup_reminder_appended(self):
        stack, m = self._stack(intent="chat", pending=3)
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_llm_respond", return_value="R"):
                reply = self.a._process("hello")
        self.assertIn("🧹 **3 memories**", reply)
        self.assertIn(str(asst.memory_module.MAX_AGE_DAYS), reply)

    def test_no_reminder_for_memory_intent(self):
        stack, m = self._stack(intent="memory", pending=3)
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_handle_tool", return_value="M"), \
                    mock.patch.object(self.a, "_talk_back", return_value="T"):
                reply = self.a._process("clear old memories")
        self.assertEqual(reply, "T")

    def test_speak_path_sends_sentiment(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_llm_respond", return_value="OK"), \
                    mock.patch.object(asst, "detect_sentiment", return_value="positive") as sent, \
                    mock.patch.object(asst.tts, "speak") as speak:
                self.a.tts_engine = "pyttsx3"
                self.a._first_reply = False  # skip brief injection
                reply = self.a._process("hello", speak_it=True)
        self.assertEqual(reply, "OK")
        sent.assert_called_once_with("hello")
        m["emit_status"].assert_any_call("speaking", "Speaking...")
        speak.assert_called_once_with(
            "OK", self.a.tts_voice, self.a.tts_speed, offline=False,
            sentiment="positive",
        )

    def test_bracket_reply_never_spoken(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_llm_respond", return_value="[Error: x]"), \
                    mock.patch.object(asst.tts, "speak") as speak:
                reply = self.a._process("hello", speak_it=True)
        speak.assert_not_called()
        for call in m["emit_status"].call_args_list:
            self.assertNotEqual(call.args[0], "speaking")

    def test_tts_failure_does_not_break_reply(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_llm_respond", return_value="OK"), \
                    mock.patch.object(
                        asst.tts, "speak", side_effect=RuntimeError("no audio")
            ):
                reply = self.a._process("hello", speak_it=True)
        self.assertEqual(reply, "OK")

    def test_no_speak_status_when_speak_it_false(self):
        stack, m = self._stack(intent="chat")
        with stack:
            self._queen(stack, ok=False)
            with mock.patch.object(self.a, "_cleanup_old_history"), \
                    mock.patch.object(self.a, "_llm_respond", return_value="OK"), \
                    mock.patch.object(asst.tts, "speak") as speak:
                self.a._process("hello", speak_it=False)
        speak.assert_not_called()
        m["emit_status"].assert_not_called()


class TestListenAndRespond(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_reentrant_guard(self):
        self.a.listening = True
        with mock.patch.object(asst.stt, "listen") as listen, \
                mock.patch.object(self.a, "_emit_status") as es:
            out = self.a.listen_and_respond()
        self.assertIsNone(out)
        listen.assert_not_called()
        es.assert_not_called()
        self.assertTrue(self.a.listening)

    def test_none_heard(self):
        with mock.patch.object(asst.stt, "listen", return_value=None), \
                mock.patch.object(self.a, "_emit_status") as es:
            out = self.a.listen_and_respond()
        self.assertIsNone(out)
        es.assert_any_call("listening", "Listening...")
        es.assert_any_call("idle", "Ready")
        self.assertFalse(self.a.listening)

    def test_bracket_error_string(self):
        with mock.patch.object(
            asst.stt, "listen", return_value="[error: mic busy]"
        ), mock.patch.object(self.a, "_emit_message") as em, \
                mock.patch.object(self.a, "_emit_status") as es:
            out = self.a.listen_and_respond()
        self.assertIsNone(out)
        em.assert_called_once_with("assistant", "[error: mic busy]")
        es.assert_any_call("idle", "Ready")

    def test_empty_string(self):
        with mock.patch.object(asst.stt, "listen", return_value=""), \
                mock.patch.object(self.a, "_emit_status") as es:
            out = self.a.listen_and_respond()
        self.assertEqual(out, "")
        es.assert_any_call("idle", "Couldn't understand")
        self.assertFalse(self.a.listening)

    def test_success_flow(self):
        with mock.patch.object(
            asst.stt, "listen", return_value="hello world"
        ) as listen, mock.patch.object(self.a, "_emit_message") as em, \
                mock.patch.object(self.a, "_emit_status") as es, \
                mock.patch.object(self.a, "_process", return_value="R") as proc:
            out = self.a.listen_and_respond()
        self.assertEqual(out, "R")
        listen.assert_called_once_with(
            mf_index=None, offline=False
        )
        em.assert_any_call("user", "hello world")
        es.assert_any_call("thinking", "Thinking...")
        es.assert_any_call("idle", "Ready")
        proc.assert_called_once_with("hello world", speak_it=True)
        self.assertFalse(self.a.listening)

    def test_speak_responses_off(self):
        self.a.speak_responses = False
        with mock.patch.object(asst.stt, "listen", return_value="hi"), \
                mock.patch.object(self.a, "_emit_message"), \
                mock.patch.object(self.a, "_emit_status"), \
                mock.patch.object(self.a, "_process", return_value="R") as proc:
            self.a.listen_and_respond()
        proc.assert_called_once_with("hi", speak_it=False)

    def test_process_exception_returns_none_and_resets_flag(self):
        with mock.patch.object(asst.stt, "listen", return_value="hi"), \
                mock.patch.object(self.a, "_emit_message"), \
                mock.patch.object(self.a, "_emit_status") as es, \
                mock.patch.object(
                    self.a, "_process", side_effect=RuntimeError("kaputt")
            ):
            out = self.a.listen_and_respond()
        self.assertIsNone(out)
        es.assert_any_call("idle", "Ready")
        self.assertFalse(self.a.listening)

    def test_listen_exception_returns_none(self):
        with mock.patch.object(
            asst.stt, "listen", side_effect=RuntimeError("device gone")
        ), mock.patch.object(self.a, "_emit_status") as es:
            out = self.a.listen_and_respond()
        self.assertIsNone(out)
        es.assert_any_call("idle", "Ready")
        self.assertFalse(self.a.listening)


class TestSendText(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_flow(self):
        with mock.patch.object(self.a, "_emit_message") as em, \
                mock.patch.object(self.a, "_emit_status") as es, \
                mock.patch.object(self.a, "_process", return_value="R") as proc:
            out = self.a.send_text("hi there")
        self.assertEqual(out, "R")
        em.assert_called_once_with("user", "hi there")
        es.assert_any_call("thinking", "Thinking...")
        es.assert_any_call("idle", "Ready")
        proc.assert_called_once_with("hi there", speak_it=True)

    def test_speak_responses_off(self):
        self.a.speak_responses = False
        with mock.patch.object(self.a, "_emit_message"), \
                mock.patch.object(self.a, "_emit_status"), \
                mock.patch.object(self.a, "_process", return_value="R") as proc:
            self.a.send_text("hi")
        proc.assert_called_once_with("hi", speak_it=False)


class TestClearHistory(unittest.TestCase):
    def test_clear_normal(self):
        a = make_assistant()
        a.history = [{"role": "user", "content": "x"}]
        with mock.patch.object(a, "_emit_message") as em:
            a.clear_history()
        self.assertEqual(a.history, [])
        em.assert_called_once_with("assistant", "🧹 Chat history cleared, Sir!")

    def test_clear_girlfriend(self):
        a = make_assistant()
        a.girlfriend_mode = True
        a.history = [{"role": "user", "content": "x"}]
        with mock.patch.object(a, "_emit_message") as em:
            a.clear_history()
        em.assert_called_once_with(
            "assistant", f"🧹 Chat clear, Baby! - {asst.GF_NAME}"
        )


class TestModelError(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_empty_reply_passes_through(self):
        self.assertIsNone(self.a._check_model_error(None))
        self.assertEqual(self.a._check_model_error(""), "")

    def test_image_phrases_replaced(self):
        expected = (
            "⚠️ Current model image nahi samajhta. "
            "Use `ollama pull llava` for vision support."
        )
        for phrase in (
            "This model does not support images",
            "I cannot read the screenshot",
            "image input is required",
            "multimodal models only",
        ):
            self.assertEqual(self.a._check_model_error(phrase), expected, phrase)

    def test_case_insensitive_match(self):
        self.assertIn("ollama pull llava", self.a._check_model_error("MODEL CANNOT READ"))

    def test_normal_reply_untouched(self):
        self.assertEqual(self.a._check_model_error("all good"), "all good")


class TestSkillLevels(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_defaults(self):
        levels = self.a.get_skill_levels()
        self.assertEqual(levels["Computer"], 0.5)
        self.assertEqual(levels["Vision"], 0.3)
        self.assertEqual(levels["Love"], 0.3)
        self.assertEqual(levels["Emotions"], 0.5)

    def test_high_count_saturates(self):
        self.a.skill_counts["computer"] = 10_000
        levels = self.a.get_skill_levels()
        self.assertEqual(levels["Computer"], 1.0)

    def test_girlfriend_love_level(self):
        self.a.girlfriend_mode = True
        self.assertEqual(self.a.get_skill_levels()["Love"], 0.7)


class TestOllamaAndRouter(unittest.TestCase):
    def setUp(self):
        self.a = make_assistant()

    def test_check_ollama_empty(self):
        with mock.patch.object(
            asst.llm_router, "list_ollama_models", return_value=[]
        ):
            ok, models = self.a.check_ollama()
        self.assertFalse(ok)
        self.assertEqual(models, [])

    def test_check_ollama_with_models(self):
        with mock.patch.object(
            asst.llm_router, "list_ollama_models", return_value=["qwen3:1.7b"]
        ):
            ok, models = self.a.check_ollama()
        self.assertTrue(ok)
        self.assertEqual(models, ["qwen3:1.7b"])

    def test_get_router_status(self):
        status = {"online": True}
        with mock.patch.object(asst.llm_router, "get_status", return_value=status):
            self.assertEqual(self.a.get_router_status(), status)


class TestSingleton(unittest.TestCase):
    def test_get_assistant_is_singleton(self):
        with mock.patch.object(asst, "_assistant_singleton", None), \
                mock.patch.object(asst, "Assistant") as cls:
            first = asst.get_assistant()
            second = asst.get_assistant()
        cls.assert_called_once_with()
        self.assertIs(first, second)

    def test_existing_singleton_returned_as_is(self):
        sentinel = object()
        with mock.patch.object(asst, "_assistant_singleton", sentinel), \
                mock.patch.object(asst, "Assistant") as cls:
            out = asst.get_assistant()
        cls.assert_not_called()
        self.assertIs(out, sentinel)


class TestCaiImportFallback(unittest.TestCase):
    def test_fallback_definitions_when_cai_security_missing(self):
        real_import = builtins.__import__

        def blocked(name, globals=None, locals=None, fromlist=(), level=0):
            if "cai_security" in str(name) or "cai_security" in str(fromlist):
                raise ImportError("blocked for test")
            return real_import(name, globals, locals, fromlist, level)

        try:
            with mock.patch("builtins.__import__", side_effect=blocked):
                importlib.reload(asst)
            self.assertEqual(asst.cai_analyze("scan"), "CAI module unavailable")
            self.assertEqual(asst.cai_audit(), "CAI module unavailable")
            self.assertEqual(asst.cai_threat(), "CAI module unavailable")
        finally:
            importlib.reload(asst)  # restore the real bindings
