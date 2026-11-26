import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


class TestCapabilityHardening(unittest.TestCase):
    def test_expiring_grant_and_escalation(self):
        from orbit.orbit.core.capabilities import CapabilityManager

        with tempfile.TemporaryDirectory() as td:
            manager = CapabilityManager(audit_path=Path(td) / "audit.jsonl")
            manager.grant("TEST", {"agent.dispatch"}, task_id="task-1", ttl_seconds=1)
            self.assertTrue(manager.check("TEST", "agent.dispatch", "task-1"))
            with self.assertRaises(PermissionError):
                manager.grant("TEST", {"agent.dispatch", "shell.execute"}, task_id="task-1", ttl_seconds=1)


class TestMemoryClaimSafety(unittest.TestCase):
    def test_uncertain_claim_quarantined_and_unverified_promotion_rejected(self):
        from orbit.orbit.core.memory_safety import MemoryClaimSafety

        with tempfile.TemporaryDirectory() as td:
            safety = MemoryClaimSafety(Path(td) / "claims.jsonl")
            quarantined = safety.classify("May be true", confidence=0.4, evidence=[])
            self.assertEqual(quarantined["status"], "quarantined")
            rejected = safety.promote("May be true", evidence=[])
            self.assertEqual(rejected["status"], "rejected")


class TestTrustHardening(unittest.TestCase):
    def test_unverified_response_has_indicators(self):
        from orbit.orbit.core.transparency import build_trust_indicators

        result = build_trust_indicators("This is definitely true", evidence_count=0, confidence=0.2)
        self.assertEqual(result["trust"]["verification_level"], "unverified")
        self.assertEqual(result["trust"]["evidence_count"], 0)


class TestRouterBenchmark(unittest.TestCase):
    def test_reproducible_presets_and_no_cost_claim(self):
        from orbit.orbit.core.learned_router import run_static_vs_learned_benchmark

        result = run_static_vs_learned_benchmark(100, ["hello"] * 100)
        self.assertEqual(result["preset"], 100)
        self.assertEqual(result["route_samples"], 100)
        self.assertIsNone(result["measured_cost"])


if __name__ == "__main__":
    unittest.main()
