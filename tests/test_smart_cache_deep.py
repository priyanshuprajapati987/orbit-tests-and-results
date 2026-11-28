"""Deep tests for orbit/orbit/core/smart_cache.py (Loop 20/4)."""

import hashlib
import json
import math
import threading
import time
import unittest
from collections import OrderedDict
from pathlib import Path
from unittest import mock

from orbit.orbit.core import smart_cache as sc


class CacheEntryTests(unittest.TestCase):
    def test_defaults(self):
        e = sc.CacheEntry(key="k", query="q", response="r", category="general",
                          tokens_in=1, tokens_out=2, created_at=100.0, ttl=60)
        self.assertEqual(e.hits, 0)
        self.assertIsNone(e.embedding)

    def test_is_expired_ttl_zero_never(self):
        e = sc.CacheEntry(key="k", query="q", response="r", category="g",
                          tokens_in=0, tokens_out=0, created_at=0.0, ttl=0)
        with mock.patch("time.time", return_value=999999.0):
            self.assertFalse(e.is_expired)

    def test_is_expired_true(self):
        e = sc.CacheEntry(key="k", query="q", response="r", category="g",
                          tokens_in=0, tokens_out=0, created_at=100.0, ttl=10)
        with mock.patch("time.time", return_value=200.0):
            self.assertTrue(e.is_expired)

    def test_is_expired_false(self):
        e = sc.CacheEntry(key="k", query="q", response="r", category="g",
                          tokens_in=0, tokens_out=0, created_at=100.0, ttl=1000)
        with mock.patch("time.time", return_value=150.0):
            self.assertFalse(e.is_expired)

    def test_age_seconds(self):
        e = sc.CacheEntry(key="k", query="q", response="r", category="g",
                          tokens_in=0, tokens_out=0, created_at=100.0, ttl=10)
        with mock.patch("time.time", return_value=150.0):
            self.assertEqual(e.age_seconds, 50.0)


class NormalizeTokenizeTests(unittest.TestCase):
    def test_normalize_lowercases_and_strips(self):
        c = sc.SmartCache.__new__(sc.SmartCache)
        c._data_dir = Path("/tmp/x")
        c._entries = OrderedDict()
        c._stats = {}
        c._lock = threading.RLock()
        self.assertEqual(c._normalize("  Hello World!  "), "hello world")

    def test_normalize_removes_stop_words(self):
        c = sc.SmartCache.__new__(sc.SmartCache)
        c._data_dir = Path("/tmp/x")
        c._entries = OrderedDict()
        c._stats = {}
        c._lock = threading.RLock()
        self.assertEqual(c._normalize("the cat is on the mat"), "cat mat")

    def test_normalize_short_words_removed(self):
        c = sc.SmartCache.__new__(sc.SmartCache)
        c._data_dir = Path("/tmp/x")
        c._entries = OrderedDict()
        c._stats = {}
        c._lock = threading.RLock()
        # "a" and "I" (len 1) removed
        self.assertEqual(c._normalize("a I am"), "am")

    def test_tokenize(self):
        c = sc.SmartCache.__new__(sc.SmartCache)
        c._data_dir = Path("/tmp/x")
        c._entries = OrderedDict()
        c._stats = {}
        c._lock = threading.RLock()
        self.assertEqual(c._tokenize("Hello World"), ["hello", "world"])


class CosineSimilarityTests(unittest.TestCase):
    def _c(self):
        c = sc.SmartCache.__new__(sc.SmartCache)
        c._data_dir = Path("/tmp/x")
        c._entries = OrderedDict()
        c._stats = {}
        c._lock = threading.RLock()
        return c

    def test_empty_a(self):
        self.assertEqual(self._c()._cosine_similarity([], ["a"]), 0.0)

    def test_empty_b(self):
        self.assertEqual(self._c()._cosine_similarity(["a"], []), 0.0)

    def test_no_common(self):
        self.assertEqual(self._c()._cosine_similarity(["a"], ["b"]), 0.0)

    def test_identical(self):
        self.assertAlmostEqual(self._c()._cosine_similarity(["a", "b"], ["a", "b"]), 1.0, places=9)

    def test_partial(self):
        score = self._c()._cosine_similarity(["a", "b", "c"], ["a", "b"])
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_mag_zero(self):
        # freq all zero impossible since tokens present; test common with zero freq not reachable
        # Just ensure no crash
        self.assertEqual(self._c()._cosine_similarity(["a"], ["a"]), 1.0)


class KeyTests(unittest.TestCase):
    def _c(self):
        c = sc.SmartCache.__new__(sc.SmartCache)
        c._data_dir = Path("/tmp/x")
        c._entries = OrderedDict()
        c._stats = {}
        c._lock = threading.RLock()
        return c

    def test_key_deterministic(self):
        c = self._c()
        k1 = c._key("Hello World", "general")
        k2 = c._key("hello world", "general")
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 16)

    def test_key_different_category(self):
        c = self._c()
        self.assertNotEqual(c._key("q", "general"), c._key("q", "facts"))


class InitLoadSaveTests(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_init_creates_data_dir(self):
        d = self._tmp()
        with mock.patch("pathlib.Path.mkdir") as mk:
            c = sc.SmartCache(data_dir=d)
        mk.assert_called_once_with(parents=True, exist_ok=True)
        self.assertTrue(hasattr(c, "_lock"))

    def test_init_default_data_dir(self):
        with mock.patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                        return_value=Path("/tmp/od")) as odd, \
                mock.patch("pathlib.Path.mkdir"):
            c = sc.SmartCache()
        odd.assert_called_once()
        self.assertEqual(c._data_dir, Path("/tmp/od") / "smart_cache")

    def test_load_existing(self):
        d = self._tmp()
        cache_file = d / "cache.json"
        cache_file.write_text(json.dumps({
            "entries": [{"key": "k1", "query": "q1", "response": "r1",
                         "category": "general", "tokens_in": 1, "tokens_out": 2,
                         "created_at": 100.0, "ttl": 300, "hits": 5}],
            "stats": {"hits": 10, "misses": 2, "semantic_hits": 3,
                      "exact_hits": 7, "expired_pruned": 1, "tokens_saved": 100},
        }), encoding="utf-8")
        with mock.patch("time.time", return_value=150.0):
            c = sc.SmartCache(data_dir=d)
        self.assertIn("k1", c._entries)
        self.assertEqual(c._entries["k1"].hits, 5)
        self.assertEqual(c._stats["hits"], 10)
        self.assertEqual(c._stats["misses"], 2)

    def test_load_expired_skipped(self):
        d = self._tmp()
        cache_file = d / "cache.json"
        cache_file.write_text(json.dumps({
            "entries": [{"key": "k1", "query": "q1", "response": "r1",
                         "category": "general", "tokens_in": 0, "tokens_out": 0,
                         "created_at": 100.0, "ttl": 10, "hits": 0}],
            "stats": {},
        }), encoding="utf-8")
        with mock.patch("time.time", return_value=200.0):
            c = sc.SmartCache(data_dir=d)
        self.assertNotIn("k1", c._entries)

    def test_load_corrupt(self):
        d = self._tmp()
        cache_file = d / "cache.json"
        cache_file.write_text("{bad", encoding="utf-8")
        c = sc.SmartCache(data_dir=d)
        self.assertEqual(len(c._entries), 0)

    def test_load_missing(self):
        d = self._tmp()
        c = sc.SmartCache(data_dir=d)
        self.assertEqual(len(c._entries), 0)

    def test_load_stats_partial_merge(self):
        d = self._tmp()
        cache_file = d / "cache.json"
        cache_file.write_text(json.dumps({
            "entries": [],
            "stats": {"hits": 5},  # partial
        }), encoding="utf-8")
        c = sc.SmartCache(data_dir=d)
        self.assertEqual(c._stats["hits"], 5)
        # other stats keep defaults (0)
        self.assertEqual(c._stats["misses"], 0)

    def test_save_success(self):
        d = self._tmp()
        c = sc.SmartCache(data_dir=d)
        c.set("hello world test", "response", category="general", tokens_in=1, tokens_out=2)
        cache_file = d / "cache.json"
        self.assertTrue(cache_file.exists())
        data = json.loads(cache_file.read_text("utf-8"))
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["query"], "hello world test")

    def test_save_failure_logged(self):
        d = self._tmp()
        c = sc.SmartCache(data_dir=d)
        with mock.patch.object(Path, "with_name", side_effect=OSError("boom")), \
                mock.patch.object(sc, "logger") as lg:
            c._save()
        lg.warning.assert_called_once()


class GetTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return sc.SmartCache(data_dir=d)

    def test_exact_hit(self):
        c = self._make()
        c.set("hello world test", "resp", category="general")
        with mock.patch("time.time", return_value=100.0):
            # created_at was time.time() at set time; need consistent
            pass
        # re-set with controlled time
        c2 = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c2.set("hello world test", "resp", category="general", tokens_in=5, tokens_out=3)
            r = c2.get("hello world test", category="general")
        self.assertEqual(r, "resp")
        self.assertEqual(c2._stats["hits"], 1)
        self.assertEqual(c2._stats["exact_hits"], 1)
        self.assertEqual(c2._stats["tokens_saved"], 8)

    def test_exact_hit_expired_returns_none(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("hello world test", "resp", category="general")
            # ttl=1800 (general). Set created_at far in past by mutating entry
            entry = c._entries[list(c._entries.keys())[0]]
            entry.created_at = 0.0
            entry.ttl = 1
            r = c.get("hello world test", category="general")
        self.assertIsNone(r)
        self.assertEqual(c._stats["misses"], 1)

    def test_semantic_hit(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("alpha beta gamma delta epsilon zeta eta", "resp",
                  category="general")
            r = c.get("alpha beta gamma delta epsilon zeta theta",
                      category="general")
        self.assertEqual(r, "resp")
        self.assertEqual(c._stats["semantic_hits"], 1)

    def test_semantic_below_threshold_miss(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("python programming tutorial", "resp", category="general")
            r = c.get("javascript framework", category="general")
        self.assertIsNone(r)
        self.assertEqual(c._stats["misses"], 1)

    def test_miss_no_entries(self):
        c = self._make()
        r = c.get("anything", category="general")
        self.assertIsNone(r)
        self.assertEqual(c._stats["misses"], 1)

    def test_expired_entry_skipped_in_semantic(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("hello world test", "resp", category="general")
            entry = list(c._entries.values())[0]
            entry.created_at = 0.0  # expired
            entry.ttl = 10
            r = c.get("hello world test", category="general")
        # exact key still matches but is_expired -> skip exact; semantic skips expired -> miss
        self.assertIsNone(r)

    def test_exact_key_different_category_miss(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("hello world test", "resp", category="general")
            r = c.get("hello world test", category="facts")
        # facts ttl=3600, set under general; different category key -> miss
        self.assertIsNone(r)

    def test_system_prompt_ignored(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q", "r", category="general")
            r = c.get("q", category="general", system_prompt="sp")
        self.assertEqual(r, "r")


class SetTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return sc.SmartCache(data_dir=d)

    def test_set_cacheable_category(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q", "r", category="general", tokens_in=5, tokens_out=3)
        self.assertEqual(len(c._entries), 1)
        e = list(c._entries.values())[0]
        self.assertEqual(e.query, "q")
        self.assertEqual(e.response, "r")
        self.assertEqual(e.category, "general")
        self.assertEqual(e.tokens_in, 5)
        self.assertEqual(e.tokens_out, 3)
        self.assertEqual(e.ttl, 1800)
        self.assertEqual(e.created_at, 1000.0)

    def test_set_non_cacheable_ttl_zero_returns(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q", "r", category="reasoning")
        self.assertEqual(len(c._entries), 0)

    def test_set_non_cacheable_creative(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q", "r", category="creative")
        self.assertEqual(len(c._entries), 0)

    def test_set_overwrites_same_key(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q", "r1", category="general")
            c.set("q", "r2", category="general")
        self.assertEqual(len(c._entries), 1)
        self.assertEqual(list(c._entries.values())[0].response, "r2")

    def test_set_unknown_category_uses_default_ttl(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q", "r", category="unknowncat")
        e = list(c._entries.values())[0]
        self.assertEqual(e.ttl, sc.DEFAULT_TTL)

    def test_set_facts_ttl(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q", "r", category="facts")
        e = list(c._entries.values())[0]
        self.assertEqual(e.ttl, 3600)

    def test_prune_when_over_limit(self):
        c = self._make()
        # lower MAX_ENTRIES for test
        with mock.patch("orbit.orbit.core.smart_cache.MAX_ENTRIES", 3), \
                mock.patch("orbit.orbit.core.smart_cache.PRUNE_BATCH", 1), \
                mock.patch("time.time", return_value=1000.0):
            for i in range(5):
                c.set(f"q{i}", f"r{i}", category="general")
        # pruned down
        self.assertLessEqual(len(c._entries), 3)

    def test_prune_removes_expired_first(self):
        c = self._make()
        with mock.patch("orbit.orbit.core.smart_cache.MAX_ENTRIES", 2), \
                mock.patch("orbit.orbit.core.smart_cache.PRUNE_BATCH", 1), \
                mock.patch("time.time", return_value=1000.0):
            c.set("q0", "r0", category="general")
            # make first expired
            e0 = list(c._entries.values())[0]
            e0.created_at = 0.0
            e0.ttl = 10
            c.set("q1", "r1", category="general")
            c.set("q2", "r2", category="general")
        # expired entry pruned
        self.assertNotIn(list(c._entries.values())[0].query if c._entries else "", ["q0"])


class PruneTests(unittest.TestCase):
    def test_prune_removes_expired(self):
        c = sc.SmartCache.__new__(sc.SmartCache)
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        c._data_dir = d
        c._entries = OrderedDict()
        c._stats = {"hits": 0, "misses": 0, "semantic_hits": 0,
                    "exact_hits": 0, "expired_pruned": 0, "tokens_saved": 0}
        c._lock = threading.RLock()
        # add expired entry manually
        e = sc.CacheEntry(key="k", query="q", response="r", category="g",
                          tokens_in=0, tokens_out=0, created_at=0.0, ttl=10)
        c._entries["k"] = e
        with mock.patch("time.time", return_value=1000.0):
            c._prune()
        self.assertEqual(len(c._entries), 0)
        self.assertEqual(c._stats["expired_pruned"], 1)

    def test_prune_removes_oldest_when_over_limit(self):
        c = sc.SmartCache.__new__(sc.SmartCache)
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        c._data_dir = d
        c._entries = OrderedDict()
        c._stats = {"hits": 0, "misses": 0, "semantic_hits": 0,
                    "exact_hits": 0, "expired_pruned": 0, "tokens_saved": 0}
        c._lock = threading.RLock()
        for i in range(5):
            e = sc.CacheEntry(key=f"k{i}", query=f"q{i}", response=f"r{i}",
                              category="g", tokens_in=0, tokens_out=0,
                              created_at=100.0, ttl=1000)
            c._entries[f"k{i}"] = e
        # patch MAX_ENTRIES small
        with mock.patch("orbit.orbit.core.smart_cache.MAX_ENTRIES", 3), \
                mock.patch("orbit.orbit.core.smart_cache.PRUNE_BATCH", 1), \
                mock.patch("time.time", return_value=150.0):
            c._prune()
        self.assertLessEqual(len(c._entries), 3)


class InvalidateTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        c = sc.SmartCache(data_dir=d)
        with mock.patch("time.time", return_value=1000.0):
            c.set("q1", "r1", category="general")
            c.set("q2", "r2", category="facts")
        return c, d

    def test_invalidate_category(self):
        c, d = self._make()
        c.invalidate(category="general")
        self.assertEqual(len(c._entries), 1)
        self.assertEqual(list(c._entries.values())[0].category, "facts")

    def test_invalidate_all(self):
        c, d = self._make()
        c.invalidate()
        self.assertEqual(len(c._entries), 0)

    def test_invalidate_saves(self):
        c, d = self._make()
        with mock.patch.object(c, "_save") as sv:
            c.invalidate()
        sv.assert_called_once()


class GetStatsTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return sc.SmartCache(data_dir=d)

    def test_empty(self):
        c = self._make()
        s = c.get_stats()
        self.assertEqual(s["entries"], 0)
        self.assertEqual(s["max_entries"], sc.MAX_ENTRIES)
        self.assertEqual(s["total_queries"], 0)
        self.assertEqual(s["hits"], 0)
        self.assertEqual(s["misses"], 0)
        self.assertEqual(s["hit_rate"], 0.0)
        self.assertEqual(s["exact_hits"], 0)
        self.assertEqual(s["semantic_hits"], 0)
        self.assertEqual(s["tokens_saved"], 0)
        self.assertEqual(s["expired_pruned"], 0)
        self.assertEqual(s["categories"], {})

    def test_with_data(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q", "r", category="general")
            c.get("q", category="general")  # exact hit
        s = c.get_stats()
        self.assertEqual(s["entries"], 1)
        self.assertEqual(s["hits"], 1)
        self.assertEqual(s["exact_hits"], 1)
        self.assertEqual(s["total_queries"], 1)
        self.assertEqual(s["hit_rate"], 100.0)


class GetEntriesTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return sc.SmartCache(data_dir=d)

    def test_empty(self):
        c = self._make()
        self.assertEqual(c.get_entries(), [])

    def test_sorted_by_hits_desc(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            c.set("q1", "r1", category="general")
            c.set("q2", "r2", category="general")
            # hit q1 twice
            c.get("q1", category="general")
            c.get("q1", category="general")
            entries = c.get_entries(limit=10)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["query"], "q1")
        self.assertEqual(entries[0]["hits"], 2)
        self.assertIn("category", entries[0])
        self.assertIn("age_seconds", entries[0])
        self.assertIn("ttl", entries[0])
        self.assertIn("expired", entries[0])

    def test_limit(self):
        c = self._make()
        with mock.patch("time.time", return_value=1000.0):
            for i in range(5):
                c.set(f"q{i}", f"r{i}", category="general")
            entries = c.get_entries(limit=2)
        self.assertEqual(len(entries), 2)

    def test_query_truncated_100(self):
        c = self._make()
        long_q = "x" * 200
        with mock.patch("time.time", return_value=1000.0):
            c.set(long_q, "r", category="general")
            entries = c.get_entries()
        self.assertEqual(len(entries[0]["query"]), 100)


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = sc._smart_cache
        sc._smart_cache = None
        self.addCleanup(setattr, sc, "_smart_cache", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                        return_value=d):
            a = sc.get_smart_cache()
        self.assertIsInstance(a, sc.SmartCache)
        self.assertIs(sc._smart_cache, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.runtime_paths.orbit_data_dir",
                        return_value=d):
            a = sc.get_smart_cache()
            b = sc.get_smart_cache()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
