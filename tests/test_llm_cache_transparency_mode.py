"""Tests for llm_cache, transparency, runtime_mode, and startup_diagnostics."""

import os
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


class TestLLMCache(unittest.TestCase):
    def test_cache_singleton(self):
        from orbit.orbit.core.llm_cache import get_cache

        c1 = get_cache()
        c2 = get_cache()
        self.assertIs(c1, c2)

    def test_cache_set_and_get(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import get_cache

        cache = get_cache()
        req = LLMRequest(prompt="test cache prompt xyz 999", model="test")
        resp = LLMResponse(
            content="hello world", provider="test", model="test", latency_ms=100
        )
        cache.set(req, resp)
        result = cache.get(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.content, "hello world")

    def test_cache_miss(self):
        from orbit.orbit.core.llm.router import LLMRequest
        from orbit.orbit.core.llm_cache import get_cache

        cache = get_cache()
        req = LLMRequest(prompt="nonexistent_unique_key_99999999", model="none")
        result = cache.get(req)
        self.assertIsNone(result)

    def test_cache_stats(self):
        from orbit.orbit.core.llm.router import LLMRequest, LLMResponse
        from orbit.orbit.core.llm_cache import get_cache

        cache = get_cache()
        req = LLMRequest(prompt="stats_unique_test_99999999", model="t")
        resp = LLMResponse(content="data", provider="t", model="t", latency_ms=50)
        cache.set(req, resp)
        cache.get(req)
        cache.get(LLMRequest(prompt="miss_unique_99999999", model="x"))
        stats = cache.get_stats()
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)

    def test_is_cacheable(self):
        from orbit.orbit.core.llm_cache import is_cacheable

        self.assertTrue(is_cacheable("facts"))
        self.assertTrue(is_cacheable("general"))
        self.assertFalse(is_cacheable("code"))
        self.assertFalse(is_cacheable("reasoning"))


class TestTransparency(unittest.TestCase):
    def test_record_and_history(self):
        from orbit.orbit.core.transparency import get_transparency_store

        store = get_transparency_store()
        store.record(
            {
                "provider": "ollama",
                "model": "qwen3",
                "latency_ms": 100,
                "tokens_in": 50,
                "tokens_out": 30,
            }
        )
        history = store.history()
        self.assertGreater(len(history), 0)

    def test_latest(self):
        from orbit.orbit.core.transparency import get_transparency_store

        store = get_transparency_store()
        store.record(
            {"provider": "test_transparency", "model": "test_m", "latency_ms": 50}
        )
        entry = store.latest()
        self.assertIsNotNone(entry)

    def test_singleton(self):
        from orbit.orbit.core.transparency import get_transparency_store

        s1 = get_transparency_store()
        s2 = get_transparency_store()
        self.assertIs(s1, s2)

    def test_reset(self):
        from orbit.orbit.core.transparency import get_transparency_store

        store = get_transparency_store()
        store.reset()
        history = store.history()
        self.assertEqual(len(history), 0)


class TestRuntimeMode(unittest.TestCase):
    def test_get_mode(self):
        from orbit.orbit.core.runtime_mode import get_runtime_mode

        mode = get_runtime_mode()
        self.assertIsNotNone(mode)

    def test_singleton(self):
        from orbit.orbit.core.runtime_mode import get_runtime_mode

        m1 = get_runtime_mode()
        m2 = get_runtime_mode()
        self.assertIs(m1, m2)


class TestVersion(unittest.TestCase):
    def test_version_exists(self):
        from orbit.orbit.core.version import VERSION

        self.assertIsNotNone(VERSION)
        self.assertIsInstance(VERSION, str)

    def test_version_format(self):
        from orbit.orbit.core.version import VERSION

        parts = VERSION.split(".")
        self.assertGreaterEqual(len(parts), 2)


class TestRuntimePaths(unittest.TestCase):
    def test_app_root(self):
        from orbit.orbit.core.runtime_paths import app_root

        root = app_root()
        self.assertIsNotNone(root)
        self.assertTrue(root.exists())

    def test_is_frozen(self):
        from orbit.orbit.core.runtime_paths import is_frozen

        result = is_frozen()
        self.assertIsInstance(result, bool)

    def test_orbit_data_dir(self):
        from orbit.orbit.core.runtime_paths import orbit_data_dir

        data_dir = orbit_data_dir()
        self.assertIsNotNone(data_dir)


class TestStartupDiagnostics(unittest.TestCase):
    def test_run_diagnostics(self):
        from orbit.orbit.core.startup_diagnostics import run_diagnostics

        result = run_diagnostics()
        self.assertIn("status", result)
        self.assertIn("checks", result)

    def test_check_python(self):
        from orbit.orbit.core.startup_diagnostics import check_python

        diag = check_python()
        self.assertTrue(hasattr(diag, "verdict"))
        self.assertTrue(hasattr(diag, "message"))
        self.assertTrue(hasattr(diag, "to_dict"))
        d = diag.to_dict()
        self.assertIn("verdict", d)
        self.assertIn("message", d)


if __name__ == "__main__":
    unittest.main()
