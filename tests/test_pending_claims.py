"""Claim-closure verification tests for the CLAIMED rows in
validation/claim_verification_table.md (run 2026-10-07).

New behavioral evidence written here:
  TestContextRouting      - context-aware routing (history changes decisions)
  TestQualityGateBehavior - unnecessary refinement prevented + false positive rate
  TestNoDuplicateIDs      - concurrent ID generators (notification, procedures)
  TestNoResourceLeaks     - bounded-structure churn (turns/chunks/cache + RSS)

The remaining pending claims are verified by re-running existing suites
(evidence recorded in the claim table notes):
  rolling summary      -> tests/test_tier1_competition.py::TestContextWindow
  consolidation        -> tests/test_overkill_batch3.py::TestMemoryConsolidation
  circuit breaker      -> TestCircuitBreaker + tests/test_circuit_breaker_unit.py
  fallback chain       -> tests/test_tier3_reliability.py
  ToolGate blocks ops  -> TestPolicyEngine (tier1) + tests/test_toolgate_bp.py
  browser claims       -> live probe (BrowserTool + SmartBrowser vs local server)
  battle 93% (56/60)   -> re-derived from raw rounds in orbit_data/battle_v2_latest.json
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from orbit.orbit.core.smart_router import get_smart_router


class TestContextRouting(unittest.TestCase):
    """Claim: Context-aware routing works (core/smart_router.py)."""

    TEXT = "write a short poem about the rain"

    def test_history_boost_marks_context(self):
        router = get_smart_router()
        base = router.route(self.TEXT)
        self.assertTrue(base.agents, "expected agent matches for probe text")
        # history whose top agent equals the current top agent twice triggers
        # the Step-2.5 context-window boost (>=2 recent matches)
        boosted = router.route(self.TEXT, history=[self.TEXT, self.TEXT])
        self.assertTrue(boosted.agents)
        self.assertEqual(boosted.agents[0].label, base.agents[0].label)
        self.assertIn("+context", boosted.agents[0].reason)
        self.assertGreaterEqual(boosted.agents[0].score, base.agents[0].score)

    def test_no_history_no_context_marker(self):
        router = get_smart_router()
        result = router.route(self.TEXT, history=None)
        if result.agents:
            self.assertNotIn("+context", result.agents[0].reason)


class TestQualityGateBehavior(unittest.TestCase):
    """Claims: Unnecessary refinement prevented + False positive rate low
    (quality gate in core/conversation_engine.py)."""

    GOOD = (
        "Paris is the capital of France and its largest city. It is famous for "
        "the Eiffel Tower, the Louvre museum and its historic boulevards. The "
        "city has been a major political, economic and cultural center of "
        "Europe for centuries and remains one of the world's most visited "
        "destinations every single year."
    )
    BAD = "I don't know"

    def _run_engine(self, contents, message):
        from orbit.orbit.core.conversation_engine import ConversationEngine
        from orbit.orbit.core.llm.router import LLMResponse

        calls = []

        class _FakeRouter:
            async def generate(self, request):
                calls.append(request)
                idx = min(len(calls) - 1, len(contents) - 1)
                return LLMResponse(
                    content=contents[idx],
                    provider="mock",
                    model="fake",
                    latency_ms=1,
                    success=True,
                    used_cache=False,
                )

        engine = ConversationEngine()
        p1 = patch(
            "orbit.orbit.core.conversation_engine.get_router",
            return_value=_FakeRouter(),
        )
        p2 = patch.object(
            ConversationEngine, "_ground_web", new=AsyncMock(return_value=None)
        )
        p1.start()
        self.addCleanup(p1.stop)
        p2.start()
        self.addCleanup(p2.stop)
        result = engine.process(message, force_offline=True, skip_cache=True)
        return result, calls, engine

    def test_good_response_skips_refinement(self):
        result, calls, engine = self._run_engine(
            [self.GOOD], "what exactly is the capital city of france"
        )
        self.assertEqual(
            len(calls),
            1,
            "good answer must not trigger a refinement call (skip is the claim)",
        )
        self.assertIn("Paris", result.content)
        score = engine._assess_response_quality(
            "what exactly is the capital city of france", self.GOOD, "general"
        )
        self.assertGreaterEqual(score, 0.3)

    def test_bad_response_triggers_one_refinement(self):
        result, calls, _engine = self._run_engine(
            [self.BAD, self.GOOD], "which city is the capital of france"
        )
        self.assertEqual(len(calls), 2, "bad answer must be refined exactly once")
        self.assertTrue(
            calls[1].prompt.startswith("Answer this concisely"),
            "second call must be the refinement pass",
        )
        self.assertIn("Paris", result.content)

    def test_false_positive_rate_low_on_correct_answers(self):
        import json

        candidates = [
            Path("orbit_data") / "ground_truth_eval.json",
        ]
        try:
            from orbit.orbit.core.runtime_paths import orbit_data_dir

            candidates.insert(0, Path(orbit_data_dir()) / "ground_truth_eval.json")
        except Exception:
            pass
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            self.skipTest("orbit_data/ground_truth_eval.json not present")

        data = json.loads(path.read_text(encoding="utf-8"))
        results = data.get("results") or []
        correct = [r for r in results if r.get("correct")]
        self.assertGreaterEqual(len(correct), 80, "need a fresh ground-truth eval")

        from orbit.orbit.core.conversation_engine import ConversationEngine

        scorer = ConversationEngine()

        def flagged(resp, query):
            return scorer._assess_response_quality(query, resp, "general") < 0.3

        # Substantive correct answers (>=15 words): quality IS visible there,
        # so a flag on those is a genuine false positive.
        substantive = [
            (r.get("prompt", ""), r.get("response") or "")
            for r in correct
            if len((r.get("response") or "").split()) >= 15
        ]
        self.assertTrue(substantive, "no substantive correct answers found")
        fp = [(q, resp) for q, resp in substantive if flagged(resp, q)]
        fpr = len(fp) / len(substantive)
        self.assertLess(
            fpr,
            0.10,
            f"{len(fp)}/{len(substantive)} correct answers flagged: {fp[:3]}",
        )
        # Report both numbers for the claim note (short answers like "39" are
        # correct but look low-quality to any heuristic - counted separately).
        all_flagged = sum(
            1 for r in correct if flagged(r.get("response") or "", r.get("prompt", ""))
        )
        print(
            f"\n[FPR] substantive: {len(fp)}/{len(substantive)} = {fpr:.3f}; "
            f"all-correct flagged: {all_flagged}/{len(correct)}"
        )


class TestNoDuplicateIDs(unittest.TestCase):
    """Claim: No duplicate IDs (concurrent ID generators)."""

    def test_concurrent_notification_ids_unique(self):
        from orbit.orbit.core.notification_center import NotificationCenter

        center = NotificationCenter()
        center._save = lambda *a, **k: None  # keep the test off disk
        ids: list = []
        errors: list = []
        lock = threading.Lock()

        def worker():
            try:
                for _ in range(50):
                    n = center.add_notification(
                        "info", "claim-test", "id uniqueness probe"
                    )
                    with lock:
                        ids.append(n["id"])
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertFalse(errors, errors)
        self.assertEqual(len(ids), 400)
        self.assertEqual(
            len(set(ids)), 400, "duplicate notification ids under concurrency"
        )

    def test_concurrent_procedure_ids_unique(self):
        from orbit.orbit.core.procedural_memory import ProceduralMemory

        with tempfile.TemporaryDirectory() as td:
            pm = ProceduralMemory(storage_file=str(Path(td) / "pm.json"))
            ids: list = []
            errors: list = []
            lock = threading.Lock()

            def worker(wid: int):
                try:
                    for i in range(50):
                        pid = pm.store_procedure(
                            name=f"proc-{wid}-{i}", steps=["step one", "step two"]
                        )
                        with lock:
                            ids.append(pid)
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(exc)

            threads = [
                threading.Thread(target=worker, args=(w,)) for w in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)
            self.assertFalse(errors, errors)
            self.assertEqual(len(ids), 400)
            self.assertEqual(
                len(set(ids)), 400, "duplicate procedure ids under concurrency"
            )


class TestNoResourceLeaks(unittest.TestCase):
    """Claim: No leaked resources (bounded structures under heavy churn)."""

    def test_bounded_structures_churn_no_rss_leak(self):
        try:
            import psutil
        except ImportError:  # pragma: no cover
            self.skipTest("psutil not installed")

        import gc

        from orbit.orbit.core.context_manager import ContextManager
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import LLMResponseCache

        # summary_every huge: churn must not trigger LLM summarization
        cm = ContextManager(summary_every=10**9)
        # offline/deterministic retrieval: no embedding HTTP during churn
        cm._retriever.set_embedder(lambda _t: None)
        cache = LLMResponseCache(max_size=500)

        for i in range(200):  # warm-up past live-window eviction
            cm.add_turn("user", f"warmup {i} " + "pad " * 30)
        gc.collect()
        proc = psutil.Process()
        rss0 = proc.memory_info().rss
        h0 = proc.num_handles() if hasattr(proc, "num_handles") else None

        payload = "churn payload " + "x" * 480
        for i in range(20000):
            cm.add_turn("user" if i % 2 == 0 else "assistant", f"turn {i} {payload}")
            if i % 200 == 0:
                cm.build_history(f"query {i}")  # exercise retrieval path
        for i in range(8000):
            cache.set(
                LLMRequest(prompt=f"unique prompt {i} " + "y" * 200),
                LLMResponse(
                    content="r" * 400,
                    provider="mock",
                    model="m",
                    latency_ms=1,
                ),
            )
        gc.collect()
        rss_delta_mb = (proc.memory_info().rss - rss0) / (1024 * 1024)

        # structural bounds (the real invariant)
        self.assertLessEqual(len(cm._turns), cm.max_chunk_turns, "turn list unbounded")
        self.assertLessEqual(
            cm._retriever.size, cm._retriever.max_docs, "chunk index unbounded"
        )
        stats = cache.get_stats()
        self.assertLessEqual(stats["size"], stats["max_size"], "cache unbounded")

        # RSS guard: unbounded growth here would be >= ~60MB
        self.assertLess(
            rss_delta_mb,
            30.0,
            f"RSS grew {rss_delta_mb:.1f}MB over bounded churn",
        )
        if h0 is not None:
            h_delta = proc.num_handles() - h0
            self.assertLess(abs(h_delta), 60, f"handle delta {h_delta}")


if __name__ == "__main__":
    unittest.main()
