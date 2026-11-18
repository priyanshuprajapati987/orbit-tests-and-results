"""Unit tests for orbit/orbit/notes.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.notes as notes_mod
from orbit.notes import (
    add, get_all, search, update, delete, toggle_pin,
    get_pinned, get_recent, format_list,
)


class NotesTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._old_file = notes_mod.NOTES_FILE
        notes_mod.NOTES_FILE = self.tmp / "orbit_notes.json"

    def tearDown(self):
        notes_mod.NOTES_FILE = self._old_file

    def seed(self, *notes_data):
        notes_mod.NOTES_FILE.write_text(json.dumps(list(notes_data)), encoding="utf-8")


class TestLoadSave(NotesTestBase):
    def test_load_missing(self):
        self.assertEqual(notes_mod._load(), [])

    def test_load_valid(self):
        self.seed({"id": 1, "title": "a"})
        self.assertEqual(notes_mod._load(), [{"id": 1, "title": "a"}])

    def test_load_corrupt(self):
        notes_mod.NOTES_FILE.write_text("not-json", encoding="utf-8")
        self.assertEqual(notes_mod._load(), [])

    def test_save_creates_file(self):
        notes_mod._save([{"id": 1}])
        data = json.loads(notes_mod.NOTES_FILE.read_text(encoding="utf-8"))
        self.assertEqual(data, [{"id": 1}])

    def test_save_atomic_no_tmp(self):
        notes_mod._save([{"id": 1}])
        self.assertFalse(notes_mod.NOTES_FILE.with_suffix(".json.tmp").exists())


class TestAdd(NotesTestBase):
    def test_add_basic(self):
        n = add("First", "body text", ["tag1"])
        self.assertEqual(n["title"], "First")
        self.assertEqual(n["body"], "body text")
        self.assertEqual(n["tags"], ["tag1"])
        self.assertEqual(n["id"], 1)
        self.assertFalse(n["pinned"])
        self.assertIn("created", n)
        self.assertIn("updated", n)

    def test_add_persists(self):
        add("A")
        self.assertEqual(len(get_all()), 1)

    def test_add_id_increments(self):
        add("A")
        n2 = add("B")
        self.assertEqual(n2["id"], 2)

    def test_add_inserts_at_front(self):
        add("A")
        add("B")
        all_notes = get_all()
        self.assertEqual(all_notes[0]["title"], "B")

    def test_add_default_tags_empty(self):
        n = add("A")
        self.assertEqual(n["tags"], [])

    def test_add_empty_tags(self):
        n = add("A", tags=[])
        self.assertEqual(n["tags"], [])


class TestGetAll(NotesTestBase):
    def test_empty(self):
        self.assertEqual(get_all(), [])

    def test_returns_notes(self):
        add("A")
        self.assertEqual(len(get_all()), 1)


class TestSearch(NotesTestBase):
    def test_search_title(self):
        add("Python tips")
        add("Java notes")
        r = search("python")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["title"], "Python tips")

    def test_search_body(self):
        add("T1", body="hello world")
        add("T2", body="goodbye")
        r = search("WORLD")
        self.assertEqual(len(r), 1)

    def test_search_no_match(self):
        add("A")
        self.assertEqual(search("zzz"), [])

    def test_search_empty(self):
        self.assertEqual(search("anything"), [])

    def test_search_multiple_matches(self):
        add("cat one")
        add("cat two")
        self.assertEqual(len(search("cat")), 2)


class TestUpdate(NotesTestBase):
    def test_update_title(self):
        n = add("Old")
        updated = update(n["id"], title="New")
        self.assertEqual(updated["title"], "New")
        # persisted
        self.assertEqual(get_all()[0]["title"], "New")

    def test_update_none_value_skipped(self):
        n = add("Old", body="keep")
        updated = update(n["id"], title="New", body=None)
        self.assertEqual(updated["title"], "New")
        self.assertEqual(updated["body"], "keep")  # None skipped

    def test_update_touches_updated(self):
        n = add("A")
        updated = update(n["id"], title="B")
        self.assertGreaterEqual(updated["updated"], n["updated"])

    def test_update_not_found(self):
        add("A")
        self.assertIsNone(update(999, title="x"))

    def test_update_multiple_fields(self):
        n = add("A")
        updated = update(n["id"], title="B", body="body", tags=["t"])
        self.assertEqual(updated["title"], "B")
        self.assertEqual(updated["body"], "body")
        self.assertEqual(updated["tags"], ["t"])

    def test_update_false_value_allowed(self):
        n = add("A", body="keep")
        # False is not None -> applies
        updated = update(n["id"], body=False)
        self.assertFalse(updated["body"])


class TestDelete(NotesTestBase):
    def test_delete_existing(self):
        n = add("A")
        self.assertTrue(delete(n["id"]))
        self.assertEqual(get_all(), [])

    def test_delete_missing(self):
        add("A")
        self.assertFalse(delete(999))

    def test_delete_empty(self):
        self.assertFalse(delete(1))


class TestTogglePin(NotesTestBase):
    def test_toggle_pin_on(self):
        n = add("A")
        t = toggle_pin(n["id"])
        self.assertTrue(t["pinned"])

    def test_toggle_pin_off(self):
        n = add("A")
        toggle_pin(n["id"])
        t = toggle_pin(n["id"])
        self.assertFalse(t["pinned"])

    def test_toggle_pin_missing(self):
        self.assertIsNone(toggle_pin(999))


class TestGetPinned(NotesTestBase):
    def test_no_pinned(self):
        add("A")
        self.assertEqual(get_pinned(), [])

    def test_pinned_only(self):
        n1 = add("Pinned")
        add("Unpinned")
        toggle_pin(n1["id"])
        pinned = get_pinned()
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0]["id"], n1["id"])


class TestGetRecent(NotesTestBase):
    def test_recent_default_limit(self):
        for i in range(8):
            add(f"N{i}")
        self.assertEqual(len(get_recent()), 5)

    def test_recent_custom_limit(self):
        for i in range(8):
            add(f"N{i}")
        self.assertEqual(len(get_recent(3)), 3)

    def test_recent_sorted_by_updated_desc(self):
        # explicit timestamps (Windows timer granularity can make live
        # now() calls collide within the same clock tick)
        self.seed(
            {"id": 1, "title": "Old", "updated": "2026-01-01T10:00:00"},
            {"id": 2, "title": "Newer", "updated": "2026-01-02T10:00:00"},
        )
        recent = get_recent(2)
        self.assertEqual(recent[0]["id"], 2)
        self.assertEqual(recent[1]["id"], 1)

    def test_recent_empty(self):
        self.assertEqual(get_recent(), [])


class TestFormatList(NotesTestBase):
    def test_empty(self):
        self.assertIn("Koi notes nahi", format_list([]))

    def test_basic_format(self):
        notes = [{"id": 1, "title": "Hello", "body": "short", "pinned": False}]
        r = format_list(notes)
        self.assertIn("#1", r)
        self.assertIn("**Hello**", r)
        self.assertIn("short", r)

    def test_pinned_marker(self):
        notes = [{"id": 1, "title": "P", "body": "", "pinned": True}]
        self.assertIn("📌", format_list(notes))

    def test_no_body_omits_dash(self):
        notes = [{"id": 1, "title": "NoBody", "body": "", "pinned": False}]
        r = format_list(notes)
        self.assertIn("**NoBody**", r)
        self.assertNotIn("—", r)

    def test_body_truncated_at_60(self):
        body = "x" * 100
        notes = [{"id": 1, "title": "T", "body": body, "pinned": False}]
        r = format_list(notes)
        self.assertIn("x" * 60 + "...", r)
        self.assertNotIn("x" * 61, r)

    def test_body_exactly_60_not_truncated(self):
        body = "x" * 60
        notes = [{"id": 1, "title": "T", "body": body, "pinned": False}]
        r = format_list(notes)
        self.assertIn("x" * 60, r)
        self.assertNotIn("...", r)

    def test_more_than_5_shows_remainder(self):
        notes = [{"id": i, "title": f"N{i}", "body": "", "pinned": False} for i in range(8)]
        r = format_list(notes)
        self.assertIn("...aur 3 aur notes", r)

    def test_exactly_5_no_remainder(self):
        notes = [{"id": i, "title": f"N{i}", "body": "", "pinned": False} for i in range(5)]
        r = format_list(notes)
        self.assertNotIn("aur notes", r)

    def test_missing_title_defaults(self):
        notes = [{"id": 1, "body": "", "pinned": False}]
        self.assertIn("Untitled", format_list(notes))


if __name__ == "__main__":
    unittest.main()
