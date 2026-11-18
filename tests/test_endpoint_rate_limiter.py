"""Unit tests for orbit/orbit/core/endpoint_rate_limiter.py."""

import os
import sys
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.endpoint_rate_limiter import (
    TokenBucket,
    EndpointRateLimiter,
    ENDPOINT_LIMITS,
    get_endpoint_limiter,
    _MAX_BUCKETS,
    _BUCKET_IDLE_SEC,
)
import orbit.core.endpoint_rate_limiter as erl_mod


class TestTokenBucket(unittest.TestCase):
    def test_initial_tokens_full(self):
        b = TokenBucket(rate=1.0, burst=5)
        self.assertEqual(b.tokens, 5.0)

    def test_consume_success(self):
        b = TokenBucket(rate=1.0, burst=2)
        self.assertTrue(b.consume())
        self.assertEqual(b.tokens, 1.0)

    def test_consume_exhausted(self):
        b = TokenBucket(rate=1.0, burst=2)
        self.assertTrue(b.consume())
        self.assertTrue(b.consume())
        self.assertFalse(b.consume())

    def test_refill_over_time(self):
        b = TokenBucket(rate=10.0, burst=2)
        b.consume(2)
        self.assertFalse(b.consume())
        # simulate 0.5s elapsed -> +5 tokens (capped at burst=2)
        b.last_refill = time.monotonic() - 0.5
        self.assertTrue(b.consume())
        self.assertEqual(b.tokens, 1.0)

    def test_refill_capped_at_burst(self):
        b = TokenBucket(rate=100.0, burst=3)
        b.consume(2)  # tokens = 1.0
        # 100s elapsed * 100/s = 10000 tokens would accrue if uncapped
        b.last_refill = time.monotonic() - 100
        b.consume(0)  # trigger refill without consuming
        self.assertEqual(b.tokens, 3.0)  # capped at burst

    def test_consume_more_than_available(self):
        b = TokenBucket(rate=1.0, burst=1)
        self.assertFalse(b.consume(2))

    def test_slots(self):
        b = TokenBucket(rate=1.0, burst=1)
        with self.assertRaises(AttributeError):
            b.nonexistent = 1


class TestEndpointLimitsConfig(unittest.TestCase):
    def test_limits_shape(self):
        self.assertTrue(len(ENDPOINT_LIMITS) > 0)
        for entry in ENDPOINT_LIMITS:
            self.assertEqual(len(entry), 3)
            prefix, rate, burst = entry
            self.assertIsInstance(prefix, str)
            self.assertTrue(prefix.startswith("/"))
            self.assertGreater(rate, 0)
            self.assertGreater(burst, 0)

    def test_no_duplicate_prefixes(self):
        prefixes = [p for p, _, _ in ENDPOINT_LIMITS]
        self.assertEqual(len(prefixes), len(set(prefixes)))


class TestCheckAllowed(unittest.TestCase):
    """check() with _TESTING disabled (real rate-limit path)."""

    def setUp(self):
        self.limiter = EndpointRateLimiter()
        self._testing_patch = patch.object(erl_mod, "_TESTING", False)
        self._testing_patch.start()

    def tearDown(self):
        self._testing_patch.stop()

    def test_unmatched_path_allowed(self):
        for _ in range(50):
            self.assertTrue(self.limiter.check("/api/unknown-path"))
        self.assertEqual(self.limiter.get_stats()["checked"], 50)

    def test_matched_path_allows_burst(self):
        # /api/email/send burst=2
        self.assertTrue(self.limiter.check("/api/email/send"))
        self.assertTrue(self.limiter.check("/api/email/send"))
        self.assertFalse(self.limiter.check("/api/email/send"))

    def test_blocked_increments_stats(self):
        self.limiter.check("/api/email/send")
        self.limiter.check("/api/email/send")
        self.limiter.check("/api/email/send")  # blocked
        stats = self.limiter.get_stats()
        self.assertEqual(stats["checked"], 3)
        self.assertEqual(stats["blocked"], 1)

    def test_blocked_warning_sampled(self):
        # first block (blocked % 50 == 1) logs a warning
        self.limiter.check("/api/email/send")
        self.limiter.check("/api/email/send")
        with self.assertLogs("orbit.core.endpoint_rate_limiter",
                             level="WARNING") as cm:
            self.assertFalse(self.limiter.check("/api/email/send"))
        self.assertIn("rate limit hit", cm.output[0])

    def test_per_ip_buckets_independent(self):
        for _ in range(2):
            self.assertTrue(self.limiter.check("/api/email/send", ip="1.1.1.1"))
        self.assertFalse(self.limiter.check("/api/email/send", ip="1.1.1.1"))
        # other IP unaffected (own bucket)
        self.assertTrue(self.limiter.check("/api/email/send", ip="2.2.2.2"))

    def test_shared_bucket_without_ip(self):
        self.limiter.check("/api/email/send")
        self.limiter.check("/api/email/send")
        self.assertFalse(self.limiter.check("/api/email/send"))

    def test_parameterized_path_shares_prefix_bucket(self):
        # /api/task/<id> all map to /api/task prefix bucket (burst=5)
        for i in range(5):
            self.assertTrue(self.limiter.check(f"/api/task/{i}"))
        self.assertFalse(self.limiter.check("/api/task/99"))

    def test_testing_mode_always_allows(self):
        with patch.object(erl_mod, "_TESTING", True):
            for _ in range(50):
                self.assertTrue(self.limiter.check("/api/email/send"))
        # stats untouched in testing mode
        self.assertEqual(self.limiter.get_stats()["checked"], 0)

    def test_testing_warns_when_no_pytest(self):
        # Simulate production: TESTING=1 but no active pytest run.
        def fake_getenv(key, default=None):
            if key == "PYTEST_CURRENT_TEST":
                return None
            if key == "TESTING":
                return "1"
            return default

        with patch.object(erl_mod, "_TESTING", True), \
             patch.object(erl_mod, "_TESTING_WARNED", False), \
             patch("orbit.core.endpoint_rate_limiter.os.getenv",
                   side_effect=fake_getenv):
            with self.assertLogs("orbit.core.endpoint_rate_limiter",
                                 level="ERROR") as cm:
                self.assertTrue(self.limiter.check("/api/chat"))
        self.assertIn("endpoint rate limits DISABLED", cm.output[0])

    def test_testing_warn_only_once(self):
        def fake_getenv(key, default=None):
            if key == "PYTEST_CURRENT_TEST":
                return None
            if key == "TESTING":
                return "1"
            return default

        with patch.object(erl_mod, "_TESTING", True), \
             patch.object(erl_mod, "_TESTING_WARNED", False), \
             patch("orbit.core.endpoint_rate_limiter.os.getenv",
                   side_effect=fake_getenv):
            with self.assertLogs("orbit.core.endpoint_rate_limiter",
                                 level="ERROR") as cm:
                self.limiter.check("/api/chat")
                self.limiter.check("/api/chat")
        self.assertEqual(len(cm.output), 1)


class TestRetryAfter(unittest.TestCase):
    def setUp(self):
        self.limiter = EndpointRateLimiter()
        self._testing_patch = patch.object(erl_mod, "_TESTING", False)
        self._testing_patch.start()

    def tearDown(self):
        self._testing_patch.stop()

    def test_no_bucket_returns_zero(self):
        self.assertEqual(self.limiter.get_retry_after("/api/unknown"), 0.0)

    def test_full_bucket_returns_zero(self):
        self.assertEqual(self.limiter.get_retry_after("/api/email/send"), 0.0)

    def test_empty_bucket_returns_positive(self):
        self.limiter.check("/api/email/send")
        self.limiter.check("/api/email/send")
        self.limiter.check("/api/email/send")  # blocked -> tokens ~0
        ra = self.limiter.get_retry_after("/api/email/send")
        self.assertGreater(ra, 0.0)
        self.assertLessEqual(ra, 2.0)  # burst 2, rate 0.5/s -> max 2s

    def test_unknown_path_uses_path_as_prefix(self):
        # no matching prefix -> key = path itself -> no bucket -> 0.0
        self.assertEqual(self.limiter.get_retry_after("/no/match"), 0.0)

    def test_retry_after_with_ip(self):
        self.limiter.check("/api/email/send", ip="9.9.9.9")
        self.limiter.check("/api/email/send", ip="9.9.9.9")
        self.limiter.check("/api/email/send", ip="9.9.9.9")
        ra = self.limiter.get_retry_after("/api/email/send", ip="9.9.9.9")
        self.assertGreater(ra, 0.0)


class TestPrune(unittest.TestCase):
    def test_no_prune_under_limit(self):
        lim = EndpointRateLimiter()
        with lim._lock:
            lim._prune_locked()
        # configured prefix buckets all still present
        for prefix, _, _ in ENDPOINT_LIMITS:
            self.assertIn(prefix, lim._buckets)

    def test_prune_evicts_idle_ip_buckets(self):
        lim = EndpointRateLimiter()
        # exceed max with idle per-IP buckets
        with lim._lock:
            for i in range(_MAX_BUCKETS + 10):
                key = f"/api/chat:10.0.0.{i}"
                lim._buckets[key] = TokenBucket(1.0, 1)
                lim._buckets[key].last_used = time.monotonic() - _BUCKET_IDLE_SEC - 1
            before = len(lim._buckets)
            lim._prune_locked()
            after = len(lim._buckets)
        self.assertLess(after, before)
        # protected prefix buckets survive
        for prefix, _, _ in ENDPOINT_LIMITS:
            self.assertIn(prefix, lim._buckets)

    def test_prune_keeps_recent_buckets(self):
        lim = EndpointRateLimiter()
        with lim._lock:
            for i in range(_MAX_BUCKETS + 10):
                key = f"/api/chat:10.0.0.{i}"
                lim._buckets[key] = TokenBucket(1.0, 1)  # last_used = now
            lim._prune_locked()
            # recent buckets NOT evicted (only idle ones are)
            self.assertGreater(len(lim._buckets), _MAX_BUCKETS)


class TestSingleton(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_endpoint_limiter(), get_endpoint_limiter())

    def test_type(self):
        self.assertIsInstance(get_endpoint_limiter(), EndpointRateLimiter)

    def test_singleton_initialized_buckets(self):
        lim = get_endpoint_limiter()
        for prefix, _, _ in ENDPOINT_LIMITS:
            self.assertIn(prefix, lim._buckets)


class TestStats(unittest.TestCase):
    def test_stats_shape(self):
        lim = EndpointRateLimiter()
        stats = lim.get_stats()
        self.assertEqual(set(stats.keys()),
                         {"checked", "blocked", "buckets"})
        self.assertEqual(stats["checked"], 0)
        self.assertEqual(stats["blocked"], 0)
        self.assertEqual(stats["buckets"], len(ENDPOINT_LIMITS))


if __name__ == "__main__":
    unittest.main()
