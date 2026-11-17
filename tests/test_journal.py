"""Unit tests for orbit/orbit/journal.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.journal as journal_mod
from orbit.journal import add_entry, get_today, get_all, get_by_date, search, delete, stats, format_entries


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jfile = Path(self.tmp) / "journal.json"
        journal_mod.JOURNAL_FILE = self.jfile

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_entry(self):
        e = add_entry("hello world")
        self.assertEqual(e["text"], "hello world")
        self.assertEqual(e["id"], 1)
        self.assertIn("date", e)
        self.assertIn("time", e)
        self.assertIn("created", e)

    def test_add_entry_strips(self):
        e = add_entry("  spaced  ")
        self.assertEqual(e["text"], "spaced")

    def test_add_entry_increments_id(self):
        e1 = add_entry("first")
        e2 = add_entry("second")
        self.assertEqual(e1["id"], 1)
        self.assertEqual(e2["id"], 2)

    def test_get_today(self):
        add_entry("today entry")
        r = get_today()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["text"], "today entry")

    def test_get_all(self):
        add_entry("a")
        add_entry("b")
        self.assertEqual(len(get_all()), 2)

    def test_get_by_date(self):
        add_entry("today")
        today = __import__("datetime").date.today().isoformat()
        r = get_by_date(today)
        self.assertEqual(len(r), 1)
        r2 = get_by_date("1999-01-01")
        self.assertEqual(r2, [])

    def test_search(self):
        add_entry("Python is great")
        add_entry("Java is okay")
        r = search("python")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["text"], "Python is great")
        self.assertEqual(search("nope"), [])

    def test_delete(self):
        e = add_entry("to delete")
        self.assertTrue(delete(e["id"]))
        self.assertEqual(get_all(), [])
        self.assertFalse(delete(e["id"]))  # already deleted
        self.assertFalse(delete(999))

    def test_stats_empty(self):
        self.assertEqual(stats(), {"total": 0, "days": 0, "streak": 0, "avg_words": 0})

    def test_stats(self):
        add_entry("one two three")
        add_entry("four five")
        s = stats()
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["days"], 1)
        self.assertEqual(s["streak"], 1)
        self.assertEqual(s["avg_words"], round(5 / 2))

    def test_format_entries_empty(self):
        r = format_entries([])
        self.assertIn("Koi entries nahi", r)

    def test_format_entries(self):
        add_entry("hello world")
        entries = get_all()
        r = format_entries(entries, "My Journal")
        self.assertIn("My Journal", r)
        self.assertIn("hello world", r)
        self.assertIn("#1", r)

    def test_format_entries_default_title(self):
        r = format_entries([])
        self.assertIn("Journal", r)

    def test_load_corrupt(self):
        self.jfile.write_text("not json", encoding="utf-8")
        self.assertEqual(get_all(), [])

    def test_load_missing(self):
        self.assertEqual(get_all(), [])


if __name__ == "__main__":
    unittest.main()
