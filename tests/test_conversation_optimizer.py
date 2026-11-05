"""Tests for conversation_optimizer module."""

import os
import threading

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")

from orbit.orbit.core.conversation_optimizer import (
    ConversationOptimizer,
    LatencyTracker,
    ResponseCache,
    get_conversation_optimizer,
)


class TestResponseCache:
    def test_put_and_get(self):
        c = ResponseCache()
        c.put("k1", {"text": "hello"})
        assert c.get("k1") == {"text": "hello"}

    def test_get_miss(self):
        c = ResponseCache()
        assert c.get("nonexistent") is None

    def test_hit_increments(self):
        c = ResponseCache()
        c.put("k", {"text": "x"})
        c.get("k")
        stats = c.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0

    def test_miss_increments(self):
        c = ResponseCache()
        c.get("miss")
        stats = c.get_stats()
        assert stats["misses"] == 1

    def test_hit_rate(self):
        c = ResponseCache()
        c.put("k", {"text": "x"})
        c.get("k")  # hit
        c.get("miss")  # miss
        stats = c.get_stats()
        assert stats["hit_rate_pct"] == 50.0

    def test_clear(self):
        c = ResponseCache()
        c.put("k", {"text": "x"})
        c.get("k")  # 1 hit
        c.clear()
        assert c.get("k") is None  # miss after clear
        stats = c.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1  # the get after clear

    def test_lru_eviction(self):
        import orbit.orbit.core.conversation_optimizer as mod

        old_max = mod.CACHE_MAX_ENTRIES
        mod.CACHE_MAX_ENTRIES = 2
        try:
            c = ResponseCache()
            c.put("a", {"text": "1"})
            c.put("b", {"text": "2"})
            c.put("c", {"text": "3"})  # evicts "a"
            assert c.get("a") is None
            assert c.get("b") == {"text": "2"}
            assert c.get("c") == {"text": "3"}
        finally:
            mod.CACHE_MAX_ENTRIES = old_max

    def test_overwrite_moves_to_end(self):
        c = ResponseCache()
        c.put("k", {"text": "old"})
        c.put("k", {"text": "new"})
        assert c.get("k") == {"text": "new"}

    def test_thread_safety(self):
        c = ResponseCache()
        errors = []

        def writer():
            try:
                for i in range(50):
                    c.put(f"k{i}", {"text": str(i)})
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        def reader():
            try:
                for i in range(50):
                    c.get(f"k{i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


class TestLatencyTracker:
    def test_record_and_stats(self):
        lt = LatencyTracker()
        lt.record("simple", 100)
        lt.record("simple", 200)
        stats = lt.get_stats("simple")
        assert stats["count"] == 2
        assert stats["avg_ms"] == 150.0

    def test_empty_stats(self):
        lt = LatencyTracker()
        stats = lt.get_stats("nonexistent")
        assert stats["count"] == 0
        assert stats["avg_ms"] == 0

    def test_p50_p95(self):
        lt = LatencyTracker()
        for i in range(100):
            lt.record("simple", float(i))
        stats = lt.get_stats("simple")
        assert stats["p50_ms"] == 49.0 or stats["p50_ms"] == 50.0
        assert stats["p95_ms"] >= 90

    def test_all_types(self):
        lt = LatencyTracker()
        lt.record("simple", 100)
        lt.record("complex", 500)
        stats = lt.get_stats()
        assert stats["count"] == 2

    def test_on_target(self):
        lt = LatencyTracker()
        lt.record("simple", 100)  # below 500ms target
        stats = lt.get_stats("simple")
        assert stats["on_target"] is True

    def test_over_target(self):
        lt = LatencyTracker()
        lt.record("simple", 1000)  # above 500ms target
        stats = lt.get_stats("simple")
        assert stats["on_target"] is False

    def test_max_entries_per_type(self):
        lt = LatencyTracker()
        for i in range(1100):
            lt.record("simple", float(i))
        stats = lt.get_stats("simple")
        assert stats["count"] <= 1000


class TestConversationOptimizer:
    def test_singleton(self):
        a = get_conversation_optimizer()
        b = get_conversation_optimizer()
        assert a is b

    def test_cache_response_and_get(self):
        opt = ConversationOptimizer()
        opt.reset()
        opt.cache_response("hello world", {"text": "hi there"})
        result = opt.get_cached_response("hello world")
        assert result == {"text": "hi there"}

    def test_cache_miss(self):
        opt = ConversationOptimizer()
        opt.reset()
        assert opt.get_cached_response("nonexistent") is None

    def test_record_latency(self):
        opt = ConversationOptimizer()
        opt.record_latency("simple", 150)
        stats = opt.get_latency_stats("simple")
        assert stats["count"] == 1

    def test_get_stats(self):
        opt = ConversationOptimizer()
        opt.reset()
        stats = opt.get_stats()
        assert "cache" in stats
        assert "latency" in stats
        assert "context_cache_size" in stats

    def test_reset(self):
        opt = ConversationOptimizer()
        opt.cache_response("q", {"text": "a"})
        opt.reset()
        assert opt.get_cached_response("q") is None

    def test_context_cache(self):
        opt = ConversationOptimizer()
        opt.reset()
        history = [{"role": "user", "content": "hi"}]
        opt.cache_context("hello", history, {"ctx": "data"})
        result = opt.get_cached_context("hello", history)
        assert result == {"ctx": "data"}

    def test_context_cache_miss(self):
        opt = ConversationOptimizer()
        opt.reset()
        assert opt.get_cached_context("x", []) is None
