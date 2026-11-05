"""Regression tests: Reality-anchor for YOU (leak + contradiction guard)."""

import os
import sys
import tempfile

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _anchor():
    from orbit.orbit.core.reality_anchor import RealityAnchor

    return RealityAnchor(store_path=os.path.join(tempfile.mkdtemp(), "ra.json"))


def test_secret_detected():
    a = _anchor()
    res = a.scan_text("here is my key sk-1234567890abcdef please use it")
    assert res["safe"] is False
    types = [f["type"] for f in res["findings"]]
    assert "secret" in types


def test_no_secret_is_safe():
    a = _anchor()
    res = a.scan_text("let us meet at the park at noon")
    assert res["safe"] is True


def test_stance_contradiction():
    a = _anchor()
    a.record_stance("I think I love coffee in the mornings")
    res = a.scan_text("I never drink coffee anymore, I quit")
    types = [f["type"] for f in res["findings"]]
    assert "stance_contradiction" in types


def test_goal_contradiction():
    from orbit.orbit.core.goal_drift import get_goal_drift

    get_goal_drift().reset()
    get_goal_drift().set_goal("learn rust programming")
    try:
        a = _anchor()
        res = a.scan_text("I'm quitting rust forever, not doing it")
        types = [f["type"] for f in res["findings"]]
        assert "goal_contradiction" in types
    finally:
        get_goal_drift().reset()


def test_record_stance_ignores_ordinary_text():
    a = _anchor()
    assert a.record_stance("what is the weather today?") is None
