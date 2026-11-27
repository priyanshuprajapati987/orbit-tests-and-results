"""Deep tests for orbit/orbit/quotes.py (Loop 15/5)."""

import json
import random
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit import quotes as q


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = q.QUOTES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "quotes.json"
        q.QUOTES_FILE = self._path
        self.addCleanup(setattr, q, "QUOTES_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(q._load(), [])

    def test_load_valid(self):
        self._path.write_text('[{"id":1,"text":"hi","author":"a"}]', encoding="utf-8")
        self.assertEqual(q._load(), [{"id": 1, "text": "hi", "author": "a"}])

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(q._load(), [])

    def test_save_success(self):
        ok = q._save([{"id": 1}])
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), [{"id": 1}])

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = q._save([{"id": 1}])
        self.assertFalse(ok)


class EnsureTests(unittest.TestCase):
    def setUp(self):
        self._orig = q.QUOTES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "quotes.json"
        q.QUOTES_FILE = self._path
        self.addCleanup(setattr, q, "QUOTES_FILE", self._orig)

    def test_ensure_seeds_defaults_when_empty(self):
        q._ensure()
        self.assertEqual(len(q._load()), len(q._DEFAULT_QUOTES))
        # all have ids? defaults don't have ids initially
        # _ensure saves defaults as-is (no ids added)
        self.assertGreater(len(q.get_all()), 0)

    def test_ensure_loads_existing(self):
        self._path.write_text('[{"id":1,"text":"hi","author":"a"}]', encoding="utf-8")
        qs = q._ensure()
        self.assertEqual(qs, [{"id": 1, "text": "hi", "author": "a"}])

    def test_ensure_empty_list_triggers_seed(self):
        self._path.write_text('[]', encoding="utf-8")
        q._ensure()
        self.assertEqual(len(q._load()), len(q._DEFAULT_QUOTES))


class NextIdTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(q._next_id([]), 1)

    def test_max_plus_one(self):
        self.assertEqual(q._next_id([{"id": 3}, {"id": 7}]), 8)


class AddTests(unittest.TestCase):
    def setUp(self):
        self._orig = q.QUOTES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "quotes.json"
        q.QUOTES_FILE = self._path
        self.addCleanup(setattr, q, "QUOTES_FILE", self._orig)

    def test_add_basic(self):
        qd = q.add("Be the change", "Gandhi")
        self.assertEqual(qd["text"], "Be the change")
        self.assertEqual(qd["author"], "Gandhi")
        self.assertIn("id", qd)
        self.assertIn("added", qd)
        # persisted
        self.assertEqual(len(q.get_all()), len(q._DEFAULT_QUOTES) + 1)

    def test_add_author_stripped_empty_defaults_unknown(self):
        qd = q.add("text", "   ")
        self.assertEqual(qd["author"], "Unknown")

    def test_add_text_stripped(self):
        qd = q.add("  hello  ", "A")
        self.assertEqual(qd["text"], "hello")

    def test_add_id_increments(self):
        q1 = q.add("a", "A")
        q2 = q.add("b", "B")
        self.assertGreater(q2["id"], q1["id"])


class GetRandomTests(unittest.TestCase):
    def setUp(self):
        self._orig = q.QUOTES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "quotes.json"
        q.QUOTES_FILE = self._path
        self.addCleanup(setattr, q, "QUOTES_FILE", self._orig)

    def test_get_random_returns_one(self):
        with mock.patch.object(q.random, "choice", return_value={"id": 1}) as rc:
            r = q.get_random()
        self.assertEqual(r, {"id": 1})
        rc.assert_called_once()

    def test_get_random_calls_ensure(self):
        # get_random calls _ensure internally
        q.get_random()
        self.assertGreater(len(q._load()), 0)


class GetAllSearchTests(unittest.TestCase):
    def setUp(self):
        self._orig = q.QUOTES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "quotes.json"
        q.QUOTES_FILE = self._path
        self.addCleanup(setattr, q, "QUOTES_FILE", self._orig)

    def test_get_all(self):
        qs = q.get_all()
        self.assertEqual(len(qs), len(q._DEFAULT_QUOTES))

    def test_search_by_text(self):
        r = q.search("predict")
        self.assertEqual(len(r), 1)
        self.assertIn("predict", r[0]["text"].lower())

    def test_search_by_author(self):
        r = q.search("Einstein")
        self.assertEqual(len(r), 2)

    def test_search_case_insensitive(self):
        r = q.search("PREDICT")
        self.assertEqual(len(r), 1)

    def test_search_no_match(self):
        self.assertEqual(q.search("zzzzzzz"), [])

    def test_search_empty_query_matches_all(self):
        # "" in any text/author -> all match
        r = q.search("")
        self.assertEqual(len(r), len(q._DEFAULT_QUOTES))


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self._orig = q.QUOTES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "quotes.json"
        q.QUOTES_FILE = self._path
        self.addCleanup(setattr, q, "QUOTES_FILE", self._orig)
        q.add("to delete", "A")

    def test_delete_existing(self):
        # find the id
        qs = q.get_all()
        qid = [x for x in qs if x["text"] == "to delete"][0]["id"]
        self.assertTrue(q.delete(qid))
        self.assertEqual(len([x for x in q.get_all() if x["text"] == "to delete"]), 0)

    def test_delete_missing(self):
        self.assertFalse(q.delete(99999))

    def test_delete_does_not_save_when_missing(self):
        with mock.patch.object(q, "_save") as sv:
            q.delete(99999)
        sv.assert_not_called()


class FormatTests(unittest.TestCase):
    def test_format_quote(self):
        qd = {"text": "hi", "author": "me"}
        self.assertEqual(q.format_quote(qd), '💬 **"hi"**\n   — me')

    def test_format_random(self):
        with mock.patch.object(q, "get_random", return_value={"text": "t", "author": "a"}):
            self.assertEqual(q.format_random(), '💬 **"t"**\n   — a')


class ParseTextTests(unittest.TestCase):
    def setUp(self):
        self._orig = q.QUOTES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "quotes.json"
        q.QUOTES_FILE = self._path
        self.addCleanup(setattr, q, "QUOTES_FILE", self._orig)

    def test_random_branch(self):
        with mock.patch.object(q, "format_random", return_value="FQ"):
            r = q.parse_text("random quote")
        self.assertEqual(r, {"type": "result", "result": "FQ"})

    def test_random_via_kuch_bata(self):
        with mock.patch.object(q, "format_random", return_value="FQ"):
            r = q.parse_text("kuch bata")
        self.assertEqual(r["type"], "result")

    def test_random_via_inspire(self):
        with mock.patch.object(q, "format_random", return_value="FQ"):
            r = q.parse_text("inspire me")
        self.assertEqual(r["type"], "result")

    def test_show_branch(self):
        q._ensure()
        r = q.parse_text("show all")
        self.assertEqual(r["type"], "result")
        self.assertIn("Quotes:", r["result"])

    def test_show_empty(self):
        # force empty by writing empty list (but _ensure seeds defaults if empty)
        # To get empty, monkeypatch _load to return [] and _ensure to return []
        with mock.patch.object(q, "_ensure", return_value=[]):
            r = q.parse_text("list")
        self.assertEqual(r, {"type": "info", "result": "💬 Koi quotes nahi hai. 'add quote Be the change - Gandhi' bolo."})

    def test_show_caps_at_20(self):
        qs = [{"id": i, "text": f"t{i}", "author": "a"} for i in range(25)]
        with mock.patch.object(q, "get_all", return_value=qs):
            r = q.parse_text("dikha")
        self.assertIn("...aur" if False else "Quotes:", r["result"])
        # 20 shown
        self.assertEqual(r["result"].count("#"), 20)

    def test_search_branch_found(self):
        with mock.patch.object(q, "search", return_value=[{"id": 1, "text": "t", "author": "a"}]):
            r = q.parse_text("search change")
        self.assertEqual(r["type"], "result")
        self.assertIn("Found 1 quotes", r["result"])

    def test_search_branch_not_found(self):
        with mock.patch.object(q, "search", return_value=[]):
            r = q.parse_text("find xyz")
        self.assertEqual(r, {"type": "info", "result": "🔍 'xyz' se koi quote nahi mila."})

    def test_search_no_query(self):
        r = q.parse_text("search quote")
        # q becomes "" after stripping -> info
        self.assertEqual(r, {"type": "info", "result": "Kaunsa search karun? 'search quote change' bolo."})

    def test_search_via_dhund(self):
        with mock.patch.object(q, "search", return_value=[]):
            r = q.parse_text("dhund foo")
        self.assertEqual(r["type"], "info")

    def test_delete_branch_success(self):
        with mock.patch.object(q, "delete", return_value=True):
            r = q.parse_text("delete #5")
        self.assertEqual(r, {"type": "result", "result": "🗑 Quote #5 delete!"})

    def test_delete_branch_fail(self):
        with mock.patch.object(q, "delete", return_value=False):
            r = q.parse_text("remove 7")
        self.assertEqual(r, {"type": "error", "result": "❌ Quote #7 nahi mila."})

    def test_delete_no_id(self):
        r = q.parse_text("delete quote")
        self.assertEqual(r, {"type": "info", "result": "Kaunsa quote delete? ID batao."})

    def test_delete_via_hat(self):
        with mock.patch.object(q, "delete", return_value=True):
            r = q.parse_text("hat 3")
        self.assertEqual(r["type"], "result")

    def test_add_branch_with_author(self):
        with mock.patch.object(q, "add", return_value={"id": 1, "text": "Be the change", "author": "Gandhi"}):
            r = q.parse_text("add quote Be the change - Gandhi")
        self.assertEqual(r["type"], "result")
        self.assertIn("Quote #1 added!", r["result"])

    def test_add_branch_slash_author(self):
        with mock.patch.object(q, "add", return_value={"id": 2, "text": "t", "author": "a"}) as ad:
            r = q.parse_text("add quote hello / author")
        ad.assert_called_once_with("hello", "author")

    def test_add_branch_no_author_uses_title(self):
        from orbit.orbit import config as cfg
        with mock.patch.object(q, "add", return_value={"id": 3, "text": "t", "author": cfg.TITLE}) as ad, \
                mock.patch.object(q, "TITLE", cfg.TITLE, create=True):
            r = q.parse_text("add quote hello")
        # author defaults to TITLE
        self.assertEqual(ad.call_args.args[1], cfg.TITLE)

    def test_add_branch_empty_text(self):
        r = q.parse_text("add")
        self.assertEqual(r, {"type": "info", "result": "Kya quote save karun? 'add quote Be the change - Gandhi' bolo."})

    def test_add_via_new(self):
        with mock.patch.object(q, "add", return_value={"id": 1, "text": "t", "author": "a"}):
            r = q.parse_text("new quote t")
        self.assertEqual(r["type"], "result")

    def test_add_via_save(self):
        with mock.patch.object(q, "add", return_value={"id": 1, "text": "t", "author": "a"}):
            r = q.parse_text("save quote t")
        self.assertEqual(r["type"], "result")

    def test_fallthrough_random(self):
        with mock.patch.object(q, "format_random", return_value="FR"):
            r = q.parse_text("blah blah")
        self.assertEqual(r, {"type": "result", "result": "FR"})


if __name__ == "__main__":
    unittest.main()
