"""
Unit tests for orbit.orbit.core.cache_manager (previously 0% covered).

Covers TTL expiry, LRU eviction, namespaces, persistence and statistics.
"""

import json
import time

import pytest

from orbit.orbit.core import cache_manager as cm
from orbit.orbit.core.cache_manager import CacheManager


@pytest.fixture
def cache(tmp_path):
    return CacheManager(max_size=5, default_ttl=60,
                        storage_file=str(tmp_path / "cache.json"))


class TestGetSet:
    def test_set_then_get(self, cache):
        cache.set("api", "user:1", {"name": "jarves"})
        assert cache.get("api", "user:1") == {"name": "jarves"}

    def test_get_missing_returns_none_and_counts_miss(self, cache):
        assert cache.get("api", "nope") is None
        assert cache.get_stats()["misses"] == 1

    def test_namespaces_are_isolated(self, cache):
        cache.set("a", "k", 1)
        cache.set("b", "k", 2)
        assert cache.get("a", "k") == 1
        assert cache.get("b", "k") == 2

    def test_set_overwrites_existing_value(self, cache):
        cache.set("a", "k", 1)
        cache.set("a", "k", 2)
        assert cache.get("a", "k") == 2
        assert cache.get_stats()["size"] == 1

    def test_set_many_and_get_many(self, cache):
        cache.set_many("bulk", {"a": 1, "b": 2})
        assert cache.get_many("bulk", ["a", "b", "missing"]) == {"a": 1, "b": 2}


class TestExpiry:
    def test_expired_entry_is_a_miss(self, cache):
        cache.set("api", "k", "v", ttl=-1)
        assert cache.get("api", "k") is None
        assert cache.get_stats()["misses"] == 1

    def test_expired_entry_is_removed_from_cache(self, cache):
        cache.set("api", "k", "v", ttl=-1)
        cache.get("api", "k")
        assert cache.get_stats()["size"] == 0

    def test_exists_false_for_expired(self, cache):
        cache.set("api", "k", "v", ttl=-1)
        assert cache.exists("api", "k") is False

    def test_exists_true_for_live_entry(self, cache):
        cache.set("api", "k", "v")
        assert cache.exists("api", "k") is True

    def test_exists_false_for_unknown_key(self, cache):
        assert cache.exists("api", "ghost") is False

    def test_cleanup_expired_drops_only_expired(self, cache):
        cache.set("api", "old", 1, ttl=-1)
        cache.set("api", "new", 2, ttl=60)
        cache.cleanup_expired()
        assert cache.get_stats()["size"] == 1
        assert cache.get("api", "new") == 2

    def test_default_ttl_is_applied(self, tmp_path):
        c = CacheManager(default_ttl=120, storage_file=str(tmp_path / "c.json"))
        before = time.time()
        c.set("ns", "k", "v")
        assert c.ttls["ns:k"] >= before + 120


class TestEviction:
    def test_lru_evicts_oldest_entry(self, cache):
        for i in range(5):
            cache.set("ns", f"k{i}", i)
        cache.set("ns", "k5", 5)
        assert cache.get("ns", "k0") is None
        assert cache.get("ns", "k5") == 5

    def test_eviction_counted_in_stats(self, cache):
        for i in range(6):
            cache.set("ns", f"k{i}", i)
        assert cache.get_stats()["evictions"] == 1

    def test_recently_read_entry_survives_eviction(self, cache):
        for i in range(5):
            cache.set("ns", f"k{i}", i)
        cache.get("ns", "k0")
        cache.set("ns", "k5", 5)
        assert cache.get("ns", "k0") == 0
        assert cache.get("ns", "k1") is None

    def test_size_never_exceeds_max_size(self, cache):
        for i in range(20):
            cache.set("ns", f"k{i}", i)
        assert cache.get_stats()["size"] <= 5


class TestDeleteAndClear:
    def test_delete_existing_returns_true(self, cache):
        cache.set("ns", "k", "v")
        assert cache.delete("ns", "k") is True
        assert cache.get("ns", "k") is None

    def test_delete_missing_returns_false(self, cache):
        assert cache.delete("ns", "k") is False

    def test_clear_namespace_keeps_other_namespaces(self, cache):
        cache.set("a", "k", 1)
        cache.set("b", "k", 2)
        cache.clear("a")
        assert cache.get("a", "k") is None
        assert cache.get("b", "k") == 2

    def test_clear_all(self, cache):
        cache.set("a", "k", 1)
        cache.set("b", "k", 2)
        cache.clear()
        assert cache.get_stats()["size"] == 0
        assert cache.ttls == {}


class TestGetOrSet:
    def test_factory_used_on_miss(self, cache):
        assert cache.get_or_set("ns", "k", lambda: "made") == "made"
        assert cache.get("ns", "k") == "made"

    def test_factory_skipped_on_hit(self, cache):
        cache.set("ns", "k", "cached")
        calls = []

        def factory():
            calls.append(1)
            return "made"

        assert cache.get_or_set("ns", "k", factory) == "cached"
        assert calls == []


class TestStatsAndNamespaces:
    def test_hit_rate(self, cache):
        cache.set("ns", "k", 1)
        cache.get("ns", "k")
        cache.get("ns", "missing")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0
        assert stats["total_requests"] == 2

    def test_hit_rate_zero_without_requests(self, cache):
        assert cache.get_stats()["hit_rate"] == 0

    def test_max_size_reported(self, cache):
        assert cache.get_stats()["max_size"] == 5

    def test_get_namespaces_counts_keys(self, cache):
        cache.set("a", "k1", 1)
        cache.set("a", "k2", 2)
        cache.set("b", "k1", 3)
        assert cache.get_namespaces() == {"a": 2, "b": 1}


class TestPersistence:
    def test_values_survive_reload(self, tmp_path):
        path = str(tmp_path / "cache.json")
        CacheManager(storage_file=path).set("ns", "k", "v")
        assert CacheManager(storage_file=path).get("ns", "k") == "v"

    def test_saved_file_has_expected_shape(self, tmp_path):
        path = tmp_path / "cache.json"
        CacheManager(storage_file=str(path)).set("ns", "k", "v")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["cache"] == {"ns:k": "v"}
        assert "ns:k" in data["ttls"]

    def test_corrupt_storage_file_is_tolerated(self, tmp_path):
        path = tmp_path / "cache.json"
        path.write_text("not json", encoding="utf-8")
        c = CacheManager(storage_file=str(path))
        assert c.get_stats()["size"] == 0


class TestModuleLevelApi:
    @pytest.fixture(autouse=True)
    def _isolated_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cm, "_cache_manager",
                            CacheManager(storage_file=str(tmp_path / "cache.json")))

    def test_get_cache_manager_is_singleton(self):
        assert cm.get_cache_manager() is cm.get_cache_manager()

    def test_set_get_delete(self):
        cm.set("ns", "k", "v")
        assert cm.get("ns", "k") == "v"
        assert cm.delete("ns", "k") is True

    def test_get_or_set_and_stats(self):
        assert cm.get_or_set("ns", "k", lambda: 7) == 7
        assert cm.get_stats()["size"] == 1
