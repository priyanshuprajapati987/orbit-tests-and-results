"""Unit tests for orbit/orbit/core/context_optimizer.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.context_optimizer import (
    ContextStats, ContextOptimizer, get_optimizer, PROVIDER_TOKEN_LIMITS, CHARS_PER_TOKEN,
)


class TestContextStats(unittest.TestCase):
    def test_init(self):
        s = ContextStats(original_tokens=10, optimized_tokens=5)
        self.assertEqual(s.original_tokens, 10)
        self.assertEqual(s.optimized_tokens, 5)


class TestContextOptimizer(unittest.TestCase):
    def setUp(self):
        self.co = ContextOptimizer()

    def test_instantiation(self):
        self.assertIsNotNone(self.co)

    def test_estimate_tokens(self):
        r = self.co._estimate_tokens("hello world")
        self.assertIsInstance(r, int)
        self.assertGreaterEqual(r, 1)

    def test_remove_duplicates(self):
        conv = [{"role": "user", "content": "hi"}, {"role": "user", "content": "hi"}]
        r = self.co._remove_duplicates(conv)
        self.assertEqual(len(r), 1)

    def test_remove_duplicates_empty(self):
        self.assertEqual(self.co._remove_duplicates([]), [])

    def test_compress_old_turns_short(self):
        conv = [{"role": "user", "content": "hi"}] * 3
        r = self.co._compress_old_turns(conv, 8000)
        self.assertEqual(len(r), 3)

    def test_filter_memories(self):
        mems = ["m1", "m2", "m3"]
        r = self.co._filter_memories(mems, 8000, [])
        self.assertIsInstance(r, list)

    def test_optimize(self):
        conv = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        sp, c, m, stats = self.co.optimize("system prompt", conv, memories=["mem1"], provider="groq")
        self.assertEqual(sp, "system prompt")
        self.assertIsInstance(c, list)
        self.assertIsInstance(m, list)
        self.assertIsInstance(stats, ContextStats)

    def test_optimize_dedup(self):
        conv = [{"role": "user", "content": "hi"}, {"role": "user", "content": "hi"}]
        sp, c, m, stats = self.co.optimize("sp", conv)
        self.assertGreaterEqual(stats.duplicates_removed, 1)

    def test_get_stats(self):
        self.co.optimize("sp", [{"role": "user", "content": "hi"}])
        r = self.co.get_stats()
        self.assertIsNotNone(r)

    def test_singleton(self):
        a = get_optimizer()
        b = get_optimizer()
        self.assertIs(a, b)


class TestConstants(unittest.TestCase):
    def test_provider_limits(self):
        self.assertIn("groq", PROVIDER_TOKEN_LIMITS)
        self.assertEqual(CHARS_PER_TOKEN, 4)


if __name__ == "__main__":
    unittest.main()
