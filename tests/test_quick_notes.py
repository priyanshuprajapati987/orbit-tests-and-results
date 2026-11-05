# ORBIT — Quick Notes tests (Phase 1)
# Run: python -m pytest tests/test_quick_notes.py -v

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def test_add_and_get():
    from orbit.orbit.core.quick_notes import QuickNotes
    qn = QuickNotes()
    note = qn.add("meeting tomorrow 3pm", tags=["work"])
    assert note.content == "meeting tomorrow 3pm"
    assert "work" in note.tags
    fetched = qn.get(note.id)
    assert fetched is not None
    assert fetched.content == note.content


def test_update_note():
    from orbit.orbit.core.quick_notes import QuickNotes
    qn = QuickNotes()
    note = qn.add("old content")
    updated = qn.update(note.id, content="new content", tags=["x"])
    assert updated.content == "new content"
    assert "x" in updated.tags


def test_delete_note():
    from orbit.orbit.core.quick_notes import QuickNotes
    qn = QuickNotes()
    note = qn.add("to delete")
    assert qn.delete(note.id) is True
    assert qn.get(note.id) is None
    assert qn.delete("nonexistent") is False


def test_search_notes():
    from orbit.orbit.core.quick_notes import QuickNotes
    qn = QuickNotes()
    qn.add("buy milk")
    qn.add("meeting notes", tags=["work"])
    res = qn.search("milk")
    assert len(res) >= 1
    res2 = qn.search("work")
    assert len(res2) >= 1


def test_list_and_stats():
    from orbit.orbit.core.quick_notes import QuickNotes
    qn = QuickNotes()
    qn.add("n1", tags=["a"])
    qn.add("n2", tags=["b"])
    assert len(qn.list_all()) >= 2
    stats = qn.get_stats()
    assert stats["total"] >= 2
    assert "a" in stats["tags"] or "b" in stats["tags"]
