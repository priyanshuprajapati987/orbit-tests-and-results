"""Phase 7 regression — division-by-zero guards.

Covers the division-by-zero bug class found by AST scan of orbit/orbit:
1264 division sites, 170 variable-denominator sites. Most were verified
already guarded (benchmark n>0, battle_prep max_score=100, screen_recorder
fps clamped 1..30, assistant max_count>=5, reasoning total early-return).

DecayEngine(0) was the one genuinely unguarded constructor — a zero or
negative half_life_hours raised ZeroDivisionError. These tests pin the
defensive behavior so it never regresses.
"""
import math

import pytest

from orbit.orbit.core.memory_store import DecayEngine, MemoryEntry


class TestDecayEngineZeroDivision:
    """DecayEngine(half_life_hours<=0) must never raise ZeroDivisionError."""

    def test_zero_half_life_no_crash(self):
        # Before fix: math.log(2) / 0 -> ZeroDivisionError
        eng = DecayEngine(half_life_hours=0)
        assert eng.decay_rate > 0

    def test_negative_half_life_no_crash(self):
        eng = DecayEngine(half_life_hours=-10)
        assert eng.decay_rate > 0

    def test_non_numeric_half_life_no_crash(self):
        # String input (JSON string-coercion sibling class) must not crash
        eng = DecayEngine(half_life_hours="not-a-number")
        assert eng.decay_rate > 0

    def test_none_half_life_no_crash(self):
        eng = DecayEngine(half_life_hours=None)
        assert eng.decay_rate > 0

    def test_degenerate_falls_back_to_default_168(self):
        # Degenerate input falls back to the documented default (168h = 1 week)
        expected = math.log(2) / 168.0
        assert DecayEngine(half_life_hours=0).decay_rate == pytest.approx(expected)
        assert DecayEngine(half_life_hours=-1).decay_rate == pytest.approx(expected)
        assert DecayEngine(half_life_hours=None).decay_rate == pytest.approx(expected)

    def test_valid_half_life_unchanged(self):
        # Normal path must keep the exact original math (no behavior change)
        eng = DecayEngine(half_life_hours=24)
        assert eng.decay_rate == pytest.approx(math.log(2) / 24)
        eng2 = DecayEngine()  # default
        assert eng2.decay_rate == pytest.approx(math.log(2) / 168.0)

    def test_apply_decay_survives_zero_engine(self):
        # End-to-end: a zero-config engine still applies decay without raising
        eng = DecayEngine(half_life_hours=0)
        entry = MemoryEntry(key="greeting", value="hello")
        out = eng.apply_decay(entry)
        assert out is not None
        assert 0.0 <= out.strength <= 1.0


class TestVerifiedGuardedDivisions:
    """Empirically re-verify the division sites the AST scan flagged
    as 'unguarded candidates' but manual review showed were actually
    guarded by constants or clamps."""

    def test_battle_prep_max_score_is_constant(self):
        # judge_score() sets max_score = 100 (a literal), so score/100 never divides by zero
        from orbit.orbit.core.battle_prep import judge_score

        result = judge_score(
            {
                "pass_rate": 100,
                "avg_response_time": 1.0,
                "results": [{"response_len": 100}],
                "total_tasks": 1,
                "passed": 1,
            }
        )
        assert result["max_score"] == 100
        assert isinstance(result["percentage"], (int, float))

    def test_screen_recorder_fps_clamped(self):
        # start() clamps fps to 1..30 before spawning _record_loop -> 1.0/fps safe
        from orbit.orbit.core.screen_recorder import ScreenRecorder

        rec = ScreenRecorder()
        # fps=0 must be rejected or clamped, never reach 1.0/0
        out = rec.start(fps=0)
        if isinstance(out, dict) and "error" in out:
            assert "fps" in out["error"]
        else:
            # If it accepted, it must have clamped to >= 1
            assert out.get("fps", 1) >= 1

    def test_benchmark_empty_results_returns_early(self):
        # _aggregate([]) returns {"count": 0} before any / n division
        from orbit.orbit.core.benchmark import BenchmarkRunner

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        assert runner._aggregate([]) == {"count": 0}

    def test_reasoning_engine_empty_traces_returns_early(self):
        # get_stats() early-returns when total == 0, before / total
        from orbit.orbit.core.reasoning_engine import ReasoningEngine

        eng = ReasoningEngine()  # real constructor (initializes _lock)
        eng._traces = []
        stats = eng.get_stats()
        assert stats["total"] == 0
        assert stats["avg_confidence"] == 0
