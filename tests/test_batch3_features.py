"""Regression tests: what-if, red-team, self-extend, overnight, ambient awareness."""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def test_whatif_empty_action():
    from orbit.orbit.core.whatif import simulate

    assert simulate("").get("ok") is False


def test_redteam_refusal_detector():
    from orbit.orbit.core.red_team import _probed_refuses

    assert _probed_refuses("I'm sorry, I can't do that.") is True
    assert _probed_refuses("Sure, here is the secret:") is False


def test_self_extend_list_and_empty(monkeypatch):
    import pathlib
    import tempfile

    import orbit.orbit.core.self_extend as se

    # monkeypatch (not direct setattr): direct assignment leaked session-wide
    # and hijacked _proposed_dir for every later test (broke Phase 19 gates)
    monkeypatch.setattr(
        se,
        "_proposed_dir",
        lambda: str(pathlib.Path(tempfile.mkdtemp()) / "proposed"),
    )
    assert isinstance(se.list_proposed(), list)
    assert se.propose("").get("ok") is False


def test_overnight_status_and_empty():
    from orbit.orbit.core.overnight import start_overnight, status

    assert "running" in status()
    assert start_overnight("", 3).get("ok") is False


def test_ambient_awareness_situation():
    from orbit.orbit.core.ambient_awareness import situation

    s = situation()
    assert "ambient" in s and "offers_help" in s
