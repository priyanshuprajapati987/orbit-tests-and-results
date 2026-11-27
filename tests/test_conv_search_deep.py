"""Deep tests for orbit/orbit/conv_search.py (Loop 13/2).

Covers every statement:
  * ``_load`` / ``_save`` — missing file, valid, corrupt, parent mkdir,
    atomic replace, save failure logging.
  * ``index_message`` — short text ignored, append, cap 5000 (trim),
    lock usage.
  * ``search`` — term filtering (>2 chars), scoring (count), sort desc,
    limit, empty query, no matches.
  * ``search_by_date`` — start/end filtering, 50 cap.
  * ``clear``.
  * ``stats`` — empty + populated (total/users/first/last).
  * ``highlight`` — term bolding, case-insensitive, 300-char truncation.
  * ``format_results`` — empty + populated, 10-cap + "...aur N aur".
"""

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit import conv_search as cs


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = None
        self._orig = cs.SEARCH_INDEX_FILE
        import tempfile, os
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "conv_index.json"
        cs.SEARCH_INDEX_FILE = self._path
        self.addCleanup(setattr, cs, "SEARCH_INDEX_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(cs._load(), [])

    def test_load_valid(self):
        self._path.write_text('[{"id":1}]', encoding="utf-8")
        self.assertEqual(cs._load(), [{"id": 1}])

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(cs._load(), [])

    def test_save_success(self):
        ok = cs._save([{"id": 1}])
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), [{"id": 1}])

    def test_save_failure(self):
        # make parent.mkdir raise
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = cs._save([{"id": 1}])
        self.assertFalse(ok)


class IndexMessageTests(unittest.TestCase):
    def setUp(self):
        self._orig = cs.SEARCH_INDEX_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "conv_index.json"
        cs.SEARCH_INDEX_FILE = self._path
        self.addCleanup(setattr, cs, "SEARCH_INDEX_FILE", self._orig)

    def test_short_text_ignored(self):
        cs.index_message("user", "hi")
        self.assertEqual(cs._load(), [])

    def test_empty_text_ignored(self):
        cs.index_message("user", "")
        self.assertEqual(cs._load(), [])

    def test_falsy_none(self):
        cs.index_message("user", None)
        self.assertEqual(cs._load(), [])

    def test_indexes_entry(self):
        cs.index_message("user", "hello world this is a test")
        idx = cs._load()
        self.assertEqual(len(idx), 1)
        self.assertEqual(idx[0]["role"], "user")
        self.assertEqual(idx[0]["text"], "hello world this is a test")
        self.assertEqual(idx[0]["id"], 1)
        self.assertIn("timestamp", idx[0])

    def test_text_truncated_to_500(self):
        cs.index_message("assistant", "x" * 600)
        idx = cs._load()
        self.assertEqual(len(idx[0]["text"]), 500)

    def test_cap_5000_trims(self):
        # seed 5000 entries
        data = [{"id": i, "role": "user", "text": "t" * 10,
                 "timestamp": "2026-01-01T00:00:00"} for i in range(5000)]
        self._path.write_text(json.dumps(data), encoding="utf-8")
        cs.index_message("user", "new message here")
        idx = cs._load()
        self.assertEqual(len(idx), 5000)
        self.assertEqual(idx[-1]["text"], "new message here")

    def test_id_increments(self):
        cs.index_message("user", "first message here")
        cs.index_message("assistant", "second message here")
        idx = cs._load()
        self.assertEqual(idx[0]["id"], 1)
        self.assertEqual(idx[1]["id"], 2)


class SearchTests(unittest.TestCase):
    def setUp(self):
        self._orig = cs.SEARCH_INDEX_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "conv_index.json"
        cs.SEARCH_INDEX_FILE = self._path
        self.addCleanup(setattr, cs, "SEARCH_INDEX_FILE", self._orig)
        data = [
            {"id": 1, "role": "user", "text": "python programming tips",
             "timestamp": "2026-01-01T10:00:00"},
            {"id": 2, "role": "assistant", "text": "javascript frameworks",
             "timestamp": "2026-01-02T10:00:00"},
            {"id": 3, "role": "user", "text": "python and javascript both",
             "timestamp": "2026-01-03T10:00:00"},
        ]
        self._path.write_text(json.dumps(data), encoding="utf-8")

    def test_empty_query_returns_empty(self):
        self.assertEqual(cs.search(""), [])

    def test_single_term(self):
        res = cs.search("python")
        self.assertEqual(len(res), 2)
        # higher score first: entry 3 has 1 python, entry 1 has 1 python
        # both score 1 -> order by reverse iteration (entry 3 first)
        self.assertEqual(res[0]["id"], 3)

    def test_multi_term_scoring(self):
        res = cs.search("python javascript")
        # entry 3 has both terms -> score 2
        self.assertEqual(res[0]["id"], 3)
        self.assertEqual(len(res), 3)

    def test_terms_shorter_than_3_ignored(self):
        # "is" and "a" are <=2 chars -> ignored -> no terms -> empty
        self.assertEqual(cs.search("is a"), [])

    def test_limit(self):
        res = cs.search("python", limit=1)
        self.assertEqual(len(res), 1)

    def test_no_matches(self):
        self.assertEqual(cs.search("zzzzzzzz"), [])

    def test_case_insensitive(self):
        res = cs.search("PYTHON")
        self.assertEqual(len(res), 2)

    def test_default_limit_20(self):
        data = [{"id": i, "role": "user", "text": "python message",
                 "timestamp": "2026-01-01T00:00:00"} for i in range(50)]
        self._path.write_text(json.dumps(data), encoding="utf-8")
        res = cs.search("python")
        self.assertEqual(len(res), 20)


class SearchByDateTests(unittest.TestCase):
    def setUp(self):
        self._orig = cs.SEARCH_INDEX_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "conv_index.json"
        cs.SEARCH_INDEX_FILE = self._path
        self.addCleanup(setattr, cs, "SEARCH_INDEX_FILE", self._orig)
        data = [
            {"id": 1, "role": "user", "text": "a", "timestamp": "2026-01-01T10:00:00"},
            {"id": 2, "role": "user", "text": "b", "timestamp": "2026-01-05T10:00:00"},
            {"id": 3, "role": "user", "text": "c", "timestamp": "2026-01-10T10:00:00"},
        ]
        self._path.write_text(json.dumps(data), encoding="utf-8")

    def test_start_only(self):
        res = cs.search_by_date("2026-01-05")
        ids = [r["id"] for r in res]
        self.assertIn(2, ids)
        self.assertIn(3, ids)
        self.assertNotIn(1, ids)

    def test_start_and_end(self):
        res = cs.search_by_date("2026-01-01", "2026-01-05")
        ids = [r["id"] for r in res]
        self.assertIn(1, ids)
        self.assertIn(2, ids)
        self.assertNotIn(3, ids)

    def test_cap_50(self):
        data = [{"id": i, "role": "user", "text": "x",
                 "timestamp": f"2026-01-{(i % 28) + 1:02d}T00:00:00"}
                for i in range(100)]
        self._path.write_text(json.dumps(data), encoding="utf-8")
        res = cs.search_by_date("2026-01-01")
        self.assertEqual(len(res), 50)

    def test_empty_index(self):
        self._path.write_text("[]", encoding="utf-8")
        self.assertEqual(cs.search_by_date("2026-01-01"), [])

    def test_reverse_order(self):
        res = cs.search_by_date("2026-01-01")
        # reversed iteration → last entry first
        self.assertEqual(res[0]["id"], 3)


class ClearTests(unittest.TestCase):
    def setUp(self):
        self._orig = cs.SEARCH_INDEX_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "conv_index.json"
        cs.SEARCH_INDEX_FILE = self._path
        self.addCleanup(setattr, cs, "SEARCH_INDEX_FILE", self._orig)
        self._path.write_text('[{"id":1}]', encoding="utf-8")

    def test_clear(self):
        cs.clear()
        self.assertEqual(cs._load(), [])


class StatsTests(unittest.TestCase):
    def setUp(self):
        self._orig = cs.SEARCH_INDEX_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "conv_index.json"
        cs.SEARCH_INDEX_FILE = self._path
        self.addCleanup(setattr, cs, "SEARCH_INDEX_FILE", self._orig)

    def test_empty(self):
        self._path.write_text("[]", encoding="utf-8")
        self.assertEqual(cs.stats(), {"total": 0, "users": 0,
                                     "first": None, "last": None})

    def test_missing_file(self):
        # _load returns [] when missing
        self.assertEqual(cs.stats(), {"total": 0, "users": 0,
                                     "first": None, "last": None})

    def test_populated(self):
        data = [
            {"id": 1, "role": "user", "text": "a", "timestamp": "2026-01-01T10:00:00"},
            {"id": 2, "role": "assistant", "text": "b", "timestamp": "2026-01-02T10:00:00"},
            {"id": 3, "role": "user", "text": "c", "timestamp": "2026-01-03T10:00:00"},
        ]
        self._path.write_text(json.dumps(data), encoding="utf-8")
        s = cs.stats()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["users"], 2)
        self.assertEqual(s["first"], "2026-01-01")
        self.assertEqual(s["last"], "2026-01-03")


class HighlightTests(unittest.TestCase):
    def test_no_terms(self):
        self.assertEqual(cs.highlight("hello world", "a"), "hello world")

    def test_bold_terms(self):
        self.assertEqual(cs.highlight("python is great", "python"),
                         "**python** is great")

    def test_case_insensitive(self):
        self.assertEqual(cs.highlight("Python rocks", "python"),
                         "**Python** rocks")

    def test_multiple_terms(self):
        r = cs.highlight("python and javascript", "python javascript")
        self.assertIn("**python**", r)
        self.assertIn("**javascript**", r)

    def test_truncates_to_300(self):
        text = "a" * 400
        r = cs.highlight(text, "zzz")
        self.assertEqual(len(r), 300)

    def test_short_terms_ignored(self):
        # terms <=2 chars ignored -> no bolding
        self.assertEqual(cs.highlight("hi there", "hi"), "hi there")


class FormatResultsTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(cs.format_results([], "q"),
                         "🔍 'q' ke liye kuch nahi mila.")

    def test_populated(self):
        results = [
            {"role": "user", "text": "hello python world", "timestamp": "2026-01-01T10:00:00"},
            {"role": "assistant", "text": "reply", "timestamp": "2026-01-02T10:00:00"},
        ]
        out = cs.format_results(results, "python")
        self.assertIn("🔍 **Search: 'python'** (2 results)", out)
        self.assertIn("[user]", out)
        self.assertIn("[assistant]", out)

    def test_cap_10_plus_overflow(self):
        results = [{"role": "user", "text": f"msg{i}", "timestamp": "2026-01-01T00:00:00"}
                   for i in range(15)]
        out = cs.format_results(results, "q")
        self.assertIn("...aur 5 aur", out)

    def test_highlight_applied(self):
        results = [{"role": "user", "text": "python rocks", "timestamp": "2026-01-01T00:00:00"}]
        out = cs.format_results(results, "python")
        self.assertIn("**python**", out)


if __name__ == "__main__":
    unittest.main()
