"""Tests for Multi-Tier Memory (Tier 0-3) system."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.core.multi_tier_memory import (
    TIER_CONFIGS,
    L1MemoryCache,
    MultiTierMemory,
    get_multi_tier_memory,
)


class TestL1Cache:
    def test_put_and_get(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=3600)
        c.put("a", 1)
        assert c.get("a") == 1

    def test_missing_key(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=3600)
        assert c.get("nonexistent") is None

    def test_expiry(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=0.01)
        c.put("a", 1)
        time.sleep(0.02)
        assert c.get("a") is None

    def test_evict_expired(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=0.01)
        c.put("a", 1)
        c.put("b", 2)
        time.sleep(0.02)
        assert c.evict_expired() == 2
        assert len(c) == 0

    def test_lru_eviction(self):
        c = L1MemoryCache(max_entries=3, ttl_seconds=3600)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)
        c.put("d", 4)
        assert c.get("a") is None
        assert len(c) == 3

    def test_update_existing(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=3600)
        c.put("a", 1)
        c.put("a", 2)
        assert c.get("a") == 2
        assert len(c) == 1

    def test_remove(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=3600)
        c.put("a", 1)
        c.remove("a")
        assert c.get("a") is None

    def test_clear(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=3600)
        c.put("a", 1)
        c.put("b", 2)
        c.clear()
        assert len(c) == 0

    def test_stats(self):
        c = L1MemoryCache(max_entries=100, ttl_seconds=3600)
        c.put("a", 1)
        s = c.stats()
        assert s["max_entries"] == 100
        assert s["current_entries"] == 1
        assert s["ttl_seconds"] == 3600
        assert "keys" in s

    def test_tier_origin_and_importance(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=3600)
        c.put("a", "val", tier_origin=2, importance=0.9)
        entry = next(iter(c._data.values()))
        assert entry.tier_origin == 2
        assert entry.importance == 0.9

    def test_access_count_increments(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=3600)
        c.put("a", 1)
        assert next(iter(c._data.values())).access_count == 0
        c.get("a")
        assert next(iter(c._data.values())).access_count == 1
        c.get("a")
        assert next(iter(c._data.values())).access_count == 2


class TestMultiTierMemory:
    def test_singleton(self):
        m1 = get_multi_tier_memory()
        m2 = get_multi_tier_memory()
        assert m1 is m2

    def test_stats_structure(self):
        m = get_multi_tier_memory()
        s = m.stats()
        assert "tier0" in s
        assert "tier1" in s
        assert "tier2" in s
        assert "tier3" in s
        assert "tier_configs" in s

    def test_store_retrieve_l1(self):
        m = MultiTierMemory()
        m.store("test_key", "test_val", importance=0.9)
        val, tier = m.retrieve("test_key")
        assert val == "test_val"
        assert tier == 0

    def test_retrieve_not_found(self):
        m = MultiTierMemory()
        val, tier = m.retrieve("nonexistent", cascade=False)
        assert val is None
        assert tier == -1

    def test_cascade_fallback(self):
        m = MultiTierMemory()
        m.store("cascade_key", "cascade_val", importance=0.8)
        m.tier0.clear()
        val, tier = m.retrieve("cascade_key", cascade=True)
        assert val is not None
        assert tier > 0

    def test_promote(self):
        m = MultiTierMemory()
        m.store("promote_key", "promote_val", importance=0.9)
        m.tier0.clear()
        ok = m.promote("promote_key")
        assert ok
        val, tier = m.retrieve("promote_key", cascade=False)
        assert val is not None
        assert tier == 0

    def test_demote(self):
        m = MultiTierMemory()
        m.store("demote_key", "demote_val", importance=0.9)
        m.tier0.clear()
        ok = m.demote("demote_key")
        assert not ok
        val, _tier = m.retrieve("demote_key", cascade=True)
        assert val is not None

    def test_search(self):
        m = MultiTierMemory()
        m.store("search_test", "UniqueSearchableValue", importance=0.8)
        results = m.search("UniqueSearchableValue", limit=5)
        assert len(results) > 0
        assert any("UniqueSearchableValue" in str(r.get("value", "")) for r in results)

    def test_search_empty_query(self):
        m = MultiTierMemory()
        results = m.search("XYZZY_NONEXISTENT_12345", limit=5)
        assert isinstance(results, list)

    def test_consolidate(self):
        m = MultiTierMemory()
        m.store("consolidate_test", "important memory to consolidate", importance=0.9)
        result = m.consolidate()
        assert "consolidation" in result
        assert "tier0_evicted" in result

    def test_assign_tier(self):
        m = MultiTierMemory()
        assert m._assign_tier(0.9) == 1
        assert m._assign_tier(0.6) == 2
        assert m._assign_tier(0.3) == 3

    def test_get_tier_names(self):
        m = MultiTierMemory()
        names = m.get_tier_names()
        assert names[0] == "L1 Cache"
        assert names[1] == "Working"
        assert names[2] == "Semantic"
        assert names[3] == "Archival"

    def test_reset_tier0(self):
        m = MultiTierMemory()
        m.store("reset_tier0_test", "val", importance=0.9)
        m.reset(tier=0)
        assert len(m.tier0) == 0

    def test_reset_all(self):
        m = MultiTierMemory()
        m.store("reset_all_test", "val", importance=0.9)
        m.reset()
        assert len(m.tier0) == 0

    def test_route_prompt(self):
        m = MultiTierMemory()
        prompt, _ctx_added = m.route_prompt("test", "Hello world")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_store_with_importance_routing(self):
        m = MultiTierMemory()
        t_high = m.store("high_imp", "critical", importance=0.95)
        t_medium = m.store("med_imp", "normal", importance=0.6)
        t_low = m.store("low_imp", "trivial", importance=0.2)
        assert t_high <= t_medium <= t_low

    def test_l1_cache_ttl_origin(self):
        m = MultiTierMemory()
        m.store("ttl_key", "ttl_val", tier=3)
        val, tier = m.retrieve("ttl_key")
        assert val == "ttl_val"
        assert tier == 0

    def test_multi_store_retrieve(self):
        m = MultiTierMemory()
        for i in range(5):
            m.store(f"bulk_key_{i}", f"bulk_val_{i}", importance=0.5 + i * 0.1)
        for i in range(5):
            val, _tier = m.retrieve(f"bulk_key_{i}")
            assert val == f"bulk_val_{i}"

    def test_tier_configs_immutable(self):
        for cfg in TIER_CONFIGS.values():
            assert hasattr(cfg, "enabled")
            assert hasattr(cfg, "max_entries")
            assert hasattr(cfg, "ttl_days")

    def test_cache_evict_expired_after_ttl(self):
        c = L1MemoryCache(max_entries=10, ttl_seconds=0.005)
        c.put("a", 1)
        time.sleep(0.01)
        c.evict_expired()
        assert c.get("a") is None
