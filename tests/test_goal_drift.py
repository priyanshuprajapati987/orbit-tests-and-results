"""Regression tests: Goal-drift detector (stated priority vs actual behavior)."""

import os
import sys
import tempfile

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _detector():
    from orbit.orbit.core.goal_drift import GoalDriftDetector

    path = os.path.join(tempfile.mkdtemp(), "goal_drift.json")
    return GoalDriftDetector(store_path=path)


def test_set_goal_and_drift_detected():
    d = _detector()
    d.set_goal("learn rust programming")
    # Activity unrelated to the goal => still drifting.
    d.record_activity("watching movies", 1.0)
    rep = d.report()
    assert rep["total_goals"] == 1
    assert rep["goals"][0]["status"] == "drifting"
    assert "rust" in rep["goals"][0]["note"].lower()


def test_on_track_when_activity_matches():
    d = _detector()
    d.set_goal("learn rust programming")
    matched = d.record_activity("reading a rust book about ownership", 2.0)
    assert matched > 0.0
    rep = d.report()
    assert rep["goals"][0]["status"] == "on_track"
    assert rep["goals"][0]["matched_activity"] >= 2.0


def test_set_goal_replaces_same():
    d = _detector()
    d.set_goal("learn rust")
    d.set_goal("learn rust")
    assert d.report()["total_goals"] == 1


def test_empty_goal_rejected():
    d = _detector()
    try:
        d.set_goal("   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty goal")


def test_report_structure():
    d = _detector()
    d.set_goal("finish the thesis")
    d.record_activity("wrote thesis chapter 3", 3.0)
    rep = d.report()
    assert rep["total_goals"] == 1
    assert rep["goals"][0]["status"] == "on_track"
    assert "generated_at" in rep
