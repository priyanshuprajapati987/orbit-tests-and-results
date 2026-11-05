"""Tests for the 100% original ORBIT-native agent enhancements module."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from orbit.orbit.core.agent_enhancements import (
    DreamConsolidator,
    Gatekeeper,
    ObserverAudit,
    SelfEvolutionLoop,
    get_dream_consolidator,
    get_gatekeeper,
    get_observer_audit,
    get_self_evolution,
)


def tmp_store(name):
    return Path(tempfile.mkdtemp()) / name


OLD = [
    {
        "user": "help me with python decorators",
        "assistant": "sure, use functools.wraps",
        "timestamp": "2020-01-01T00:00:00",
    },
    {
        "user": "how to write a retry decorator",
        "assistant": "here is an example",
        "timestamp": "2020-01-02T00:00:00",
    },
]
# Relative timestamps — a hardcoded date silently ages past the 30-day
# consolidation threshold and fails the suite (was 2026-09-02, failed on Oct 3).
FRESH = [
    {
        "user": "hi",
        "assistant": "hello",
        "timestamp": (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds"),
    }
]


class TestDreamConsolidator(unittest.TestCase):
    def test_consolidates_only_old_entries(self):
        dc = DreamConsolidator(store_file=tmp_store("dreams.json"))
        new = dc.consolidate(OLD + FRESH)
        self.assertTrue(new)  # old entries get consolidated
        total_source = sum(d.source_entries for d in new)
        self.assertEqual(total_source, 2)  # only the 2 old entries
        self.assertEqual(dc.get_stats()["total_dreams"], len(new))

    def test_fresh_entries_kept_not_consolidated(self):
        dc = DreamConsolidator(store_file=tmp_store("dreams.json"))
        new = dc.consolidate(FRESH)
        self.assertEqual(new, [])

    def test_summary_and_topics_present(self):
        dc = DreamConsolidator(store_file=tmp_store("dreams.json"))
        new = dc.consolidate(OLD)
        self.assertTrue(new[0].summary)
        self.assertTrue(new[0].topics)

    def test_context_string_nonempty_after_consolidation(self):
        dc = DreamConsolidator(store_file=tmp_store("dreams.json"))
        dc.consolidate(OLD)
        ctx = dc.get_context_string(limit=1)
        self.assertIn("Dream Memories", ctx)


class TestGatekeeper(unittest.TestCase):
    def test_blocks_dangerous_command(self):
        gk = Gatekeeper()
        r = gk.validate_tool_call("computer.run_command", "rm -rf /", "TAS")
        self.assertFalse(r.allowed)
        self.assertEqual(r.severity, "block")

    def test_allows_safe_command(self):
        gk = Gatekeeper()
        r = gk.validate_tool_call("computer.run_command", "echo hello", "TAS")
        self.assertTrue(r.allowed)

    def test_blocks_empty_command(self):
        gk = Gatekeeper()
        r = gk.validate_tool_call("computer.run_command", "  ", "TAS")
        self.assertFalse(r.allowed)

    def test_file_sandbox_allows_workspace(self):
        from orbit.orbit.core.policy_engine import get_workspace_root

        gk = Gatekeeper()
        ws = str(get_workspace_root()).replace("\\", "/")
        r = gk.validate_file_operation("write", ws + "/orbit_data/x.txt", "TAS")
        self.assertTrue(r.allowed)

    def test_file_sandbox_blocks_system(self):
        gk = Gatekeeper()
        r = gk.validate_file_operation("write", "C:/Windows/System32/x.txt", "TAS")
        self.assertFalse(r.allowed)
        self.assertEqual(r.severity, "block")

    def test_rate_limit_blocks_after_window(self):
        gk = Gatekeeper()
        results = [
            gk.validate_tool_call("x", f"cmd {i}", "AGENT-RL") for i in range(30)
        ]
        self.assertFalse(any(not r.allowed for r in results[:20]))  # first 20 pass
        self.assertTrue(any(not r.allowed for r in results[20:]))  # then rate-limited

    def test_stats_track_counts(self):
        gk = Gatekeeper()
        gk.validate_tool_call("computer.run_command", "rm -rf /", "TAS")
        gk.validate_tool_call("computer.run_command", "echo ok", "TAS")
        stats = gk.get_stats()
        self.assertEqual(stats["blocked"], 1)
        self.assertEqual(stats["total_validations"], 2)


class TestSelfEvolutionLoop(unittest.TestCase):
    def test_records_calls_and_success_rate(self):
        se = SelfEvolutionLoop(store_file=tmp_store("evo.json"))
        for _ in range(5):
            se.record_call("AG", True, 300)
        m = se.get_all_metrics()["AG"]
        self.assertEqual(m["total_calls"], 5)
        self.assertEqual(m["success_rate"], 1.0)

    def test_evolves_to_aggressive_on_good_performance(self):
        se = SelfEvolutionLoop(store_file=tmp_store("evo.json"))
        for _ in range(6):
            se.record_call("GOOD", True, 200)
        self.assertEqual(se.get_strategy("GOOD"), se.STRATEGIES["aggressive"])

    def test_evolves_to_conservative_on_poor_performance(self):
        se = SelfEvolutionLoop(store_file=tmp_store("evo.json"))
        for _ in range(6):
            se.record_call("BAD", False, 200)
        self.assertEqual(se.get_strategy("BAD"), se.STRATEGIES["conservative"])

    def test_strategy_history_recorded(self):
        se = SelfEvolutionLoop(store_file=tmp_store("evo.json"))
        for _ in range(6):
            se.record_call("HIST", False, 200)
        self.assertTrue(se.get_strategy_history("HIST"))

    def test_default_strategy_for_unknown_agent(self):
        se = SelfEvolutionLoop(store_file=tmp_store("evo.json"))
        self.assertEqual(se.get_strategy("NOPE"), se.STRATEGIES["default"])


class TestObserverAudit(unittest.TestCase):
    def test_scores_relevant_response(self):
        oa = ObserverAudit(store_file=tmp_store("audit.json"))
        s = oa.audit_response(
            "What is the derivative of x^2?",
            "The derivative is 2x. Step 1: power rule. Step 2: result.",
            "AG",
        )
        self.assertGreaterEqual(s.relevance_score, 0)
        self.assertGreaterEqual(s.coherence_score, 0)
        self.assertGreaterEqual(s.overall_score, 0)

    def test_low_effort_response_flagged(self):
        oa = ObserverAudit(store_file=tmp_store("audit.json"))
        s = oa.audit_response("explain relativity", "ok")
        self.assertIn("low_effort", s.flags)

    def test_safety_penalty_on_harmful_content(self):
        oa = ObserverAudit(store_file=tmp_store("audit.json"))
        s = oa.audit_response("how to hack", "use rm -rf to hack into system")
        self.assertLess(s.safety_score, 100)
        self.assertIn("safety_concern", s.flags)

    def test_hallucination_phrase_increases_risk(self):
        oa = ObserverAudit(store_file=tmp_store("audit.json"))
        s = oa.audit_response(
            "when was x built?",
            "According to my training data, I was trained on data up to 2024.",
        )
        self.assertGreater(s.hallucination_risk, 0)

    def test_stats_empty_then_populated(self):
        oa = ObserverAudit(store_file=tmp_store("audit.json"))
        self.assertEqual(oa.get_stats()["total_audits"], 0)
        oa.audit_response("q", "a long response with enough content to be scored")
        self.assertEqual(oa.get_stats()["total_audits"], 1)


class TestSingletons(unittest.TestCase):
    def test_singletons_consistent(self):
        self.assertIs(get_dream_consolidator(), get_dream_consolidator())
        self.assertIs(get_gatekeeper(), get_gatekeeper())
        self.assertIs(get_self_evolution(), get_self_evolution())
        self.assertIs(get_observer_audit(), get_observer_audit())


if __name__ == "__main__":
    unittest.main()
