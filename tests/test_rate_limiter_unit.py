"""Tests for RateLimiter — token bucket, per-IP scoped, burst handling."""

import os
import threading
import time
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

from orbit.orbit.core.rate_limiter import RateLimiterRegistry, TokenBucket


class TestTokenBucket(unittest.TestCase):
    def test_allows_within_burst(self):
        bucket = TokenBucket(rate=10, burst=5)
        for _ in range(5):
            self.assertTrue(bucket.consume())

    def test_blocks_over_burst(self):
        bucket = TokenBucket(rate=10, burst=5)
        for _ in range(5):
            bucket.consume()
        self.assertFalse(bucket.consume())

    def test_refill_over_time(self):
        bucket = TokenBucket(rate=100, burst=5)
        for _ in range(5):
            bucket.consume()
        time.sleep(0.1)  # Should refill ~10 tokens
        self.assertTrue(bucket.consume())

    def test_consume_one(self):
        bucket = TokenBucket(rate=10, burst=10)
        result = bucket.consume(1)
        self.assertTrue(result)


class TestRateLimiterRegistry(unittest.TestCase):
    def test_register_and_check(self):
        limiter = RateLimiterRegistry()
        limiter.register("test_endpoint", rate=10, burst=5)
        for _ in range(5):
            self.assertTrue(limiter.check("test_endpoint"))

    def test_unregistered_always_allows(self):
        limiter = RateLimiterRegistry()
        self.assertTrue(limiter.check("nonexistent"))

    def test_exceeds_limit(self):
        limiter = RateLimiterRegistry()
        limiter.register("limited", rate=10, burst=3)
        for _ in range(3):
            limiter.check("limited")
        self.assertFalse(limiter.check("limited"))

    def test_scoped_check_per_ip(self):
        limiter = RateLimiterRegistry()
        limiter.register("chat", rate=10, burst=5)
        for _ in range(5):
            limiter.scoped_check("chat", "192.168.1.1")
        self.assertFalse(limiter.scoped_check("chat", "192.168.1.1"))
        self.assertTrue(limiter.scoped_check("chat", "192.168.1.2"))

    def test_get_status(self):
        limiter = RateLimiterRegistry()
        limiter.register("status_test", rate=10, burst=5)
        status = limiter.get_status()
        self.assertIn("status_test", status)
        self.assertIn("tokens", status["status_test"])
        self.assertIn("burst", status["status_test"])

    def test_thread_safety(self):
        limiter = RateLimiterRegistry()
        limiter.register("thread_test", rate=100, burst=100)
        results = []

        def check():
            results.append(limiter.check("thread_test"))

        threads = [threading.Thread(target=check) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 50)
        self.assertTrue(all(results))


class TestRateLimiterScopedBuckets(unittest.TestCase):
    def test_scoped_buckets_are_separate(self):
        limiter = RateLimiterRegistry()
        limiter.register("test", rate=10, burst=2)
        limiter.scoped_check("test", "10.0.0.1")
        limiter.scoped_check("test", "10.0.0.1")
        self.assertFalse(limiter.scoped_check("test", "10.0.0.1"))
        self.assertTrue(limiter.scoped_check("test", "10.0.0.2"))

    def test_scoped_unregistered_base_allows(self):
        limiter = RateLimiterRegistry()
        self.assertTrue(limiter.scoped_check("unknown_base", "1.2.3.4"))


if __name__ == "__main__":
    unittest.main()
