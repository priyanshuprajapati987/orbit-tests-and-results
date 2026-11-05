"""
Tier 1 Part 3 — Conversation Win Metrics tests.

Covers core/benchmark.py (ChatGPT A/B comparison), core/reasoning_depth.py
(CoT quality scoring) and the benchmark API endpoints.
"""

import asyncio
import os
import time
import unittest
from unittest import mock


class TestMeasureText(unittest.TestCase):
    def test_empty(self):
        from orbit.orbit.core.benchmark import measure_text

        m = measure_text("")
        self.assertEqual(m["words"], 0)
        self.assertEqual(m["sentences"], 0)
        self.assertGreaterEqual(m["estimated_tokens"], 1)

    def test_basic_counts(self):
        from orbit.orbit.core.benchmark import measure_text

        m = measure_text("Hello world. This is a test sentence!")
        self.assertEqual(m["words"], 7)
        self.assertEqual(m["sentences"], 2)
        self.assertEqual(m["estimated_tokens"], 9)

    def test_lexical_diversity(self):
        from orbit.orbit.core.benchmark import measure_text

        m = measure_text("one two three four")
        self.assertGreater(m["lexical_diversity_pct"], 90)
        m2 = measure_text("go go go go go go go go")
        self.assertLess(m2["lexical_diversity_pct"], 40)


class TestOpponents(unittest.TestCase):
    _NO_OVERRIDE = {  # noqa: RUF012
        "OPPONENT_API_KEY": "",
        "OPPONENT_BASE_URL": "",
        "OPPONENT_MODEL": "",
        "OPPONENT_OPENAI_KEY": "",
        "OPPONENT_OPENAI_MODEL": "",
    }

    def _env(self, **extra):
        env = dict(self._NO_OVERRIDE)
        env.update(extra)
        return env

    def test_chatgpt_opponent_unavailable_without_key(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        opp = ChatGPTOpponent(api_key="")
        self.assertFalse(opp.is_available())
        self.assertIsNone(opp.generate("hello"))

    def test_chatgpt_opponent_available_with_key(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        opp = ChatGPTOpponent(api_key="sk-test-123", base_url="http://localhost:1")
        self.assertTrue(opp.is_available())
        self.assertIsNone(opp.generate("hi"))  # connection fails gracefully

    def test_opponent_auto_resolves_gemini_key(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        with mock.patch.dict(
            os.environ,
            self._env(GEMINI_API_KEY="AIzaTest", OPENAI_API_KEY=""),
            clear=False,
        ):
            opp = ChatGPTOpponent()
            self.assertTrue(opp.is_available())
            self.assertEqual(opp.provider_name(), "gemini")
            self.assertIn("generativelanguage", opp.base_url)

    def test_opponent_placeholder_key_ignored(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        with mock.patch.dict(
            os.environ, self._env(GEMINI_API_KEY="your_gemini_key_here"), clear=False
        ):
            opp = ChatGPTOpponent()
            self.assertFalse(opp.is_available())

    def test_opponent_auto_resolves_groq_key(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        with mock.patch.dict(
            os.environ,
            self._env(GROQ_API_KEY="gsk_test", GEMINI_API_KEY=""),
            clear=False,
        ):
            opp = ChatGPTOpponent()
            self.assertTrue(opp.is_available())
            self.assertEqual(opp.provider_name(), "groq")
            self.assertIn("api.groq.com", opp.base_url)

    def test_opponent_explicit_override_beats_env(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        with mock.patch.dict(
            os.environ, self._env(OPENAI_API_KEY="sk-openai"), clear=False
        ):
            opp = ChatGPTOpponent(
                api_key="sk-custom", base_url="https://custom.example/v1", model="m"
            )
            self.assertEqual(opp.provider_name(), "openai-compatible")
            self.assertEqual(opp.base_url, "https://custom.example/v1")

    def test_opponent_empty_key_explicit_not_available(self):
        from orbit.orbit.core.benchmark import ChatGPTOpponent

        with mock.patch.dict(
            os.environ, self._env(GEMINI_API_KEY="AIzaTest"), clear=False
        ):
            opp = ChatGPTOpponent(api_key="")
            self.assertFalse(opp.is_available())

    def test_resolve_opponent_falls_back_when_probe_fails(self):
        from orbit.orbit.core.benchmark import MockOpponent, _resolve_opponent

        with mock.patch("orbit.orbit.core.benchmark.ChatGPTOpponent") as cls:
            inst = cls.return_value
            inst.is_available.return_value = True
            inst.generate.return_value = None  # probe fails
            inst.provider_name.return_value = "gemini"
            inst.model = "gemini-2.0-flash"
            opp = _resolve_opponent()
            self.assertIsInstance(opp, MockOpponent)

    def test_resolve_opponent_keeps_real_when_probe_ok(self):
        from orbit.orbit.core.benchmark import MockOpponent, _resolve_opponent

        with mock.patch("orbit.orbit.core.benchmark.ChatGPTOpponent") as cls:
            inst = cls.return_value
            inst.is_available.return_value = True
            inst.generate.return_value = {"text": "ok", "latency_ms": 5}
            inst.provider_name.return_value = "groq"
            inst.model = "llama-3.1-8b-instant"
            opp = _resolve_opponent()
            self.assertNotIsInstance(opp, MockOpponent)

    def test_mock_opponent_greeting(self):
        from orbit.orbit.core.benchmark import MockOpponent

        opp = MockOpponent()
        out = opp.generate("hello there")
        self.assertIn("Hello", out["text"])
        self.assertGreater(out["latency_ms"], 400.0)

    def test_mock_opponent_math(self):
        from orbit.orbit.core.benchmark import MockOpponent

        out = MockOpponent().generate("solve this integral please")
        self.assertIn("step", out["text"].lower())

    def test_mock_opponent_code(self):
        from orbit.orbit.core.benchmark import MockOpponent

        out = MockOpponent().generate("write a python function")
        self.assertIn("code", out["text"].lower())

    def test_mock_opponent_topics_echoed(self):
        from orbit.orbit.core.benchmark import MockOpponent

        out = MockOpponent().generate("explain quantum entanglement simply")
        self.assertIn("quantum", out["text"].lower())
        self.assertIn("entanglement", out["text"].lower())

    def test_mock_opponent_latency_scales_with_length(self):
        from orbit.orbit.core.benchmark import MockOpponent

        short = MockOpponent().generate("hello there")
        long = MockOpponent().generate("explain quantum entanglement simply")
        self.assertLess(short["latency_ms"], long["latency_ms"])

    def test_mock_opponent_deterministic_jitter(self):
        from orbit.orbit.core.benchmark import MockOpponent

        a = MockOpponent().generate("how does gravity work")
        b = MockOpponent().generate("how does gravity work")
        self.assertEqual(a["latency_ms"], b["latency_ms"])
        self.assertNotEqual(
            a["text"], MockOpponent().generate("how does magnetism work")["text"]
        )


class TestBenchmarkRunner(unittest.TestCase):
    def _fake_jarvus(self, prompt, latency=50.0):
        def _gen(p):
            return {"text": f"ORBIT answer to: {p[:20]}", "latency_ms": latency}

        return _gen

    def test_compare_builds_result(self):
        from orbit.orbit.core.benchmark import BenchmarkRunner, MockOpponent

        r = BenchmarkRunner()
        res = r.compare(
            "hello", jarvus_generator=self._fake_jarvus("x"), opponent=MockOpponent()
        )
        self.assertIn("ORBIT", res.jarvus_text)
        self.assertIn("Hello", res.opponent_text)
        self.assertEqual(res.jarvus_latency_ms, 50.0)
        self.assertGreater(res.opponent_latency_ms, 400.0)
        self.assertTrue(res._jarvus_faster())

    def test_compare_verdict_fields(self):
        from orbit.orbit.core.benchmark import BenchmarkRunner, MockOpponent

        res = BenchmarkRunner().compare("hi", self._fake_jarvus("x"), MockOpponent())
        d = res.to_dict()
        self.assertTrue(d["verdict"]["jarvus_faster"])
        self.assertGreater(d["verdict"]["speedup_pct"], 90)

    def test_compare_slower_jarvus(self):
        from orbit.orbit.core.benchmark import BenchmarkRunner, MockOpponent

        res = BenchmarkRunner().compare(
            "hi", self._fake_jarvus("x", latency=5000.0), MockOpponent()
        )
        self.assertFalse(res._jarvus_faster())

    def test_default_generator_offline_returns_none(self):
        from orbit.orbit.core.benchmark import BenchmarkRunner

        class _FailingRouter:
            async def generate(self, request):
                from orbit.orbit.core.llm.router import LLMResponse

                return LLMResponse(
                    content="[Error: All LLM providers unavailable]",
                    provider="none",
                    model="mock",
                    latency_ms=0,
                    success=False,
                    error="offline",
                )

        with mock.patch(
            "orbit.orbit.core.llm.router.get_router",
            return_value=_FailingRouter(),
        ):
            out = BenchmarkRunner()._jarvus_default("hello", timeout=2.0)
        self.assertIsNone(out)  # provider failure -> graceful None

    def test_batch_aggregation(self):
        from orbit.orbit.core.benchmark import BenchmarkRunner, MockOpponent

        r = BenchmarkRunner()
        prompts = [f"prompt {i}" for i in range(10)]
        agg = r.run_batch(prompts, self._fake_jarvus("x"), MockOpponent())
        self.assertEqual(agg["count"], 10)
        self.assertEqual(agg["jarvus_win_rate_pct"], 100.0)
        self.assertGreater(agg["jarvus"]["p50_ms"], 0)
        self.assertLessEqual(agg["jarvus"]["p95_ms"], 200)

    def test_stats_tracks_runs(self):
        from orbit.orbit.core.benchmark import BenchmarkRunner, MockOpponent

        cleared = {
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GROQ_API_KEY": "",
            "CEREBRAS_API_KEY": "",
            "OPPONENT_API_KEY": "",
            "OPPONENT_BASE_URL": "",
            "OPPONENT_MODEL": "",
            "OPPONENT_OPENAI_KEY": "",
            "OPPONENT_OPENAI_MODEL": "",
        }
        with mock.patch.dict(os.environ, cleared, clear=False):
            r = BenchmarkRunner()
            r.compare("a", self._fake_jarvus("x"), MockOpponent())
            r.compare("b", self._fake_jarvus("x"), MockOpponent())
            stats = r.get_stats()
        self.assertEqual(stats["total_runs"], 2)
        self.assertEqual(stats["history_size"], 2)
        self.assertTrue(stats["opponent"]["is_mock"])
        self.assertIsNotNone(stats["last_result"])

    def test_reset(self):
        from orbit.orbit.core.benchmark import BenchmarkRunner, MockOpponent

        r = BenchmarkRunner()
        r.compare("a", self._fake_jarvus("x"), MockOpponent())
        r.reset()
        stats = r.get_stats()
        self.assertEqual(stats["total_runs"], 0)
        self.assertEqual(stats["history_size"], 0)

    def test_singleton(self):
        from orbit.orbit.core.benchmark import get_benchmark

        self.assertIsNotNone(get_benchmark())

    def test_compare_prompt_helper(self):
        from orbit.orbit.core import benchmark as bm
        from orbit.orbit.core.benchmark import MockOpponent

        with mock.patch.object(
            bm.BenchmarkRunner,
            "_jarvus_default",
            lambda self, p, timeout=12: {"text": "j", "latency_ms": 5.0},
        ):
            out = bm.get_benchmark().compare("hello", opponent=MockOpponent()).to_dict()
        self.assertIn("verdict", out)


class TestReasoningDepth(unittest.TestCase):
    def test_empty(self):
        from orbit.orbit.core.reasoning_depth import score_depth

        s = score_depth("")
        self.assertEqual(s["depth_score"], 0)
        self.assertEqual(s["verdict"], "empty")

    def test_shallow(self):
        from orbit.orbit.core.reasoning_depth import score_depth

        s = score_depth("It is fine. Yes.")
        self.assertEqual(s["verdict"], "shallow")

    def test_deep_steps(self):
        from orbit.orbit.core.reasoning_depth import score_depth

        text = (
            "First, identify the variables. Then, write the equation. "
            "Next, solve for x. Therefore, substitute back. Finally, verify."
        )
        s = score_depth(text)
        self.assertGreaterEqual(s["steps"], 4)
        # "Then"/"Next" count as step markers only (no double-count in
        # connectors); the sole true connector here is "Therefore".
        self.assertGreaterEqual(s["connectors"], 1)
        self.assertIn(s["verdict"], ("deep", "moderate"))

    def test_math_verbs(self):
        from orbit.orbit.core.reasoning_depth import score_depth

        s = score_depth(
            "Compute the derivative. Simplify and integrate the result. Verify by substituting."
        )
        self.assertGreaterEqual(s["math_verbs"], 4)

    def test_numbered_steps(self):
        from orbit.orbit.core.reasoning_depth import score_depth

        s = score_depth("Step 1: do this. Step 2: do that. Step 3: done.")
        self.assertEqual(s["numbered_steps"], 3)

    def test_hedges_detected(self):
        from orbit.orbit.core.reasoning_depth import score_depth

        s = score_depth(
            "I think maybe this might be roughly correct, but I am not sure."
        )
        self.assertGreater(s["hedges"], 0)

    def test_compare_depth_jarvus_wins(self):
        from orbit.orbit.core.reasoning_depth import compare_depth

        deep = "First compute. Then substitute. Therefore solve. Finally verify the result."
        shallow = "Yes."
        r = compare_depth(deep, shallow)
        self.assertTrue(r["jarvus_wins"])
        self.assertEqual(r["verdict"], "jarvus_deeper")
        self.assertGreater(r["depth_delta"], 0)

    def test_compare_depth_no_baseline(self):
        from orbit.orbit.core.reasoning_depth import compare_depth

        r = compare_depth(
            "Therefore, this reasoning follows directly from the evidence."
        )
        self.assertIsNone(r["baseline"])
        self.assertTrue(r["jarvus_wins"])

    def test_compare_depth_baseline_wins(self):
        from orbit.orbit.core.reasoning_depth import compare_depth

        r = compare_depth(
            "Fine.",
            "First, analyze. Second, plan. Then execute. Therefore evaluate. Finally iterate.",
        )
        self.assertFalse(r["jarvus_wins"])
        self.assertEqual(r["verdict"], "baseline_deeper")

    def test_score_consistency(self):
        from orbit.orbit.core.reasoning_depth import score_depth

        s1 = score_depth("First we plan. Then we act. Therefore we review.")
        s2 = score_depth("First we plan. Then we act. Therefore we review.")
        self.assertEqual(s1["depth_score"], s2["depth_score"])


class TestBenchmarkAPI(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def test_stats_endpoint(self):
        r = self.client.get("/api/benchmark/stats")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("total_runs", data)
        self.assertIn("opponent", data)

    def test_depth_endpoint(self):
        r = self.client.get(
            "/api/benchmark/depth",
            query_string={"response": "First, compute. Then, verify."},
        )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("depth_score", data)

    def test_depth_endpoint_requires_response(self):
        r = self.client.get("/api/benchmark/depth")
        self.assertEqual(r.status_code, 400)

    def test_compare_endpoint_requires_prompt(self):
        r = self.client.get("/api/benchmark/compare")
        self.assertEqual(r.status_code, 400)

    def test_compare_endpoint_with_mock(self):
        import orbit.orbit.core.benchmark as bm

        with mock.patch.object(
            bm.BenchmarkRunner,
            "_jarvus_default",
            lambda self, p, timeout=12: {"text": "ORBIT says hi", "latency_ms": 25.0},
        ):
            r = self.client.get(
                "/api/benchmark/compare", query_string={"prompt": "hello"}
            )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("ORBIT", data["jarvus"]["text"])
        self.assertIn("verdict", data)


class TestAutonomousRunner(unittest.TestCase):
    def _fake_gen(self, text="auto reply", provider="groq", fail_first=0):
        state = {"calls": 0}

        def _gen(prompt):
            state["calls"] += 1
            if state["calls"] <= fail_first:
                return None
            return {
                "text": f"{text} {state['calls']}",
                "latency_ms": 5.0,
                "provider": provider,
                "model": "test",
            }

        return _gen

    def test_session_completes(self):
        from orbit.orbit.core.autonomous_chat import AutonomousConversationRunner

        runner = AutonomousConversationRunner()
        status = runner.start(
            minutes=0.05,
            max_turns=3,
            generator=self._fake_gen(),
            background=False,
            gap_seconds=0.0,
        )
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["turns_completed"], 3)
        self.assertEqual(status["jarvus_turns"], 3)
        self.assertEqual(status["last_provider"], "groq")

    def test_transcript_written(self):
        from pathlib import Path

        from orbit.orbit.core.autonomous_chat import AutonomousConversationRunner

        runner = AutonomousConversationRunner()
        status = runner.start(
            minutes=0.05,
            max_turns=2,
            generator=self._fake_gen(),
            background=False,
            gap_seconds=0.0,
        )
        path = Path(status["transcript_path"])
        self.assertTrue(path.exists())
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(lines), 2)

    def test_self_correction_on_failure(self):
        from orbit.orbit.core.autonomous_chat import AutonomousConversationRunner

        runner = AutonomousConversationRunner()
        status = runner.start(
            minutes=0.05,
            max_turns=3,
            generator=self._fake_gen(fail_first=1),
            background=False,
            gap_seconds=0.0,
        )
        self.assertGreaterEqual(status["self_corrections"], 1)
        self.assertEqual(status["turns_completed"], 3)

    def test_provider_switch_counted(self):
        from orbit.orbit.core.autonomous_chat import AutonomousConversationRunner

        runner = AutonomousConversationRunner()
        state = {"n": 0}

        def _gen(prompt):
            state["n"] += 1
            prov = "groq" if state["n"] % 2 else "gemini"
            return {"text": "x", "latency_ms": 5.0, "provider": prov, "model": "m"}

        status = runner.start(
            minutes=0.05, max_turns=4, generator=_gen, background=False, gap_seconds=0.0
        )
        self.assertGreaterEqual(status["provider_switches"], 1)

    def test_default_generator_offline(self):
        from orbit.orbit.core.autonomous_chat import AutonomousConversationRunner

        class _FailingRouter:
            async def generate(self, request):
                from orbit.orbit.core.llm.router import LLMResponse

                return LLMResponse(
                    content="[Error: All LLM providers unavailable]",
                    provider="none",
                    model="mock",
                    latency_ms=0,
                    success=False,
                    error="offline",
                )

        runner = AutonomousConversationRunner()
        with mock.patch(
            "orbit.orbit.core.llm.router.get_router",
            return_value=_FailingRouter(),
        ):
            self.assertIsNone(runner._default_generate("hello"))

    def test_status_and_stop(self):
        from orbit.orbit.core.autonomous_chat import AutonomousConversationRunner

        runner = AutonomousConversationRunner()
        status = runner.start(
            minutes=0.1,
            max_turns=1,
            generator=self._fake_gen(),
            background=True,
            gap_seconds=0.0,
        )
        sid = status["session_id"]
        time.sleep(1.0)
        s = runner.get_status(sid)
        self.assertIn(s["status"], ("completed", "running", "stopped"))
        self.assertTrue(runner.stop(sid))
        overall = runner.get_status()
        self.assertIn("active_sessions", overall)

    def test_transcripts_listing(self):
        from orbit.orbit.core.autonomous_chat import AutonomousConversationRunner

        runner = AutonomousConversationRunner()
        runner.start(
            minutes=0.05,
            max_turns=1,
            generator=self._fake_gen(),
            background=False,
            gap_seconds=0.0,
        )
        tx = runner.get_transcripts(limit=5)
        self.assertGreaterEqual(len(tx), 1)
        self.assertIn("turns", tx[0])

    def test_get_autonomous_singleton(self):
        from orbit.orbit.core.autonomous_chat import (
            get_autonomous,
            start_autonomous_battle,
        )

        self.assertIsNotNone(get_autonomous())
        self.assertIsNotNone(
            start_autonomous_battle(
                opponent="chatgpt",
                minutes=0.01,
                max_turns=1,
                generator=self._fake_gen(),
                background=False,
            )
        )


class TestAutonomousAPI(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def test_start_status_stop(self):
        import orbit.orbit.core.autonomous_chat as ac

        with mock.patch.object(
            ac.AutonomousConversationRunner,
            "_default_generate",
            lambda self, prompt: {
                "text": "auto",
                "latency_ms": 5.0,
                "provider": "groq",
                "model": "m",
            },
        ):
            r = self.client.get(
                "/api/autonomous/start", query_string={"minutes": 0.05, "max_turns": 2}
            )
            self.assertEqual(r.status_code, 200)
            sid = r.get_json().get("session_id")
            self.assertIsNotNone(sid)
            r = self.client.get("/api/autonomous/status")
            self.assertEqual(r.status_code, 200)
            self.assertIn("active_sessions", r.get_json())
            r = self.client.get("/api/autonomous/stop")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.get_json()["stopped"])
            r = self.client.get("/api/autonomous/transcripts")
            self.assertEqual(r.status_code, 200)
            self.assertIn("transcripts", r.get_json())


class TestSemanticSimilarity(unittest.TestCase):
    def test_identical(self):
        from orbit.orbit.core.benchmark import _semantic_similarity

        self.assertEqual(
            _semantic_similarity(
                "quantum entanglement links particles",
                "quantum entanglement links particles",
            ),
            1.0,
        )

    def test_disjoint(self):
        from orbit.orbit.core.benchmark import _semantic_similarity

        s = _semantic_similarity(
            "the planet mars orbits the sun", "banana pancakes taste delicious"
        )
        self.assertLess(s, 0.05)

    def test_partial_overlap(self):
        from orbit.orbit.core.benchmark import _semantic_similarity

        s = _semantic_similarity("the quick fox jumps", "the lazy fox sits")
        self.assertGreater(s, 0.0)
        self.assertLess(s, 1.0)

    def test_synonym_morphology_boost(self):
        from orbit.orbit.core.benchmark import _semantic_similarity

        base = _semantic_similarity(
            "quantum entanglement connects particles",
            "entangled quantum particles stay connected",
        )
        self.assertGreater(base, 0.25)

    def test_empty(self):
        from orbit.orbit.core.benchmark import _semantic_similarity

        self.assertEqual(_semantic_similarity("", "hello world"), 0.0)

    def test_semantic_module_direct(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        self.assertAlmostEqual(
            semantic_similarity("same exact answer text", "same exact answer text"), 1.0
        )
        self.assertEqual(semantic_similarity("", "anything"), 0.0)
        self.assertGreater(
            semantic_similarity(
                "water boils at high temperature",
                "high temperature causes water boiling",
            ),
            0.5,
        )

    def test_context_retention(self):
        from orbit.orbit.core.benchmark import _context_retention

        r = _context_retention(
            "improve code quality pipeline", "improve the code quality"
        )
        self.assertGreater(r, 0.5)
        self.assertLessEqual(r, 1.0)


class TestBenchmarkEngine(unittest.TestCase):
    def _override(self, text, latency=50.0, model="test-model"):
        return {
            "content": text,
            "latency_ms": latency,
            "model_used": model,
            "provider": "test",
        }

    def test_compare_single_composite_fields(self):
        from orbit.orbit.core.benchmark import BenchmarkEngine, MockOpponent

        e = BenchmarkEngine()
        r = asyncio.run(
            e.compare_single(
                "Explain how to optimize a database query",
                reasoning=True,
                opponent=MockOpponent(),
                jarvus_override=self._override(
                    "First, analyze the query. Then, identify the slow parts. Therefore, add an index and verify the plan."
                ),
            )
        )
        self.assertEqual(r["composite"]["winner"], "jarvus")
        self.assertIn("accuracy_score", r)
        self.assertIn("context_retention", r)
        self.assertIn("reasoning", r)
        self.assertLessEqual(r["composite"]["total"], 1.0)

    def test_compare_single_slow_jarvus_loses(self):
        from orbit.orbit.core.benchmark import BenchmarkEngine, MockOpponent

        e = BenchmarkEngine()
        r = asyncio.run(
            e.compare_single(
                "what is quantum entanglement",
                opponent=MockOpponent(),
                jarvus_override=self._override("Just hello.", latency=9000.0),
            )
        )
        self.assertEqual(r["composite"]["winner"], "opponent")

    def test_compare_batch_aggregation(self):
        from orbit.orbit.core.benchmark import BenchmarkEngine, MockOpponent

        e = BenchmarkEngine()

        async def _fake_orbit(
            prompt,
            reasoning=False,
            history=None,
            local=False,
            max_tokens=None,
            system_prompt=None,
        ):
            return self._override("Deep structured answer here.")

        with mock.patch.object(e, "_run_orbit", side_effect=_fake_orbit):
            agg = asyncio.run(
                e.compare_batch(["p1", "p2", "p3"], opponent=MockOpponent())
            )
        self.assertEqual(agg["count"], 3)
        self.assertIn("jarvus_win_rate_pct", agg)
        self.assertIn("avg_composite", agg)

    def test_compare_multiturn_returns_turns(self):
        from orbit.orbit.core.benchmark import BenchmarkEngine, MockOpponent

        e = BenchmarkEngine()

        async def _fake_orbit(
            prompt,
            reasoning=False,
            history=None,
            local=False,
            max_tokens=None,
            system_prompt=None,
        ):
            return self._override("Structured multi-part answer.")

        with mock.patch.object(e, "_run_orbit", side_effect=_fake_orbit):
            mt = asyncio.run(
                e.compare_multiturn(
                    [
                        "what is quantum entanglement?",
                        "how does it relate to computing?",
                        "give an example of quantum entanglement",
                    ],
                    opponent=MockOpponent(),
                )
            )
        self.assertEqual(len(mt["turns"]), 3)
        self.assertGreaterEqual(mt["count"], 3)
        for t in mt["turns"]:
            self.assertIn("context_retention", t)

    def test_export_and_status(self):
        from orbit.orbit.core.benchmark import BenchmarkEngine, MockOpponent

        e = BenchmarkEngine()
        asyncio.run(
            e.compare_single(
                "what is quantum entanglement",
                opponent=MockOpponent(),
                jarvus_override=self._override("a"),
            )
        )
        path = e.export_results()
        self.assertTrue(__import__("pathlib").Path(path).exists())
        status = e.get_status()
        self.assertGreaterEqual(status["total_runs"], 1)
        self.assertIn("exports", status)

    def test_reset(self):
        from orbit.orbit.core.benchmark import BenchmarkEngine, MockOpponent

        e = BenchmarkEngine()
        asyncio.run(
            e.compare_single(
                "what is quantum entanglement",
                opponent=MockOpponent(),
                jarvus_override=self._override("a"),
            )
        )
        e.reset()
        self.assertEqual(e.get_status()["total_runs"], 0)

    def test_singleton(self):
        from orbit.orbit.core.benchmark import get_benchmark_engine

        self.assertIsNotNone(get_benchmark_engine())

    def test_default_runner_still_works(self):
        from orbit.orbit.core.benchmark import BenchmarkRunner, MockOpponent

        res = BenchmarkRunner().compare(
            "hello",
            lambda p: {"text": "ORBIT reply", "latency_ms": 10.0},
            MockOpponent(),
        )
        self.assertIn("ORBIT", res.jarvus_text)


class TestReasoningDepthAnalyzer(unittest.TestCase):
    def test_empty(self):
        from orbit.orbit.core.reasoning_depth import analyze_reasoning

        a = analyze_reasoning("")
        self.assertEqual(a["verdict"], "empty")
        self.assertEqual(a["depth_score"], 0.0)

    def test_deep_sentence_metrics(self):
        from orbit.orbit.core.reasoning_depth import analyze_reasoning

        a = analyze_reasoning(
            "First, define the problem. Then, gather the data. Next, run the analysis. "
            "Therefore, interpret the results. Finally, verify the conclusion."
        )
        self.assertGreaterEqual(a["sentence_count"], 4)
        self.assertGreaterEqual(a["step_markers"], 4)
        # Corrected semantics: only "Therefore" is a true connector here.
        self.assertGreaterEqual(a["reasoning_connectors"], 1)
        self.assertIn(a["verdict"], ("deep", "moderate"))

    def test_self_corrections_detected(self):
        from orbit.orbit.core.reasoning_depth import analyze_reasoning

        a = analyze_reasoning(
            "I think the answer is X. Wait, actually, on second thought, it is Y."
        )
        self.assertGreaterEqual(a["self_corrections"], 1)

    def test_uncertainty_detected(self):
        from orbit.orbit.core.reasoning_depth import analyze_reasoning

        a = analyze_reasoning("I am not sure, perhaps it is roughly 5, maybe 6.")
        self.assertGreater(a["uncertainty"], 0)

    def test_compare_analyzer(self):
        from orbit.orbit.core.reasoning_depth import compare_analyzer

        r = compare_analyzer(
            "First compute. Then substitute. Therefore solve. Finally verify.", "yes."
        )
        self.assertTrue(r["jarvus_wins"])
        self.assertEqual(r["verdict"], "jarvus_deeper")
        self.assertGreater(r["depth_delta"], 0)

    def test_compare_analyzer_no_baseline(self):
        from orbit.orbit.core.reasoning_depth import compare_analyzer

        r = compare_analyzer("Therefore, this conclusion follows from the evidence.")
        self.assertIsNone(r["baseline"])
        self.assertTrue(r["jarvus_wins"])

    def test_analyzer_no_nltk_dependency(self):
        from orbit.orbit.core.reasoning_depth import (
            ReasoningDepthAnalyzer,
        )

        a = ReasoningDepthAnalyzer().analyze("First do this. Then do that.")
        self.assertGreaterEqual(a.sentence_count, 2)
        self.assertIsNotNone(a.to_dict())


class TestBenchmarkEngineAPI(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def test_compare_post(self):
        from orbit.orbit.core import benchmark as bm

        with mock.patch.object(
            bm.BenchmarkEngine,
            "_run_orbit",
            return_value={
                "content": "ORBIT structured answer",
                "latency_ms": 30.0,
                "model_used": "m",
            },
        ):
            r = self.client.post(
                "/api/benchmark/compare", json={"prompt": "hello", "reasoning": True}
            )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("composite", data)
        self.assertIn("winner", data["composite"])

    def test_compare_post_requires_prompt(self):
        r = self.client.post("/api/benchmark/compare", json={})
        self.assertEqual(r.status_code, 400)

    def test_batch_post(self):
        from orbit.orbit.core import benchmark as bm

        with mock.patch.object(
            bm.BenchmarkEngine,
            "_run_orbit",
            return_value={"content": "a", "latency_ms": 10.0, "model_used": "m"},
        ):
            r = self.client.post("/api/benchmark/batch", json={"prompts": ["a", "b"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 2)

    def test_multiturn_post(self):
        from orbit.orbit.core import benchmark as bm

        with mock.patch.object(
            bm.BenchmarkEngine,
            "_run_orbit",
            return_value={"content": "a", "latency_ms": 10.0, "model_used": "m"},
        ):
            r = self.client.post(
                "/api/benchmark/multiturn",
                json={"prompts": ["what is X?", "explain more"]},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["turns"]), 2)

    def test_multiturn_requires_two_prompts(self):
        r = self.client.post("/api/benchmark/multiturn", json={"prompts": ["only one"]})
        self.assertEqual(r.status_code, 400)

    def test_reasoning_depth_post(self):
        r = self.client.post(
            "/api/benchmark/reasoning-depth",
            json={"response": "First compute. Then verify."},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("sentence_count", r.get_json())

    def test_reasoning_depth_compare_post(self):
        r = self.client.post(
            "/api/benchmark/reasoning-depth/compare",
            json={"jarvus": "First compute. Then verify.", "baseline": "yes."},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["jarvus_wins"])

    def test_export_post(self):
        from orbit.orbit.core import benchmark as bm

        with mock.patch.object(
            bm.BenchmarkEngine,
            "_run_orbit",
            return_value={"content": "a", "latency_ms": 10.0, "model_used": "m"},
        ):
            self.client.post("/api/benchmark/compare", json={"prompt": "hello"})
            r = self.client.post("/api/benchmark/export", json={})
        self.assertEqual(r.status_code, 200)
        self.assertIn("path", r.get_json())

    def test_results_and_status(self):
        from orbit.orbit.core import benchmark as bm

        with mock.patch.object(
            bm.BenchmarkEngine,
            "_run_orbit",
            return_value={"content": "a", "latency_ms": 10.0, "model_used": "m"},
        ):
            self.client.post("/api/benchmark/compare", json={"prompt": "hello"})
            r = self.client.get("/api/benchmark/results")
            s = self.client.get("/api/benchmark/status")
        self.assertEqual(r.status_code, 200)
        self.assertIn("results", r.get_json())
        self.assertEqual(s.status_code, 200)
        self.assertIn("total_runs", s.get_json())


if __name__ == "__main__":
    unittest.main()
