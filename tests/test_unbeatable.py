"""Tests for Operation Demons Army v2 — streaming TTS, multi-candidate, wake eval, proactive screen."""

import threading
import time


# ── Wave 1: Streaming TTS ──────────────────────────────────────────────────


class TestStreamingTTS:
    def test_singleton(self):
        from orbit.orbit.core.streaming_tts import get_streaming_tts

        a = get_streaming_tts()
        b = get_streaming_tts()
        assert a is b

    def test_feed_token_accumulates(self):
        from orbit.orbit.core.streaming_tts import StreamingTTSEngine

        eng = StreamingTTSEngine()
        eng.feed_token("Hello")
        eng.feed_token(" world")
        assert eng._buffer == "Hello world"
        assert len(eng._queue) == 0  # no sentence boundary yet

    def test_sentence_splitting(self):
        from orbit.orbit.core.streaming_tts import StreamingTTSEngine

        eng = StreamingTTSEngine()
        eng.feed_token("Hello world. ")
        assert len(eng._queue) == 1
        assert eng._queue[0] == "Hello world."
        assert eng._buffer == ""

    def test_multiple_sentences(self):
        from orbit.orbit.core.streaming_tts import StreamingTTSEngine

        eng = StreamingTTSEngine()
        eng.feed_token("First sentence. Second sentence! ")
        assert len(eng._queue) == 2

    def test_flush_remaining(self):
        from orbit.orbit.core.streaming_tts import StreamingTTSEngine

        eng = StreamingTTSEngine()
        eng.feed_token("No period here")
        assert len(eng._queue) == 0
        eng.flush()
        assert len(eng._queue) == 1
        assert eng._queue[0] == "No period here"

    def test_min_chars_filter(self):
        from orbit.orbit.core.streaming_tts import StreamingTTSEngine

        eng = StreamingTTSEngine()
        eng.feed_token("A. ")  # "A." = 2 chars < _MIN_CHARS=3
        assert len(eng._queue) == 0  # too short, filtered

    def test_stats(self):
        from orbit.orbit.core.streaming_tts import StreamingTTSEngine

        eng = StreamingTTSEngine()
        stats = eng.get_stats()
        assert stats["started"] is False
        assert stats["queue_len"] == 0

    def test_stop_clears_state(self):
        from orbit.orbit.core.streaming_tts import StreamingTTSEngine

        eng = StreamingTTSEngine()
        eng.feed_token("Hello world. ")
        eng.stop()
        assert len(eng._queue) == 0
        assert eng._buffer == ""


# ── Wave 2: Multi-candidate creative ──────────────────────────────────────


class TestMultiCandidate:
    def test_tokenize(self):
        from orbit.orbit.core.multi_candidate import _tokenize

        tokens = _tokenize("Hello, World! This is a test.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_creativity_score(self):
        from orbit.orbit.core.multi_candidate import _creativity_score

        diverse = "Ephemeral cascades shimmer beneath twilight obsidian horizons"
        repetitive = "the the the the the the the the"
        assert _creativity_score(diverse) > _creativity_score(repetitive)

    def test_relevance_score(self):
        from orbit.orbit.core.multi_candidate import _relevance_score

        prompt = "Write a haiku about rain"
        good = "Soft rain falls on leaves, nature weeps in silver streams"
        bad = "The quick brown fox jumps over the lazy dog"
        assert _relevance_score(prompt, good) > _relevance_score(prompt, bad)

    def test_fitness_score(self):
        from orbit.orbit.core.multi_candidate import _fitness_score

        assert _fitness_score("Short but fine sentence here.") == 1.0
        assert _fitness_score("x") < 1.0  # too short
        assert _fitness_score(" ".join(["word"] * 200)) < 1.0  # too long

    def test_score_candidate_structure(self):
        from orbit.orbit.core.multi_candidate import score_candidate

        s = score_candidate("Write a poem about stars", "Stars twinkle in the vast cosmic night")
        assert "creativity" in s
        assert "relevance" in s
        assert "fitness" in s
        assert "total" in s
        assert 0 <= s["total"] <= 1

    def test_is_creative_query(self):
        from orbit.orbit.core.multi_candidate import is_creative_query

        assert is_creative_query("Write a haiku about rain")
        assert is_creative_query("Tell me a joke about programmers")
        assert is_creative_query("Give me a tagline for a coffee shop")
        assert not is_creative_query("What is 2+2?")
        assert not is_creative_query("Explain quantum computing")

    def test_generate_best_creative_fallback(self):
        from orbit.orbit.core.multi_candidate import generate_best_creative

        # n=1 uses single-candidate path (no parallel, no LLM call needed if empty)
        best, meta = generate_best_creative("test prompt", n=1)
        assert meta["n"] == 1
        assert "scores" in meta


# ── Wave 3: Wake word eval ────────────────────────────────────────────────


class TestWakeEval:
    def test_sine_wave_generation(self):
        from orbit.orbit.core.wake_eval import _sine_wave, SAMPLE_RATE

        samples = _sine_wave(440, 100)  # 100ms
        assert len(samples) == SAMPLE_RATE * 100 // 1000
        assert any(s != 0 for s in samples)

    def test_noise_generation(self):
        from orbit.orbit.core.wake_eval import _noise, SAMPLE_RATE

        samples = _noise(100)
        assert len(samples) == SAMPLE_RATE * 100 // 1000

    def test_silence_generation(self):
        from orbit.orbit.core.wake_eval import _silence

        samples = _silence(100)
        assert all(s == 0 for s in samples)

    def test_speech_like_generation(self):
        from orbit.orbit.core.wake_eval import _speech_like, SAMPLE_RATE

        samples = _speech_like(200)
        assert len(samples) == SAMPLE_RATE * 200 // 1000
        assert any(s != 0 for s in samples)

    def test_frame_energy(self):
        from orbit.orbit.core.wake_eval import _frame_energy

        assert _frame_energy([0, 0, 0, 0]) == 0.0
        assert _frame_energy([1000, 1000, 1000, 1000]) > 0

    def test_to_frames(self):
        from orbit.orbit.core.wake_eval import _to_frames

        samples = list(range(1000))
        frames = _to_frames(samples, frame_size=100)
        assert len(frames) == 10
        assert len(frames[0]) == 100

    def test_run_far_frr_eval(self):
        from orbit.orbit.core.wake_eval import run_far_frr_eval

        report = run_far_frr_eval(
            energy_thresholds=[500, 1000],
            confidence_thresholds=[0.5, 0.7],
        )
        assert "sweep_results" in report
        assert "best_operating_point" in report
        assert "summary" in report
        assert report["n_positive"] > 0
        assert report["n_negative"] > 0
        assert len(report["sweep_results"]) == 4  # 2x2 sweep

    def test_best_operating_point_valid(self):
        from orbit.orbit.core.wake_eval import run_far_frr_eval

        report = run_far_frr_eval()
        best = report["best_operating_point"]
        assert best is not None
        assert 0 <= best["far"] <= 1
        assert 0 <= best["frr"] <= 1
        assert 0 <= best["eer"] <= 1

    def test_get_current_config(self):
        from orbit.orbit.core.wake_eval import get_current_config

        cfg = get_current_config()
        assert "energy_threshold" in cfg
        assert "confidence_threshold" in cfg


# ── Wave 4: Proactive screen ──────────────────────────────────────────────


class TestProactiveScreen:
    def test_singleton(self):
        from orbit.orbit.core.proactive_screen import get_proactive_screen

        a = get_proactive_screen()
        b = get_proactive_screen()
        assert a is b

    def test_status_initial(self):
        from orbit.orbit.core.proactive_screen import get_proactive_screen

        ps = get_proactive_screen()
        status = ps.get_status()
        assert "running" in status
        assert "captures" in status

    def test_inject_suggestion(self):
        from orbit.orbit.core.proactive_screen import ProactiveScreen

        ps = ProactiveScreen()
        ps.inject_suggestion("test_pattern", "Test suggestion text", "high")
        suggestions = ps.get_suggestions()
        assert len(suggestions) == 1
        assert suggestions[0]["pattern"] == "test_pattern"
        assert suggestions[0]["priority"] == "high"

    def test_cooldown(self):
        from orbit.orbit.core.proactive_screen import ProactiveScreen

        ps = ProactiveScreen()
        # First trigger should pass
        assert ps._cooldown_ok("test_pattern") is True
        # Second immediate trigger should be blocked
        assert ps._cooldown_ok("test_pattern") is False

    def test_detect_patterns_error(self):
        from orbit.orbit.core.proactive_screen import ProactiveScreen

        ps = ProactiveScreen()
        patterns = ps._detect_patterns("An error occurred: ValueError in module X")
        assert any(p[0] == "error_dialog" for p in patterns)

    def test_detect_patterns_build(self):
        from orbit.orbit.core.proactive_screen import ProactiveScreen

        ps = ProactiveScreen()
        patterns = ps._detect_patterns("Compiling main.c... linking...")
        assert any(p[0] == "build_running" for p in patterns)

    def test_detect_patterns_clean(self):
        from orbit.orbit.core.proactive_screen import ProactiveScreen

        ps = ProactiveScreen()
        patterns = ps._detect_patterns("Just a normal text document, nothing special")
        assert len(patterns) == 0

    def test_start_stop(self):
        from orbit.orbit.core.proactive_screen import ProactiveScreen

        ps = ProactiveScreen()
        ps.start(interval_sec=999)  # long interval so it doesn't actually capture
        assert ps._running is True
        ps.stop()
        assert ps._running is False


# ── API blueprint ─────────────────────────────────────────────────────────


class TestUnbeatableAPI:
    def _app(self):
        from orbit.orbit.server import create_app

        app = create_app()
        app.config["TESTING"] = True
        return app

    def test_status_endpoint(self):
        client = self._app().test_client()
        resp = client.get("/api/unbeatable/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "streaming_tts" in data
        assert "multi_candidate" in data
        assert "proactive_screen" in data

    def test_wake_eval_endpoint(self):
        client = self._app().test_client()
        resp = client.post("/api/unbeatable/wake-eval", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sweep_results" in data
        assert "live_config" in data

    def test_wake_eval_apply_dry_run(self):
        client = self._app().test_client()
        resp = client.post("/api/unbeatable/wake-eval/apply", json={"dry_run": True})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["applied"] is False
        assert "would_apply" in data

    def test_creative_endpoint_requires_prompt(self):
        client = self._app().test_client()
        resp = client.post("/api/unbeatable/creative", json={})
        assert resp.status_code == 400

    def test_proactive_screen_suggestions(self):
        client = self._app().test_client()
        resp = client.get("/api/unbeatable/proactive-screen/suggestions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "suggestions" in data


# ── "Best" pass regression tests ─────────────────────────────────────────


class TestStreamingSSEContract:
    def test_complete_payload_has_tts_streamed_key(self):
        """The SSE complete path must be able to set tts_streamed (double-speak guard)."""
        import inspect
        from orbit.orbit.core import chat_api

        src = inspect.getsource(chat_api.chat_stream)
        assert 'item["done"]["tts_streamed"] = True' in src
        # Non-blocking: no drain with a multi-second timeout in the SSE loop
        assert "drain(timeout=8.0)" not in src

    def test_frontend_guards_autospeak(self):
        from pathlib import Path

        app_jsx = Path(r"D:\JARVES\ui_provided\src\App.jsx").read_text(encoding="utf-8")
        assert "tts_streamed" in app_jsx
        assert "!newMsg.tts_streamed" in app_jsx


class TestWakeTuning:
    def test_apply_tuning_persists(self, tmp_path, monkeypatch):
        import orbit.orbit.wake_word as ww

        target = tmp_path / "wake_tuning.json"
        monkeypatch.setattr(ww, "_tuning_file", lambda: str(target))
        applied = ww.apply_tuning(energy_threshold=1234, confidence_threshold=0.85)
        assert applied["energy_threshold"] == 1234
        assert applied["confidence_threshold"] == 0.85
        assert ww.ENERGY_THRESHOLD == 1234
        assert target.exists()

        # Restore module globals so other tests see defaults
        ww.ENERGY_THRESHOLD = 500
        ww.CONFIDENCE_THRESHOLD = 0.7

    def test_apply_tuning_leaves_none_untouched(self, tmp_path, monkeypatch):
        import orbit.orbit.wake_word as ww

        target = tmp_path / "wake_tuning.json"
        monkeypatch.setattr(ww, "_tuning_file", lambda: str(target))
        before = ww.OWW_THRESHOLD
        applied = ww.apply_tuning()  # all None → no change
        assert applied["oww_threshold"] == before
        assert ww.OWW_THRESHOLD == before

    def test_load_tuning_env_wins(self, tmp_path, monkeypatch):
        import orbit.orbit.wake_word as ww

        target = tmp_path / "wake_tuning.json"
        target.write_text('{"energy_threshold": 9999}', encoding="utf-8")
        monkeypatch.setattr(ww, "_tuning_file", lambda: str(target))
        monkeypatch.setenv("WAKE_ENERGY_THRESHOLD", "500")  # env set → env wins
        before = ww.ENERGY_THRESHOLD
        ww._load_tuning()
        assert ww.ENERGY_THRESHOLD == before  # unchanged — env wins


class TestProactiveNotificationBridge:
    def test_add_suggestion_pushes_notification(self):
        from orbit.orbit.core.proactive_screen import ProactiveScreen

        ps = ProactiveScreen()
        ps.inject_suggestion("test_bridge", "Bridge suggestion text", "high")
        from orbit.orbit.core.notification_center import get_notification_center

        notes = get_notification_center().get_notifications(limit=10)
        assert any(n.get("source") == "proactive_screen" for n in notes)

    def test_broken_center_never_breaks_add(self, monkeypatch):
        """Fail-open: a broken notification center must not raise from _add_suggestion."""
        from orbit.orbit.core import proactive_screen as ps_mod

        def _boom():
            raise RuntimeError("center down")

        monkeypatch.setattr(
            "orbit.orbit.core.notification_center.get_notification_center",
            lambda: (_ for _ in ()).throw(RuntimeError("center down")),
        )
        ps = ps_mod.ProactiveScreen()
        ps.inject_suggestion("fail_open", "Still added", "low")  # must not raise
        assert any(s["pattern"] == "fail_open" for s in ps.get_suggestions())


class TestMultiCandidateErrorGuard:
    def test_error_strings_score_empty(self, monkeypatch):
        """Router [Error: ...] results must not win the candidate contest."""
        from orbit.orbit.core import multi_candidate as mc
        from orbit.orbit.core.llm import legacy_adapter

        monkeypatch.setattr(
            legacy_adapter, "generate", lambda *a, **k: "[Error: All providers unavailable]"
        )
        assert mc._generate_one("test", "", None, "A") == ""

    def test_provider_down_strings_score_empty(self, monkeypatch):
        from orbit.orbit.core import multi_candidate as mc
        from orbit.orbit.core.llm import legacy_adapter

        monkeypatch.setattr(
            legacy_adapter, "generate", lambda *a, **k: "[All providers unavailable]"
        )
        assert mc._generate_one("test", "", None, "B") == ""
