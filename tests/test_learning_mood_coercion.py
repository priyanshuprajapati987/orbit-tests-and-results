"""Learning system + mood detector coercion regression (LOOP-ITER-6)."""
import json
import time

import pytest


class TestLearningKnowledgeSummary:
    def _ls(self):
        from orbit.orbit.core.learning_system import get_learning_system

        return get_learning_system()

    def test_string_knowledge_no_crash(self):
        """REGRESSION: string total/successes must not TypeError on > or /."""
        ls = self._ls()
        ls._agent_knowledge["COERCE_TEST_A"] = {"total": "10", "successes": "5", "failures": "5"}
        try:
            summary = ls.get_knowledge_summary("COERCE_TEST_A")
            assert summary["success_rate"] == pytest.approx(0.5, abs=0.01)
            assert summary["total_experiences"] == pytest.approx(10.0, abs=0.01)
        finally:
            ls._agent_knowledge.pop("COERCE_TEST_A", None)

    def test_string_knowledge_full_summary(self):
        """REGRESSION: full summary comprehension with string values."""
        ls = self._ls()
        ls._agent_knowledge["COERCE_TEST_B"] = {"total": "4", "successes": "3", "failures": "1"}
        try:
            full = ls.get_knowledge_summary()
            rate = full["agents"]["COERCE_TEST_B"]["success_rate"]
            assert rate == pytest.approx(0.75, abs=0.01)
        finally:
            ls._agent_knowledge.pop("COERCE_TEST_B", None)

    def test_numeric_still_works(self):
        ls = self._ls()
        ls._agent_knowledge["COERCE_TEST_C"] = {"total": 20, "successes": 15, "failures": 5}
        try:
            summary = ls.get_knowledge_summary("COERCE_TEST_C")
            assert summary["success_rate"] == pytest.approx(0.75, abs=0.01)
        finally:
            ls._agent_knowledge.pop("COERCE_TEST_C", None)

    def test_zero_total_no_division_error(self):
        ls = self._ls()
        ls._agent_knowledge["COERCE_TEST_D"] = {"total": 0, "successes": 0, "failures": 0}
        try:
            summary = ls.get_knowledge_summary("COERCE_TEST_D")
            assert summary["success_rate"] == 0
        finally:
            ls._agent_knowledge.pop("COERCE_TEST_D", None)


class TestMoodDetectorRestore:
    def test_string_timestamp_restore_no_crash(self):
        """REGRESSION: string last_update must not TypeError on float - str."""
        from orbit.orbit.core import mood_detector as md

        md.DATA_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "last_update": str(time.time()),  # string timestamp
            "mood": "focused",  # valid MoodLevel
            "energy": "high",
            "confidence": 0.8,
        }
        (md.DATA_DIR / "mood_state.json").write_text(json.dumps(state), encoding="utf-8")
        inst = md.MoodDetector()
        inst._load_state()  # must not raise
        # recent timestamp -> mood restored to focused
        assert inst._current_mood == md.MoodLevel.FOCUSED

    def test_stale_timestamp_not_restored(self):
        from orbit.orbit.core import mood_detector as md

        md.DATA_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "last_update": str(time.time() - 86400),  # 1 day old
            "mood": "stressed",
            "energy": "low",
            "confidence": 0.4,
        }
        (md.DATA_DIR / "mood_state.json").write_text(json.dumps(state), encoding="utf-8")
        inst = md.MoodDetector()
        inst._load_state()
        # stale -> not restored (stays default neutral)
        assert inst._current_mood == md.MoodLevel.NEUTRAL

    def test_invalid_mood_value_fallback(self):
        from orbit.orbit.core import mood_detector as md

        md.DATA_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "last_update": str(time.time()),
            "mood": "bogus_mood",
            "energy": "medium",
            "confidence": 0.5,
        }
        (md.DATA_DIR / "mood_state.json").write_text(json.dumps(state), encoding="utf-8")
        inst = md.MoodDetector()
        inst._load_state()  # invalid enum value caught, no crash
        assert inst._current_mood == md.MoodLevel.NEUTRAL

    def test_mood_enum_values(self):
        from orbit.orbit.core.mood_detector import EnergyLevel, MoodLevel

        assert MoodLevel.NEUTRAL.value == "neutral"
        assert EnergyLevel.HIGH.value == "high"
