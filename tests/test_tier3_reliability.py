"""
Tier 3 — Reliability & Uptime stress tests.

Covers core/reliability.py (circuit/quota/rate-limit queue),
core/fallback_chain.py (death detection + fast switch), core/monitoring.py
(uptime/crash recovery/auto-restart) and the health API.
"""

import asyncio
import time
import unittest


class TestQuotaTracker(unittest.TestCase):
    def test_register_and_record(self):
        from orbit.orbit.core.reliability import QuotaTracker

        q = QuotaTracker()
        q.register("openrouter", limit=100)
        q.record_use("openrouter", 30)
        rec = q.get_record("openrouter")
        self.assertEqual(rec["used"], 30)
        self.assertEqual(rec["remaining"], 70)

    def test_check_under_limit(self):
        from orbit.orbit.core.reliability import QuotaTracker

        q = QuotaTracker()
        q.register("groq", limit=10)
        q.record_use("groq", 5)
        self.assertTrue(q.check("groq"))

    def test_check_at_limit(self):
        from orbit.orbit.core.reliability import QuotaTracker

        q = QuotaTracker()
        q.register("groq", limit=10)
        q.record_use("groq", 10)
        self.assertFalse(q.check("groq"))

    def test_unlimited_provider(self):
        from orbit.orbit.core.reliability import QuotaTracker

        q = QuotaTracker()
        q.register("ollama")  # limit 0 = unlimited
        self.assertTrue(q.check("ollama"))
        self.assertEqual(q.get_record("ollama")["remaining"], -1)

    def test_unknown_provider_allowed(self):
        from orbit.orbit.core.reliability import QuotaTracker

        self.assertTrue(QuotaTracker().check("nope"))

    def test_get_all(self):
        from orbit.orbit.core.reliability import QuotaTracker

        q = QuotaTracker()
        q.register("a", limit=5)
        q.register("b", limit=5)
        self.assertEqual(len(q.get_all()), 2)


class TestRateLimitQueue(unittest.TestCase):
    def test_enqueue_pop(self):
        from orbit.orbit.core.reliability import RateLimitQueue

        q = RateLimitQueue(rate=0)  # no throttle
        q.enqueue("a")
        q.enqueue("b")
        self.assertEqual(q.length(), 2)
        self.assertEqual(q.pop(), "a")
        self.assertEqual(q.length(), 1)

    def test_submit_returns_result(self):
        from orbit.orbit.core.reliability import RateLimitQueue

        q = RateLimitQueue(rate=0)
        out = q.submit(lambda: 42)
        self.assertEqual(out, 42)

    def test_submit_no_throttle_instant(self):
        from orbit.orbit.core.reliability import RateLimitQueue

        q = RateLimitQueue(rate=0)
        t0 = time.monotonic()
        q.submit(lambda: None)
        self.assertLess(time.monotonic() - t0, 0.2)

    def test_submit_throttled(self):
        from orbit.orbit.core.reliability import RateLimitQueue

        q = RateLimitQueue(rate=50.0, burst=1.0)
        q.submit(lambda: None)
        t0 = time.monotonic()
        q.submit(lambda: None)  # must wait for a token refill
        self.assertGreaterEqual(time.monotonic() - t0, 0.01)

    def test_stats(self):
        from orbit.orbit.core.reliability import RateLimitQueue

        q = RateLimitQueue(rate=10.0, burst=5.0, name="test")
        q.submit(lambda: None)
        s = q.get_stats()
        self.assertEqual(s["name"], "test")
        self.assertEqual(s["submitted"], 1)
        self.assertEqual(s["completed"], 1)
        self.assertGreaterEqual(s["burst"], 5.0)

    def test_pop_empty(self):
        from orbit.orbit.core.reliability import RateLimitQueue

        self.assertIsNone(RateLimitQueue(rate=0).pop())


class TestProviderReliabilityRegistry(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.core.reliability import ProviderReliabilityRegistry

        self.rl = ProviderReliabilityRegistry()

    def test_default_providers(self):
        self.assertEqual(len(self.rl.get_all_status()), 6)

    def test_record_success(self):
        self.rl.record_success("groq", latency_ms=120.0)
        s = self.rl.get_status("groq")
        self.assertEqual(s["successes"], 1)
        self.assertEqual(s["p50_latency_ms"], 120.0)
        self.assertFalse(s["dead"])

    def test_record_failure_marks_dead(self):
        self.rl.record_failure("gemini", "429 rate limit")
        self.assertTrue(self.rl.is_dead("gemini"))
        s = self.rl.get_status("gemini")
        self.assertEqual(s["failures"], 1)
        self.assertIn("429", s["last_error"])

    def test_mark_alive(self):
        self.rl.record_failure("ollama", "down")
        self.rl.mark_alive("ollama")
        self.assertFalse(self.rl.is_dead("ollama"))

    def test_register_with_quota(self):
        self.rl.register("openrouter", quota_limit=50)
        self.assertEqual(self.rl.get_status("openrouter")["quota"]["limit"], 50)

    def test_circuit_state_reported(self):
        s = self.rl.get_status("openrouter")
        self.assertIn(s["circuit"], ("closed", "open", "half_open"))

    def test_summary_availability(self):
        self.rl.record_success("groq")
        self.rl.record_failure("groq", "x")
        summary = self.rl.get_summary()
        self.assertEqual(summary["total_calls"], 2)
        self.assertEqual(summary["total_failures"], 1)
        self.assertEqual(summary["availability_pct"], 50.0)

    def test_unknown_provider_status(self):
        s = self.rl.get_status("custom")
        self.assertEqual(s["provider"], "custom")


class TestProviderDeathDetector(unittest.TestCase):
    def test_register_and_probe_alive(self):
        from orbit.orbit.core.fallback_chain import ProviderDeathDetector

        d = ProviderDeathDetector()
        d.register("groq", lambda: True)
        self.assertTrue(d.run_check("groq"))
        self.assertTrue(d.is_alive("groq"))

    def test_probe_dead(self):
        from orbit.orbit.core.fallback_chain import ProviderDeathDetector

        d = ProviderDeathDetector()
        d.register("gemini", lambda: False)
        self.assertFalse(d.run_check("gemini"))
        self.assertFalse(d.is_alive("gemini"))

    def test_probe_raising_is_dead(self):
        from orbit.orbit.core.fallback_chain import ProviderDeathDetector

        d = ProviderDeathDetector()

        def _boom():
            raise RuntimeError("down")

        d.register("ollama", _boom)
        self.assertFalse(d.run_check("ollama"))
        self.assertIn("down", d.get_status()[0]["last_error"])

    def test_unregistered_alive(self):
        from orbit.orbit.core.fallback_chain import ProviderDeathDetector

        d = ProviderDeathDetector()
        self.assertTrue(d.is_alive("nope"))
        self.assertFalse(d.is_registered("nope"))

    def test_run_all(self):
        from orbit.orbit.core.fallback_chain import ProviderDeathDetector

        d = ProviderDeathDetector()
        d.register("a", lambda: True)
        d.register("b", lambda: False)
        out = d.run_all()
        self.assertTrue(out["a"])
        self.assertFalse(out["b"])


class TestFallbackChain(unittest.TestCase):
    def test_first_success_wins(self):
        from orbit.orbit.core.fallback_chain import FallbackChain

        chain = FallbackChain(stagger_ms=10.0)

        async def _slow():
            await asyncio.sleep(0.3)
            return "slow"

        async def _fast():
            await asyncio.sleep(0.02)
            return "fast"

        result = asyncio.run(chain.race([("a", _slow), ("b", _fast)]))
        self.assertEqual(result["winner"], "b")
        self.assertEqual(result["results"]["b"]["result"], "fast")
        self.assertLess(result["switch_ms"], 200)

    def test_fast_switch_below_target(self):
        from orbit.orbit.core.fallback_chain import STAGGER_MS, FallbackChain

        chain = FallbackChain(stagger_ms=100.0)
        result = asyncio.run(chain.race([("a", lambda: "ok")]))
        self.assertLessEqual(result["switch_ms"], STAGGER_MS + 50)

    def test_all_fail(self):
        from orbit.orbit.core.fallback_chain import FallbackChain

        chain = FallbackChain(stagger_ms=10.0)

        def _fail():
            raise ValueError("nope")

        result = asyncio.run(chain.race([("a", _fail), ("b", _fail)]))
        self.assertIsNone(result["winner"])
        self.assertFalse(result["results"]["a"]["success"])

    def test_empty_chain(self):
        from orbit.orbit.core.fallback_chain import FallbackChain

        result = asyncio.run(FallbackChain().race([]))
        self.assertIsNone(result["winner"])
        self.assertEqual(result["attempts"], 0)

    def test_run_chain_sync(self):
        from orbit.orbit.core.fallback_chain import FallbackChain

        result = FallbackChain().run_chain([("a", lambda: "sync-ok")])
        self.assertEqual(result["winner"], "a")

    def test_metrics_after_runs(self):
        from orbit.orbit.core.fallback_chain import FallbackChain

        chain = FallbackChain(stagger_ms=10.0)
        asyncio.run(chain.race([("a", lambda: (time.sleep(0.02), 1)[1])]))
        asyncio.run(
            chain.race([("a", lambda: (time.sleep(0.02), 2)[1]), ("b", lambda: 3)])
        )
        m = chain.get_metrics()
        self.assertEqual(m["runs"], 2)
        self.assertGreater(m["p50_switch_ms"], 0)
        self.assertIn("a", m["wins_by_provider"])

    def test_singleton(self):
        from orbit.orbit.core.fallback_chain import (
            get_death_detector,
            get_fallback_chain,
        )

        self.assertIsNotNone(get_fallback_chain())
        self.assertIsNotNone(get_death_detector())


class TestUptimeTracker(unittest.TestCase):
    def test_heartbeat_marks_ok(self):
        from orbit.orbit.core.monitoring import UptimeTracker

        u = UptimeTracker()
        u.register_component("server")
        u.record_heartbeat("server")
        self.assertTrue(u.is_up("server"))
        self.assertEqual(u.get_component("server")["status"], "ok")

    def test_failure_marks_error(self):
        from orbit.orbit.core.monitoring import UptimeTracker

        u = UptimeTracker()
        u.register_component("ollama")
        u.record_failure("ollama", "refused")
        self.assertFalse(u.is_up("ollama"))
        self.assertEqual(u.get_component("ollama")["status"], "error")

    def test_uptime_pct(self):
        from orbit.orbit.core.monitoring import UptimeTracker

        u = UptimeTracker()
        u.register_component("a")
        u.register_component("b")
        u.record_heartbeat("a")
        u.record_failure("b", "down")
        self.assertEqual(u.get_uptime_pct(), 50.0)

    def test_incidents_logged(self):
        from orbit.orbit.core.monitoring import UptimeTracker

        u = UptimeTracker()
        u.record_failure("x", "boom")
        incidents = u.get_incidents()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["message"], "boom")


class TestRecoveryAndRestart(unittest.TestCase):
    def test_crash_recovery_handler(self):
        from orbit.orbit.core.monitoring import CrashRecovery

        c = CrashRecovery()
        called = {"n": 0}
        c.register_recovery("ollama", lambda: called.__setitem__("n", called["n"] + 1))
        self.assertTrue(c.has_handler("ollama"))
        self.assertTrue(c.recover("ollama"))
        self.assertEqual(called["n"], 1)

    def test_no_handler(self):
        from orbit.orbit.core.monitoring import CrashRecovery

        self.assertFalse(CrashRecovery().recover("nope"))

    def test_handler_raises(self):
        from orbit.orbit.core.monitoring import CrashRecovery

        c = CrashRecovery()
        c.register_recovery("x", lambda: (_ for _ in ()).throw(RuntimeError("bad")))
        self.assertFalse(c.recover("x"))

    def test_auto_restarter_limits(self):
        from orbit.orbit.core.monitoring import AutoRestarter

        r = AutoRestarter(max_attempts=3)
        for _ in range(3):
            self.assertTrue(r.should_restart("s"))
            r.restart("s")
        self.assertFalse(r.should_restart("s"))
        self.assertEqual(r.get_attempts("s"), 3)

    def test_reset_attempts(self):
        from orbit.orbit.core.monitoring import AutoRestarter

        r = AutoRestarter()
        r.restart("s")
        r.reset_attempts("s")
        self.assertEqual(r.get_attempts("s"), 0)

    def test_monitoring_fail_autorestart(self):
        from orbit.orbit.core.monitoring import MonitoringService

        mon = MonitoringService()
        mon.register_component("ollama")
        flag = {"recovered": False}

        def _recover():
            flag["recovered"] = True

        mon.register_recovery("ollama", _recover)
        recovered = mon.fail("ollama", "crash", auto_restart=True)
        self.assertTrue(recovered)
        self.assertTrue(flag["recovered"])
        self.assertEqual(mon.restarter.get_attempts("ollama"), 1)

    def test_dashboard_structure(self):
        from orbit.orbit.core.monitoring import MonitoringService

        mon = MonitoringService()
        mon.register_component("server")
        mon.heartbeat("server")
        d = mon.get_dashboard()
        self.assertIn("uptime_pct", d)
        self.assertIn("components", d)
        self.assertIn("incidents", d)
        self.assertIn("restarts", d)
        self.assertIn("reliability", d)
        self.assertEqual(d["status"], "healthy")

    def test_get_monitoring_singleton(self):
        from orbit.orbit.core.monitoring import get_health_dashboard, get_monitoring

        self.assertIsNotNone(get_monitoring())
        self.assertIn("uptime_pct", get_health_dashboard())


class TestHealthAPI(unittest.TestCase):
    def setUp(self):
        from orbit.orbit.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def test_dashboard_endpoint(self):
        r = self.client.get("/api/health/dashboard")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("uptime_pct", data)
        self.assertIn("components", data)
        self.assertIn("agent_dashboard", data)

    def test_components_endpoint(self):
        r = self.client.get("/api/health/components")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("components", data)

    def test_reliability_endpoint(self):
        r = self.client.get("/api/health/reliability")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("providers", data)
        self.assertIn("summary", data)
        self.assertIn("fallback_chain", data)
        self.assertIn("death_detection", data)


if __name__ == "__main__":
    unittest.main()
