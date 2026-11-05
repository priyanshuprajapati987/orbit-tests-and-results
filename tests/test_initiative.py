"""Regression tests: Initiative engine — agentic micro-tasks with forgiving undo."""

import os
import sys
import tempfile

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _engine(tmp_path):
    from orbit.orbit.core.initiative_engine import InitiativeEngine

    return InitiativeEngine(
        store_path=str(tmp_path / "initiatives.json"),
        notes_dir=str(tmp_path / "notes"),
    )


def test_run_saves_note_and_undo_deletes():
    d = _engine(_tmp())
    action = d.run("save this as a note titled Ideas: buy milk and eggs")
    assert action is not None
    assert action["kind"] == "note"
    fpath = action["file_path"]
    assert os.path.exists(fpath)
    # Undo reverses it.
    res = d.undo(action["id"])
    assert res["ok"] is True
    assert res["removed"] is True
    assert not os.path.exists(fpath)
    assert d.log()[0]["undone"] is True


def _tmp():
    import pathlib

    return pathlib.Path(tempfile.mkdtemp())


def test_no_safe_intent_returns_none():
    d = _engine(_tmp())
    assert d.run("what is the capital of France?") is None


def test_remember_that_intent():
    d = _engine(_tmp())
    action = d.run("remember that I prefer tea over coffee")
    assert action is not None
    assert action["kind"] == "memory"
    assert os.path.exists(action["file_path"])


def test_undo_unknown_id_fails():
    d = _engine(_tmp())
    res = d.undo("nope")
    assert res["ok"] is False


def test_log_lists_actions_newest_first():
    d = _engine(_tmp())
    a1 = d.run("note: First — one")
    a2 = d.run("note: Second — two")
    log = d.log()
    assert log[0]["id"] == a2["id"]
    assert log[1]["id"] == a1["id"]
