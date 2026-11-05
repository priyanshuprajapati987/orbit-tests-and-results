"""
Tests for ORBIT Tier 1 — ChatGPT Competition Killer systems.

Covers:
- Multi-Provider Orchestrator (query classification, routing chains, gating)
- Conversation Engine (state machine, CoT, formatting, latency stats)
- LLM Response Cache (LRU + TTL)
- Input Sanitizer (XSS/SQL/path traversal)
- Rate Limiter (token bucket)
- Circuit Breaker (states, retry)
"""

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestOrchestrator(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.llm.orchestrator import get_orchestrator

        self.assertIsNotNone(get_orchestrator())

    def test_reasoning_routing(self):
        from orbit.orbit.core.llm.orchestrator import QueryType, get_orchestrator

        plan = get_orchestrator().plan(
            "explain step by step why the sky is blue and compare it with the ocean"
        )
        self.assertEqual(plan.query_type, QueryType.REASONING)
        self.assertIn("openrouter", [p for p, _ in plan.chain])

    def test_fast_routing(self):
        from orbit.orbit.core.llm.orchestrator import QueryType, get_orchestrator

        plan = get_orchestrator().plan("quick - what time is it?")
        self.assertEqual(plan.query_type, QueryType.FAST)
        # groq/gemini only lead when their keys are configured; the chain must
        # always end with the openrouter gateway fallback so FAST never blocks.
        self.assertEqual(plan.chain[-1][0], "openrouter")

    def test_creative_routing(self):
        # Hermetic: ambient .env keys (gemini/openrouter present or empty) and
        # singleton quality history must not decide chain order — force every
        # provider available on a FRESH orchestrator (all quality scores 0.5 →
        # stable sort) so the chain is exactly the design ROUTES order.
        from unittest.mock import patch

        from orbit.orbit.core.llm.orchestrator import (
            ProviderOrchestrator,
            QueryType,
        )

        orch = ProviderOrchestrator()
        with patch.object(
            ProviderOrchestrator, "_provider_available", return_value=True
        ), patch("orbit.orbit.core.llm.orchestrator.get_circuit_breaker"):
            plan = orch.plan("write a poem about a robot falling in love")
        self.assertEqual(plan.query_type, QueryType.CREATIVE)
        self.assertEqual(
            [p for p, _ in plan.chain],
            [p for p, _ in ProviderOrchestrator.ROUTES[QueryType.CREATIVE]],
        )
        self.assertEqual(plan.chain[0][0], "gemini")

    def test_code_routing(self):
        from unittest.mock import patch

        from orbit.orbit.core.llm.orchestrator import (
            ProviderOrchestrator,
            QueryType,
        )

        orch = ProviderOrchestrator()
        with patch.object(
            ProviderOrchestrator, "_provider_available", return_value=True
        ), patch("orbit.orbit.core.llm.orchestrator.get_circuit_breaker"):
            plan = orch.plan(
                "debug this python function that crashes on empty input"
            )
        self.assertEqual(plan.query_type, QueryType.CODE)
        # Full design order (openai → openrouter → groq → cloudflare → gemini → ollama)
        self.assertEqual(
            [p for p, _ in plan.chain],
            [p for p, _ in ProviderOrchestrator.ROUTES[QueryType.CODE]],
        )
        self.assertIn(plan.chain[0][0], ("openai", "openrouter"))

    def test_chat_routing(self):
        from orbit.orbit.core.llm.orchestrator import QueryType, get_orchestrator

        plan = get_orchestrator().plan("hey orbit how are you")
        self.assertEqual(plan.query_type, QueryType.CHAT)

    def test_offline_plan_forces_ollama(self):
        from orbit.orbit.core.llm.orchestrator import get_orchestrator

        plan = get_orchestrator().plan(
            "explain quantum computing in detail", offline=True
        )
        self.assertEqual(len(plan.chain), 1)
        self.assertEqual(plan.chain[0][0], "ollama")

    def test_math_routing(self):
        from orbit.orbit.core.llm.orchestrator import QueryType, get_orchestrator

        plan = get_orchestrator().plan("what is the derivative of x squared")
        self.assertEqual(plan.query_type, QueryType.REASONING)

    def test_plan_to_dict(self):
        from orbit.orbit.core.llm.orchestrator import get_orchestrator

        d = get_orchestrator().plan("hello").to_dict()
        self.assertIn("query_type", d)
        self.assertIn("chain", d)
        self.assertIsInstance(d["chain"], list)

    def test_stats(self):
        from orbit.orbit.core.llm.orchestrator import get_orchestrator

        get_orchestrator().plan("test prompt one")
        get_orchestrator().plan("test prompt two more words here")
        stats = get_orchestrator().get_stats()
        self.assertGreaterEqual(stats["total_routes"], 2)
        self.assertIn("by_type", stats)


class TestConversationEngine(unittest.TestCase):
    def test_import(self):
        from orbit.orbit.core.conversation_engine import get_engine

        self.assertIsNotNone(get_engine())

    def test_state_machine(self):
        from orbit.orbit.core.conversation_engine import (
            ConversationEngine,
            ConversationState,
        )

        e = ConversationEngine()
        e._transition(ConversationState.ROUTING)
        e._transition(ConversationState.GENERATING)
        e._transition(ConversationState.COMPLETE)
        self.assertEqual(e.state, ConversationState.COMPLETE)

    def test_invalid_transition(self):
        from orbit.orbit.core.conversation_engine import (
            ConversationEngine,
            ConversationState,
        )

        e = ConversationEngine()
        with self.assertRaises(ValueError):
            e._transition(
                ConversationState.GENERATING
            )  # IDLE -> GENERATING not allowed

    def test_error_recovery_transition(self):
        from orbit.orbit.core.conversation_engine import (
            ConversationEngine,
            ConversationState,
        )

        e = ConversationEngine()
        e._transition(ConversationState.ROUTING)
        e._transition(ConversationState.ERROR)
        e._transition(ConversationState.ROUTING)  # recovery allowed
        self.assertEqual(e.state, ConversationState.ROUTING)

    def test_cot_reasoning(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine
        from orbit.orbit.core.llm.orchestrator import QueryType

        e = ConversationEngine()
        cot = e._apply_cot("why does this happen", QueryType.REASONING, "complex")
        self.assertIn("step by step", cot)
        plain = e._apply_cot("hello", QueryType.CHAT, "simple")
        self.assertNotIn("step by step", plain)

    def test_formatter_truncate(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        long = "x" * 5000
        out = MessageFormatter.truncate(long)
        self.assertLessEqual(len(out), 1300)
        self.assertIn("truncated", out)

    def test_formatter_structure_lists(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        long_list = (
            "first apple, second banana, third mango, fourth grape, fifth peach, "
            "sixth plum, seventh berry, eighth cherry, ninth melon, tenth papaya here"
        )
        self.assertGreater(len(long_list), 120)
        out = MessageFormatter.structure_lists(long_list)
        self.assertIn("- ", out)

    def test_formatter_collapse(self):
        from orbit.orbit.core.conversation_engine import MessageFormatter

        out = MessageFormatter.collapse_blank_lines("a\n\n\n\nb")
        self.assertEqual(out, "a\n\nb")

    def test_latency_stats(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine

        e = ConversationEngine()
        e._latencies.extend([800, 1500, 2500, 3000, 900])
        stats = e.get_latency_stats()
        self.assertEqual(stats["count"], 5)
        self.assertEqual(stats["target_ms"], 2000)
        self.assertEqual(stats["p50_ms"], 1500)
        self.assertGreaterEqual(stats["on_target_pct"], 0)
        self.assertLessEqual(stats["on_target_pct"], 100)

    def test_empty_latency_stats(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine

        stats = ConversationEngine().get_latency_stats()
        self.assertEqual(stats["count"], 0)

    def test_token_estimate(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine

        self.assertGreater(
            ConversationEngine._estimate_tokens("hello world", "hi back"), 0
        )

    def test_get_stats(self):
        from orbit.orbit.core.conversation_engine import get_engine

        stats = get_engine().get_stats()
        self.assertIn("state", stats)
        self.assertIn("latency", stats)
        self.assertIn("turn_count", stats)


class TestContextWindow(unittest.TestCase):
    # ── token budget ──────────────────────────────────────────────────────
    def test_estimate_tokens(self):
        from orbit.orbit.core.token_budget import estimate_tokens

        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("hello world this is a test"), 7)

    def test_budget_allocation_sums(self):
        from orbit.orbit.core.token_budget import budget_allocation

        ratios = {"live": 0.5, "chunks": 0.3, "summary": 0.2}
        alloc = budget_allocation(4000, ratios)
        self.assertEqual(sum(alloc.values()), 4000)
        self.assertEqual(alloc["live"], 2000)
        self.assertEqual(alloc["chunks"], 1200)
        self.assertEqual(alloc["summary"], 800)

    def test_budget_allocation_zero(self):
        from orbit.orbit.core.token_budget import budget_allocation

        self.assertEqual(budget_allocation(0, {"a": 1.0}), {"a": 0})

    def test_token_tracker_record(self):
        from orbit.orbit.core.token_budget import TokenTracker

        t = TokenTracker()
        t.record_turn(prompt_tokens=10, response_tokens=5, compressed_tokens=3)
        t.record_turn(prompt_tokens=20, response_tokens=10, compressed_tokens=5)
        stats = t.get_stats()
        self.assertEqual(stats["turns"], 2)
        self.assertEqual(stats["tokens_in"], 30)
        self.assertEqual(stats["tokens_out"], 15)
        self.assertEqual(stats["tokens_compressed"], 8)

    def test_token_tracker_reset(self):
        from orbit.orbit.core.token_budget import TokenTracker

        t = TokenTracker()
        t.record_turn(10, 5, 3)
        t.reset()
        self.assertEqual(t.get_stats()["turns"], 0)

    # ── context manager ───────────────────────────────────────────────────
    def _run_conversation(self, turns=250, live_window=4, summary_every=8):
        from orbit.orbit.core.context_manager import ContextManager

        class _FastFailingRouter:
            async def generate(self, request):
                from orbit.orbit.core.llm.router import LLMResponse

                return LLMResponse(
                    content="[Error]",
                    provider="none",
                    model="mock",
                    latency_ms=0,
                    success=False,
                    error="offline",
                )

        with mock.patch(
            "orbit.orbit.core.llm.router.get_router",
            return_value=_FastFailingRouter(),
        ):
            cm = ContextManager(
                live_window=live_window,
                summary_every=summary_every,
                max_chunk_turns=20,
                context_budget=2000,
            )
            for i in range(turns):
                cm.add_turn("user", f"discuss budget and timeline for phase {i}")
                cm.add_turn(
                    "assistant",
                    f"phase {i} budget is {i * 100} dollars, moved to next quarter",
                )
        return cm

    def test_turns_bounded(self):
        cm = self._run_conversation()
        self.assertLessEqual(len(cm._turns), 20)

    def test_rolling_summary_runs(self):
        cm = self._run_conversation()
        stats = cm.get_stats()
        self.assertGreaterEqual(stats["summaries_run"], 1)
        self.assertGreater(stats["summary_chars"], 0)
        self.assertIn("phase", cm._summary)

    def test_extractive_fallback_offline(self):
        class _FailingRouter:
            async def generate(self, request):
                from orbit.orbit.core.llm.router import LLMResponse

                return LLMResponse(
                    content="[Error]",
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
            cm = self._run_conversation()
            stats = cm.get_stats()
        self.assertEqual(
            stats["llm_summaries"], 0
        )  # provider failed -> extractive fallback
        self.assertGreater(stats["summary_chars"], 0)  # extractive still produced

    def test_chunks_indexed(self):
        cm = self._run_conversation()
        self.assertGreaterEqual(cm.get_stats()["chunks_indexed"], 1)

    def test_retrieval_relevance(self):
        cm = self._run_conversation()
        ctx = cm.get_context("how much was the budget in phase 12")
        self.assertIn("budget", ctx.lower())

    def test_compression_positive(self):
        cm = self._run_conversation()
        stats = cm.get_stats()
        self.assertGreater(stats["total_tokens_ingested"], stats["window_used_tokens"])
        self.assertGreater(stats["compression_pct"], 0)

    def test_build_history_structure(self):
        cm = self._run_conversation()
        history = cm.build_history("budget recap")
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["role"], "system")
        self.assertIn("content", history[0])

    def test_reset(self):
        cm = self._run_conversation()
        cm.reset()
        stats = cm.get_stats()
        self.assertEqual(stats["turns_stored"], 0)
        self.assertEqual(stats["chunks_indexed"], 0)
        self.assertEqual(stats["total_tokens_ingested"], 0)

    def test_singleton(self):
        from orbit.orbit.core.context_manager import get_context_manager

        self.assertIsNotNone(get_context_manager())

    # ── engine wiring ─────────────────────────────────────────────────────
    def test_engine_reset(self):
        from orbit.orbit.core.conversation_engine import get_engine

        engine = get_engine()
        engine._context.add_turn("user", "hello")
        engine.reset()
        stats = engine.get_stats()
        self.assertEqual(stats["context"]["turns_stored"], 0)
        self.assertEqual(stats["tokens"]["turns"], 0)
        self.assertEqual(stats["turn_count"], 0)

    def test_engine_records_context_turns(self):
        from orbit.orbit.core.conversation_engine import ConversationEngine

        e = ConversationEngine()
        e._context.add_turn("user", "hello there")
        e._context.add_turn("assistant", "hi back")
        stats = e.get_stats()
        self.assertEqual(stats["context"]["turns_stored"], 2)
        self.assertIn("tokens", stats)
        self.assertIn("context", stats)

    def test_context_status_endpoint(self):
        from orbit.orbit.server import create_app

        app = create_app()
        client = app.test_client()
        r = client.get("/api/context/status")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("context", data)
        self.assertIn("tokens", data)
        self.assertIn("engine", data)
        self.assertIn("compression_pct", data["context"])


class TestLLMCache(unittest.TestCase):
    def test_get_set(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import LLMResponseCache

        cache = LLMResponseCache(max_size=10, default_ttl=60)
        req = LLMRequest(prompt="hello")
        resp = LLMResponse(
            content="hi", provider="test", model="m", latency_ms=1, success=True
        )
        cache.set(req, resp)
        got = cache.get(req)
        self.assertEqual(got.content, "hi")
        self.assertGreaterEqual(cache.get_stats()["hits"], 0)

    def test_ttl_expiry(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import LLMResponseCache

        cache = LLMResponseCache(max_size=10, default_ttl=0.01)
        req = LLMRequest(prompt="hello")
        resp = LLMResponse(
            content="hi", provider="test", model="m", latency_ms=1, success=True
        )
        cache.set(req, resp)
        time.sleep(0.02)
        self.assertIsNone(cache.get(req))

    def test_max_size_eviction(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import LLMResponseCache

        cache = LLMResponseCache(max_size=3, default_ttl=60)
        for i in range(5):
            req = LLMRequest(prompt=f"prompt {i}")
            resp = LLMResponse(
                content=f"resp {i}", provider="t", model="m", latency_ms=1, success=True
            )
            cache.set(req, resp)
        self.assertLessEqual(cache.get_stats()["size"], 3)

    def test_failure_not_cached(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import LLMResponseCache

        cache = LLMResponseCache()
        req = LLMRequest(prompt="x")
        bad = LLMResponse(
            content="[Error]", provider="t", model="m", latency_ms=1, success=False
        )
        cache.set(req, bad)
        self.assertEqual(cache.get_stats()["size"], 0)

    def test_clear(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import LLMResponseCache

        cache = LLMResponseCache()
        req = LLMRequest(prompt="x")
        cache.set(req, LLMResponse(content="y", provider="t", model="m", latency_ms=1))
        cache.clear()
        self.assertEqual(cache.get_stats()["size"], 0)
        self.assertEqual(cache.get_stats()["hits"], 0)

    def test_cache_key_has_use_cache_flag(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import LLMResponseCache

        cache = LLMResponseCache()
        req_a = LLMRequest(prompt="hello", use_cache=True)
        req_b = LLMRequest(prompt="hello", use_cache=False)
        cache.set(
            req_a, LLMResponse(content="cached", provider="t", model="m", latency_ms=50)
        )
        self.assertIsNone(
            cache.get(req_b), "use_cache=False must not hit a use_cache=True entry"
        )

    def test_generate_honors_use_cache(self):
        import asyncio

        from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

        router = LLMRouter()
        hits = []

        async def fake_failover(request):
            hits.append(1)
            return type(
                "R",
                (),
                {
                    "content": "fresh",
                    "provider": "t",
                    "model": "m",
                    "latency_ms": 100,
                    "success": True,
                    "error": None,
                },
            )()

        async def run():
            router._generate_with_failover = fake_failover
            r1 = await router.generate(LLMRequest(prompt="p", use_cache=False))
            r2 = await router.generate(LLMRequest(prompt="p", use_cache=False))
            self.assertEqual(
                len(hits), 2, "use_cache=False must bypass cache on every call"
            )
            return r1, r2

        asyncio.run(run())


class TestInputSanitizer(unittest.TestCase):
    def test_xss_removed(self):
        from orbit.orbit.core.input_sanitizer import sanitize_request_data

        data = {"message": "<script>alert('x')</script>hello"}
        out = sanitize_request_data(data)
        self.assertNotIn("<script>", out["message"])
        self.assertIn("hello", out["message"])

    def test_sql_injection(self):
        from orbit.orbit.core.input_sanitizer import sanitize_request_data

        data = {"query": "SELECT * FROM users; DROP TABLE users; --"}
        out = sanitize_request_data(data)
        self.assertNotIn("DROP TABLE", out["query"])

    def test_path_traversal(self):
        from orbit.orbit.core.input_sanitizer import sanitize_request_data

        data = {"path": "../../etc/passwd"}
        out = sanitize_request_data(data)
        self.assertNotIn("..", out["path"])

    def test_nested_dict(self):
        from orbit.orbit.core.input_sanitizer import sanitize_request_data

        data = {"nested": {"msg": "<script>x</script>"}}
        out = sanitize_request_data(data)
        self.assertNotIn("<script>", out["nested"]["msg"])

    def test_coerce_int(self):
        from orbit.orbit.core.input_sanitizer import coerce_int

        self.assertEqual(coerce_int("42", 0), 42)
        self.assertEqual(coerce_int("abc", 5), 5)

    def test_lists_processed(self):
        from orbit.orbit.core.input_sanitizer import sanitize_request_data

        out = sanitize_request_data({"items": ["<script>alert(1)</script>", "ok"]})
        self.assertEqual(out["items"][0], "")


class TestRateLimiter(unittest.TestCase):
    def test_bucket_consume(self):
        from orbit.orbit.core.rate_limiter import TokenBucket

        b = TokenBucket(rate=100, burst=5)
        self.assertTrue(all(b.consume() for _ in range(5)))
        self.assertFalse(b.consume())  # exhausted burst

    def test_refill(self):
        from orbit.orbit.core.rate_limiter import TokenBucket

        b = TokenBucket(rate=1000, burst=1)
        b.consume()
        time.sleep(0.02)
        self.assertTrue(b.consume())

    def test_registry_status(self):
        from orbit.orbit.core.rate_limiter import RateLimiterRegistry

        r = RateLimiterRegistry()
        r.register("test:bucket", rate=10, burst=5)
        status = r.get_status()
        self.assertIn("test:bucket", status)
        self.assertIn("available_pct", status["test:bucket"])

    def test_register_endpoint(self):
        from orbit.orbit.core.rate_limiter import RateLimiterRegistry

        r = RateLimiterRegistry()
        r.register_endpoint("/api/test", rate=1, burst=2)
        self.assertTrue(r.check("endpoint:/api/test"))
        self.assertTrue(r.check("endpoint:/api/test"))
        self.assertFalse(r.check("endpoint:/api/test"))

    def test_unregistered_always_allows(self):
        from orbit.orbit.core.rate_limiter import RateLimiterRegistry

        self.assertTrue(RateLimiterRegistry().check("unknown:bucket"))


class TestCircuitBreaker(unittest.TestCase):
    def _make(self, threshold=3, timeout=1.0):
        import asyncio

        from orbit.orbit.core.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        return asyncio.run, CircuitBreaker(
            name="t",
            config=CircuitBreakerConfig(
                failure_threshold=threshold, recovery_timeout=timeout
            ),
        )

    def test_initial_state_closed(self):
        from orbit.orbit.core.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(name="test")
        self.assertEqual(cb.state.value, "closed")

    def test_opens_after_failures(self):
        import asyncio

        from orbit.orbit.core.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitBreakerOpenError,
        )

        async def run():
            cb = CircuitBreaker(
                name="test",
                config=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=1),
            )

            def boom():
                raise RuntimeError("boom")

            for _ in range(3):
                try:
                    await cb.call(boom)
                except RuntimeError:
                    pass
            return cb

        cb = asyncio.run(run())
        self.assertEqual(cb.state.value, "open")

        async def check_open():

            with self.assertRaises(CircuitBreakerOpenError):
                await cb.call(lambda: "x")

        asyncio.run(check_open())

    def test_recovery_after_timeout(self):
        import asyncio

        from orbit.orbit.core.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        async def run():
            cb = CircuitBreaker(
                name="test",
                config=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.01),
            )

            def boom():
                raise RuntimeError("boom")

            for _ in range(2):
                try:
                    await cb.call(boom)
                except RuntimeError:
                    pass
            await asyncio.sleep(0.03)
            try:
                await cb.call(lambda: "ok")
            except Exception:  # noqa: BLE001, S110
                pass
            return cb

        cb = asyncio.run(run())
        self.assertIn(cb.state.value, ("half_open", "closed"))

    def test_success_closes(self):
        import asyncio

        from orbit.orbit.core.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        async def run():
            cb = CircuitBreaker(
                name="test",
                config=CircuitBreakerConfig(
                    failure_threshold=1,
                    recovery_timeout=0.01,
                    consecutive_success_threshold=1,
                ),
            )

            def boom():
                raise RuntimeError("boom")

            try:
                await cb.call(boom)
            except RuntimeError:
                pass
            await asyncio.sleep(0.02)
            await cb.call(lambda: "ok")
            return cb

        cb = asyncio.run(run())
        self.assertEqual(cb.state.value, "closed")

    def test_state_dict(self):
        import asyncio

        from orbit.orbit.core.circuit_breaker import CircuitBreaker

        async def run():
            cb = CircuitBreaker(name="test")
            await cb.call(lambda: "ok")
            return cb

        cb = asyncio.run(run())
        state = cb.get_state()
        self.assertEqual(state["total_calls"], 1)
        self.assertEqual(state["total_successes"], 1)
        self.assertEqual(state["state"], "closed")

    def test_get_all_states(self):
        from orbit.orbit.core.circuit_breaker import get_all_circuit_states

        states = get_all_circuit_states()
        self.assertIsInstance(states, list)
        for s in states:
            self.assertIn("name", s)
            self.assertIn("state", s)


class TestPolicyEngine(unittest.TestCase):
    """P0-02/03/06/07: central ToolGate sandbox + risk classification."""

    def setUp(self):
        import tempfile

        self.workspace = Path(tempfile.mkdtemp(prefix="orbit_pol_ws_"))
        self.audit_dir = Path(tempfile.mkdtemp(prefix="orbit_pol_audit_"))
        from orbit.orbit.core.policy_engine import PolicyEngine

        self.engine = PolicyEngine(
            workspace=str(self.workspace), audit_dir=str(self.audit_dir)
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.workspace, ignore_errors=True)
        shutil.rmtree(self.audit_dir, ignore_errors=True)

    def test_import_and_singleton(self):
        from orbit.orbit.core.policy_engine import (
            check_tool,
            get_audit_log,
            get_policy_engine,
        )

        eng = get_policy_engine()
        self.assertIs(eng, get_policy_engine())
        self.assertIsInstance(get_audit_log(5), list)
        d = check_tool("file", "write", path=str(eng.workspace / "x.txt"), mutate=True)
        self.assertTrue(d.allowed)

    def test_inside_workspace_write_allowed(self):
        d = self.engine.check(
            "file", "write", path=str(self.workspace / "a" / "b.txt"), mutate=True
        )
        self.assertTrue(d.allowed)

    def test_outside_workspace_write_blocked(self):
        import tempfile

        outside = Path(tempfile.mkdtemp(prefix="orbit_pol_out_"))
        self.addCleanup(
            lambda: __import__("shutil").rmtree(outside, ignore_errors=True)
        )
        d = self.engine.check("file", "write", path=str(outside / "x.txt"), mutate=True)
        self.assertFalse(d.allowed)
        self.assertIn("outside_workspace", d.reason)

    def test_outside_read_allowed(self):
        import tempfile

        outside = Path(tempfile.mkdtemp(prefix="orbit_pol_out2_"))
        self.addCleanup(
            lambda: __import__("shutil").rmtree(outside, ignore_errors=True)
        )
        d = self.engine.check("file", "read", path=str(outside / "x.txt"), mutate=False)
        self.assertTrue(d.allowed)

    def test_blocked_system32(self):
        d = self.engine.check(
            "file", "write", path="C:/Windows/System32/x.txt", mutate=True
        )
        self.assertFalse(d.allowed)
        self.assertIn("blocked", d.reason)

    def test_approve_path_allows_outside_write(self):
        import tempfile

        outside = Path(tempfile.mkdtemp(prefix="orbit_pol_out3_"))
        self.addCleanup(
            lambda: __import__("shutil").rmtree(outside, ignore_errors=True)
        )
        target = outside / "x.txt"
        self.assertTrue(self.engine.approve_path(str(target)))
        d = self.engine.check("file", "write", path=str(target), mutate=True)
        self.assertTrue(d.allowed)
        entries = self.engine.get_audit_log(10)
        self.assertIn("file.write", str(entries))

    def test_path_traversal_blocked(self):
        import tempfile

        outside = Path(tempfile.mkdtemp(prefix="orbit_pol_out4_"))
        self.addCleanup(
            lambda: __import__("shutil").rmtree(outside, ignore_errors=True)
        )
        evil = str(self.workspace / ".." / ".." / outside.name / "escape.txt")
        d = self.engine.check("file", "delete", path=evil, mutate=True)
        self.assertFalse(d.allowed)

    def test_low_risk_auto_allowed(self):
        d = self.engine.check("file", "read", path=str(self.workspace / "r.txt"))
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "low_risk_auto")

    def test_medium_risk_audited(self):
        d = self.engine.check(
            "file", "write", path=str(self.workspace / "m.txt"), mutate=True
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "medium_risk_audited")
        self.assertTrue(d.audit_id)

    def test_risk_map(self):
        from orbit.orbit.core.policy_engine import TOOL_ACTION_RISK, RiskLevel

        self.assertEqual(TOOL_ACTION_RISK["github.delete_repo"], RiskLevel.CRITICAL)
        self.assertEqual(TOOL_ACTION_RISK["github.merge_pr"], RiskLevel.CRITICAL)
        self.assertEqual(TOOL_ACTION_RISK["desktop.ps"], RiskLevel.HIGH)
        self.assertEqual(TOOL_ACTION_RISK["file.write"], RiskLevel.MEDIUM)
        self.assertEqual(TOOL_ACTION_RISK["system.command"], RiskLevel.HIGH)
        self.assertEqual(TOOL_ACTION_RISK["file.read"], RiskLevel.LOW)

    def test_strict_mode_blocks_high(self):
        self.engine.strict = True
        d = self.engine.check("desktop", "ps")
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "strict_mode_requires_approval")

    def test_approve_action_unblocks_high(self):
        self.engine.strict = True
        self.engine.approve_action("desktop.ps")
        d = self.engine.check("desktop", "ps")
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "approved")

    def test_audit_log_redacts_secrets(self):
        self.engine.check(
            "file",
            "write",
            path=str(self.workspace / "s.txt"),
            mutate=True,
            details="token=sk-abcdef1234567890",
        )
        entries = self.engine.get_audit_log(10)
        self.assertTrue(entries)
        blob = str(entries)
        self.assertNotIn("sk-abcdef1234567890", blob)
        self.assertIn("[REDACTED]", blob)

    def test_audit_tracks_actions(self):
        self.engine.check(
            "file", "write", path=str(self.workspace / "t.txt"), mutate=True
        )
        self.engine.check(
            "file", "delete", path=str(self.workspace / "t.txt"), mutate=True
        )
        actions = {e.get("action") for e in self.engine.get_audit_log(10)}
        self.assertIn("file.write", actions)
        self.assertIn("file.delete", actions)


class TestConfigValidator(unittest.TestCase):
    def test_validation_result(self):
        from orbit.orbit.core.config_validator import validate_all

        result = validate_all()
        self.assertIsInstance(result.errors, list)
        self.assertIsInstance(result.warnings, list)
        self.assertIsInstance(result.info, list)
        self.assertIn(result.is_valid(), (True, False))

    def test_validate_api_key(self):
        from orbit.orbit.core.config_validator import validate_api_key

        self.assertIsNone(validate_api_key("K", "real-key-123"))
        self.assertIsNotNone(validate_api_key("K", ""))
        self.assertIsNotNone(
            validate_api_key("K", "your_placeholder_here", ("your_placeholder",))
        )

    def test_validate_url(self):
        from orbit.orbit.core.config_validator import validate_url

        self.assertIsNone(validate_url("U", "http://localhost:5000"))
        self.assertIsNotNone(validate_url("U", "ftp://bad"))

    def test_validate_port(self):
        from orbit.orbit.core.config_validator import validate_port

        self.assertIsNone(validate_port("P", "5000"))
        self.assertIsNotNone(validate_port("P", "70000"))
        self.assertIsNotNone(validate_port("P", "abc"))

    def test_log_validation_runs(self):
        from orbit.orbit.core.config_validator import log_validation, validate_all

        log_validation(validate_all())


if __name__ == "__main__":
    unittest.main()
