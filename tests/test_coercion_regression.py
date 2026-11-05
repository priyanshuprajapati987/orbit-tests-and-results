"""String-coercion bug fixes — regression tests (LOOP-ITER-2).

Covers the systemic class of bugs where JSON/API string values
("50" instead of 50) crashed numeric comparisons with TypeError.
"""
import tempfile

import pytest


def _tracker():
    import orbit.orbit.core.goal_tracker as gt

    gt.DATA_DIR = __import__("pathlib").Path(tempfile.mkdtemp())
    from orbit.orbit.core.goal_tracker import GoalTracker

    return GoalTracker()


class TestCoerceHelpers:
    def test_coerce_float_string(self):
        from orbit.orbit.core.input_sanitizer import coerce_float

        assert coerce_float("50") == 50.0
        assert coerce_float("0.75") == 0.75

    def test_coerce_float_bad(self):
        from orbit.orbit.core.input_sanitizer import coerce_float

        assert coerce_float("abc", 0.0) == 0.0
        assert coerce_float(None, 1.5) == 1.5

    def test_coerce_int_string(self):
        from orbit.orbit.core.input_sanitizer import coerce_int

        assert coerce_int("5") == 5

    def test_coerce_int_negative_floored(self):
        from orbit.orbit.core.input_sanitizer import coerce_int

        assert coerce_int(-3) == 0


class TestGoalTrackerStringProgress:
    def test_stats_string_progress_no_crash(self):
        """REGRESSION: progress as string must not raise TypeError."""
        t = _tracker()
        t._goals = [
            {
                "id": "g1",
                "title": "Learn Rust",
                "progress": "55",  # string from JSON
                "category": "work",
                "deadline": "2027-06-01",
                "sub_goals": [{"title": "s1", "done": False}],
            },
            {
                "id": "g2",
                "title": "Fitness",
                "progress": "10",
                "category": "personal",
                "deadline": "",
                "sub_goals": [],
            },
        ]
        s = t.get_stats()
        assert s["total"] == 2
        assert s["on_track"] == 1  # 55 >= 50
        assert s["at_risk"] == 1  # 10 < 30
        assert isinstance(s["avg_progress"], float)

    def test_suggestions_string_progress_no_crash(self):
        """REGRESSION: suggestions loop with string progress + near deadline."""
        t = _tracker()
        t._goals = [
            {
                "id": "g1",
                "title": "Urgent goal",
                "progress": "15",  # < 20 and within deadline
                "category": "work",
                "deadline": "2026-12-31",
                "sub_goals": [{"title": "next step", "done": False}],
            }
        ]
        sug = t.get_suggestions()
        assert isinstance(sug, list)
        # progress 15 < 20 -> incomplete suggestion
        assert len(sug) >= 1

    def test_numeric_progress_still_works(self):
        t = _tracker()
        t._goals = [
            {"id": "g", "title": "T", "progress": 60, "category": "c", "deadline": "", "sub_goals": []}
        ]
        s = t.get_stats()
        assert s["on_track"] == 1

    def test_avg_progress_string_sum(self):
        """REGRESSION: progress_sum += string must not TypeError."""
        t = _tracker()
        t._goals = [
            {"id": "a", "title": "A", "progress": "40", "category": "c", "deadline": "", "sub_goals": []},
            {"id": "b", "title": "B", "progress": "80", "category": "c", "deadline": "", "sub_goals": []},
        ]
        s = t.get_stats()
        assert s["avg_progress"] == pytest.approx(60.0, abs=0.1)


class TestModuleImports:
    def test_briefing_agent_imports(self):
        from orbit.orbit.agents import briefing_agent

        assert hasattr(briefing_agent, "DailyBriefingAgent")

    def test_chat_api_imports(self):
        from orbit.orbit.core import chat_api

        assert hasattr(chat_api, "_generate_response")

    def test_goal_tracker_imports_coerce(self):
        from orbit.orbit.core import goal_tracker

        assert hasattr(goal_tracker, "coerce_float")


class TestChatApiProgress:
    def test_progress_coercion_helper_available(self):
        from orbit.orbit.core.input_sanitizer import coerce_float

        # mimic the chat_api guard: string progress < 1.0
        assert coerce_float("0.5") < 1.0
        assert not (coerce_float("1.0") < 1.0)
        assert not (coerce_float(1) < 1.0)


# ═══════════════════════════════════════════════════════════════════
#  LOOP-ITER-3 — remaining coercion sites across codebase
# ═══════════════════════════════════════════════════════════════════


class TestModuleImportsIter3:
    def test_cost_optimizer(self):
        from orbit.orbit.core import cost_optimizer

        assert hasattr(cost_optimizer, "coerce_float")

    def test_daily_digest(self):
        from orbit.orbit.core import daily_digest

        assert hasattr(daily_digest, "coerce_float")

    def test_domain_mastery(self):
        from orbit.orbit.core import domain_mastery

        assert hasattr(domain_mastery, "coerce_float")

    def test_resource_tracker(self):
        from orbit.orbit.core import resource_tracker

        assert hasattr(resource_tracker, "coerce_float")

    def test_self_improvement_v2(self):
        from orbit.orbit.core import self_improvement_v2

        assert hasattr(self_improvement_v2, "coerce_int")

    def test_performance_optimizer(self):
        from orbit.orbit.core import performance_optimizer

        assert hasattr(performance_optimizer, "coerce_float")

    def test_habits(self):
        import orbit.orbit.habits as hb

        assert hasattr(hb, "coerce_int")

    def test_proactive(self):
        import orbit.orbit.proactive as pr

        assert hasattr(pr, "coerce_float")


class TestDomainMasteryStringScores:
    def _dm(self):
        from orbit.orbit.core.domain_mastery import DomainMastery

        d = DomainMastery.__new__(DomainMastery)
        return d

    def test_recalc_stats_string_scores(self):
        """REGRESSION: string score/latency must not TypeError."""
        dm = self._dm()
        domain = {
            "practice_tasks": [
                {"score": "85", "latency_ms": "120"},
                {"score": "90", "latency_ms": "80"},
            ],
            "benchmarks": [{"score": "90", "expert_score": "100"}],
            "stats": {},
        }
        dm._recalc_stats(domain)
        assert domain["stats"]["avg_accuracy"] == pytest.approx(87.5, abs=0.1)
        assert domain["stats"]["avg_latency_ms"] == pytest.approx(100.0, abs=0.1)
        assert domain["stats"]["overall_score"] == pytest.approx(0.9, abs=0.001)

    def test_check_phase_ready_string_benchmarks(self):
        """REGRESSION: string expert_score division must not TypeError."""
        dm = self._dm()
        domain = {
            "current_phase": "C",
            "benchmarks": [{"score": "95", "expert_score": "100"}],
        }
        assert dm._check_phase_ready(domain) is True

    def test_numeric_still_works(self):
        dm = self._dm()
        domain = {
            "practice_tasks": [{"score": 80, "latency_ms": 100}],
            "benchmarks": [{"score": 92, "expert_score": 100}],
            "stats": {},
        }
        dm._recalc_stats(domain)
        assert domain["stats"]["avg_accuracy"] == 80.0


class TestCostOptimizerCoercion:
    def test_pricing_string_input(self):
        from orbit.orbit.core.input_sanitizer import coerce_float

        # mimic: pricing.get("input", 0) > 0.005
        assert coerce_float("0.01") > 0.005
        assert not (coerce_float("0.001") > 0.005)

    def test_budget_pct_string(self):
        from orbit.orbit.core.input_sanitizer import coerce_float

        assert coerce_float("90") > 80
        assert not (coerce_float("50") > 80)


class TestHabitsStreak:
    def test_streak_string_no_crash(self):
        import orbit.orbit.habits as hb

        h = {"id": "h1", "name": "Exercise", "log": [], "frequency": "daily", "streak": "5"}
        # mimic the guard used in habits display
        assert hb.coerce_int(h.get("streak", 0)) > 0

    def test_streak_zero(self):
        import orbit.orbit.habits as hb

        assert not (hb.coerce_int({"streak": 0}.get("streak", 0)) > 0)


class TestProactiveRam:
    def test_ram_string_percent(self):
        import orbit.orbit.proactive as pr

        ram = {"percent": "90", "used_gb": 14, "total_gb": 16}
        assert pr.coerce_float(ram.get("percent", 0)) > 85

    def test_ram_ok_percent(self):
        import orbit.orbit.proactive as pr

        ram = {"percent": "50"}
        assert not (pr.coerce_float(ram.get("percent", 0)) > 85)
