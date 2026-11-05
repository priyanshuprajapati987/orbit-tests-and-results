"""Decision Engine audit — regression tests for string-score risk bug + full coverage."""
import tempfile

import pytest


def _engine(monkeypatch=None):
    import orbit.orbit.core.decision_engine as de

    de.DATA_DIR = __import__("pathlib").Path(tempfile.mkdtemp())
    return de.DecisionEngine()


class TestAnalyze:
    def test_normal_numeric_scores(self):
        eng = _engine()
        # full default-criteria scores so nothing is "missing"
        def full(base):
            return {
                "Impact": base,
                "Feasibility": base,
                "Risk": 100 - base,  # risk is a score, lower raw is safer here
                "Cost": base,
                "Time": base,
            }

        r = eng.analyze(
            "Which stack?",
            [
                {"name": "FastAPI", "scores": full(90)},
                {"name": "Flask", "scores": full(60)},
            ],
            personality="tony_stark",
        )
        assert r["winner"] == "FastAPI"
        assert r["winner_score"] > 0
        assert r["confidence"] > 0

    def test_string_scores_do_not_crash(self):
        """REGRESSION: string scores from JSON/API must not raise TypeError."""
        eng = _engine()
        r = eng.analyze(
            "Q?",
            [
                {"name": "A", "scores": {"Risk": "80"}},
                {"name": "B", "scores": {"Risk": "30"}},
            ],
        )
        assert r["winner"] is not None
        # A has Risk 80 -> HIGH
        risks = {o["name"]: o["risk"] for o in r["options"]}
        assert risks["A"] == "HIGH"
        assert risks["B"] == "LOW"

    def test_missing_scores_graceful(self):
        eng = _engine()
        r = eng.analyze("Q?", [{"name": "A"}, {"name": "B"}])
        assert r["winner"] is not None
        assert r["confidence"] == 0  # missing scores -> 0 confidence

    def test_empty_options(self):
        eng = _engine()
        r = eng.analyze("Q?", [])
        assert r["winner"] is None
        assert "Insufficient data" in r["recommendation"]

    def test_default_criteria_used(self):
        eng = _engine()
        r = eng.analyze("Q?", [{"name": "A", "scores": {}}])
        assert len(r["criteria"]) == 5

    def test_custom_criteria(self):
        eng = _engine()
        r = eng.analyze(
            "Q?",
            [{"name": "A", "scores": {"Quality": 90}}],
            criteria=[{"name": "Quality", "weight": 1.0}],
        )
        assert r["criteria"][0]["name"] == "Quality"
        assert r["winner_score"] == pytest.approx(90.0, abs=0.01)

    def test_weighted_total_calculation(self):
        eng = _engine()
        r = eng.analyze(
            "Q?",
            [{"name": "A", "scores": {"X": 100, "Y": 0}}],
            criteria=[{"name": "X", "weight": 0.7}, {"name": "Y", "weight": 0.3}],
        )
        assert r["options"][0]["weighted_total"] == pytest.approx(70.0, abs=0.01)

    def test_options_sorted_by_score(self):
        eng = _engine()
        r = eng.analyze(
            "Q?",
            [
                {"name": "Low", "scores": {"X": 10}},
                {"name": "High", "scores": {"X": 90}},
            ],
            criteria=[{"name": "X", "weight": 1.0}],
        )
        assert r["options"][0]["name"] == "High"

    def test_personality_fallback_tony(self):
        eng = _engine()
        r = eng.analyze("Q?", [{"name": "A", "scores": {"X": 50}}], personality="unknown")
        assert r["personality"]["name"] == "Tony Stark"

    def test_elapsed_ms_present(self):
        eng = _engine()
        r = eng.analyze("Q?", [{"name": "A", "scores": {"X": 50}}])
        assert "elapsed_ms" in r
        assert r["elapsed_ms"] >= 0

    def test_decision_persisted(self):
        eng = _engine()
        r = eng.analyze("Q?", [{"name": "A", "scores": {"X": 50}}])
        found = eng.get_decision(r["id"])
        assert found is not None
        assert found["id"] == r["id"]


class TestRisk:
    def _eng(self):
        return _engine()

    def test_high_risk(self):
        eng = self._eng()
        assert eng._assess_risk({"scores": {"Risk": 80}}, []) == "HIGH"

    def test_medium_risk(self):
        eng = self._eng()
        assert eng._assess_risk({"scores": {"Risk": 50}}, []) == "MEDIUM"

    def test_low_risk(self):
        eng = self._eng()
        assert eng._assess_risk({"scores": {"Risk": 20}}, []) == "LOW"

    def test_string_risk_coerced(self):
        """REGRESSION: string '80' must coerce to HIGH not crash."""
        eng = self._eng()
        assert eng._assess_risk({"scores": {"Risk": "80"}}, []) == "HIGH"
        assert eng._assess_risk({"scores": {"Risk": "30"}}, []) == "LOW"

    def test_garbage_risk_defaults_medium(self):
        eng = self._eng()
        assert eng._assess_risk({"scores": {"Risk": "not-a-number"}}, []) == "MEDIUM"

    def test_none_risk_defaults_medium(self):
        eng = self._eng()
        assert eng._assess_risk({"scores": {"Risk": None}}, []) == "MEDIUM"

    def test_missing_risk_defaults_medium(self):
        eng = self._eng()
        assert eng._assess_risk({}, []) == "MEDIUM"


class TestRecommendation:
    def test_no_winner(self):
        eng = _engine()
        rec = eng._generate_recommendation("q", None, {"prefix": "P", "name": "N", "approach": "a"})
        assert "Insufficient data" in rec

    def test_with_winner(self):
        eng = _engine()
        winner = {"name": "Opt", "weighted_total": 85.5, "risk": "LOW"}
        pers = {"prefix": "What would Tony Stark do?", "name": "Tony Stark", "approach": "Bold"}
        rec = eng._generate_recommendation("q", winner, pers)
        assert "Opt" in rec
        assert "85.5" in rec
        assert "LOW" in rec


class TestHistoryStats:
    def test_history_order(self):
        eng = _engine()
        eng.analyze("q1", [{"name": "A", "scores": {"X": 50}}])
        eng.analyze("q2", [{"name": "B", "scores": {"X": 60}}])
        h = eng.get_history()
        assert h[0]["question"] == "q2"  # reversed = newest first

    def test_history_limit(self):
        eng = _engine()
        for i in range(5):
            eng.analyze(f"q{i}", [{"name": "A", "scores": {"X": 50}}])
        h = eng.get_history(limit=2)
        assert len(h) == 2

    def test_get_decision_not_found(self):
        eng = _engine()
        assert eng.get_decision("ghost") is None

    def test_stats_empty(self):
        eng = _engine()
        s = eng.get_stats()
        assert s["total"] == 0
        assert s["avg_confidence"] == 0

    def test_stats_populated(self):
        eng = _engine()
        full = {
            "Impact": 80,
            "Feasibility": 80,
            "Risk": 30,
            "Cost": 70,
            "Time": 70,
        }
        eng.analyze("q1", [{"name": "A", "scores": full}], category="technical")
        eng.analyze("q2", [{"name": "B", "scores": full}], category="personal")
        s = eng.get_stats()
        assert s["total"] == 2
        assert s["categories"]["technical"] == 1
        assert s["avg_confidence"] > 0

    def test_singleton(self):
        import orbit.orbit.core.decision_engine as de

        de._instance = None
        e1 = de.get_decision_engine()
        e2 = de.get_decision_engine()
        assert e1 is e2
        de._instance = None


class TestPersonalityFilters:
    def test_all_three_present(self):
        import orbit.orbit.core.decision_engine as de

        assert "tony_stark" in de.PERSONALITY_FILTERS
        assert "pepper_potts" in de.PERSONALITY_FILTERS
        assert "james_howlett" in de.PERSONALITY_FILTERS
        for pf in de.PERSONALITY_FILTERS.values():
            assert "name" in pf
            assert "approach" in pf
            assert "prefix" in pf
            assert "traits" in pf
