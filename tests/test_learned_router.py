"""Tests for learned_router — RouteLLM integration for ORBIT."""

import os

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")

from orbit.orbit.core.learned_router import (
    LearnedRouter,
    RouterStats,
    RoutingDecision,
    get_learned_router,
)


class TestRoutingDecision:
    def test_to_dict(self):
        d = RoutingDecision(
            query="hello world",
            win_rate=0.75,
            use_strong=True,
            threshold=0.5,
            latency_ms=12.3,
            router_type="mf",
            strong_model="gpt-4",
            weak_model="ollama/qwen",
        )
        result = d.to_dict()
        assert result["win_rate"] == 0.75
        assert result["use_strong"] is True
        assert result["latency_ms"] == 12.3
        assert result["query"] == "hello world"

    def test_query_truncated(self):
        d = RoutingDecision(
            query="x" * 200,
            win_rate=0.5,
            use_strong=False,
            threshold=0.5,
            latency_ms=5.0,
            router_type="mf",
            strong_model="gpt-4",
            weak_model="ollama",
        )
        assert len(d.to_dict()["query"]) <= 100


class TestRouterStats:
    def test_empty_stats(self):
        s = RouterStats()
        d = s.to_dict()
        assert d["total_queries"] == 0
        assert d["estimated_cost_savings_pct"] == 0.0

    def test_record_strong(self):
        s = RouterStats()
        dec = RoutingDecision("q", 0.8, True, 0.5, 10.0, "mf", "gpt-4", "ollama")
        s.record(dec)
        assert s.total_queries == 1
        assert s.strong_routed == 1
        assert s.weak_routed == 0

    def test_record_weak(self):
        s = RouterStats()
        dec = RoutingDecision("q", 0.2, False, 0.5, 10.0, "mf", "gpt-4", "ollama")
        s.record(dec)
        assert s.weak_routed == 1
        assert s.estimated_cost_savings_pct > 0

    def test_mixed_routing(self):
        s = RouterStats()
        for i in range(10):
            use_strong = i % 2 == 0
            dec = RoutingDecision(
                "q", 0.5, use_strong, 0.5, 10.0, "mf", "gpt-4", "ollama"
            )
            s.record(dec)
        assert s.total_queries == 10
        assert s.strong_routed == 5
        assert s.weak_routed == 5


class TestLearnedRouter:
    def test_singleton(self):
        r1 = get_learned_router()
        r2 = get_learned_router()
        assert r1 is r2

    def test_fallback_mode(self):
        """Without RouteLLM installed, should use heuristic fallback."""
        router = LearnedRouter()
        decision = router.route("What is 2+2?")
        assert isinstance(decision, RoutingDecision)
        assert decision.router_type == "heuristic-fallback"
        assert 0.0 <= decision.win_rate <= 1.0

    def test_short_query_weak(self):
        router = LearnedRouter(threshold=0.5)
        decision = router.route("hi")
        # Short query should have low complexity → weak model
        assert decision.use_strong is False

    def test_long_query_strong(self):
        router = LearnedRouter(threshold=0.2)
        decision = router.route(
            "Explain the mathematical proof of the fundamental theorem of calculus in detail with step by step derivation and examples from real analysis and also discuss the applications in modern physics and engineering problems"
        )
        # Long complex query should have higher complexity
        assert decision.win_rate > 0.2

    def test_custom_threshold(self):
        router = LearnedRouter(threshold=0.9)
        decision = router.route("hello")
        # Very high threshold → almost everything routes to weak
        assert decision.use_strong is False

    def test_stats_tracked(self):
        router = LearnedRouter()
        router.route("test query one")
        router.route("test query two")
        assert router.stats.total_queries == 2

    def test_get_status(self):
        router = LearnedRouter()
        status = router.get_status()
        assert "router_type" in status
        assert "threshold" in status
        assert "stats" in status

    def test_calibrate(self):
        router = LearnedRouter()
        threshold = router.calibrate(0.3)
        assert isinstance(threshold, float)
        assert 0.0 <= threshold <= 1.0
