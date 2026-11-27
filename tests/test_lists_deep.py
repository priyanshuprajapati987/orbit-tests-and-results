"""Deep tests for orbit/orbit/lists.py (Loop 15/4)."""

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit import lists as ls


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(ls._load(), {})

    def test_load_valid(self):
        self._path.write_text('{"a":{"name":"a","items":[]}}', encoding="utf-8")
        self.assertEqual(ls._load(), {"a": {"name": "a", "items": []}})

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(ls._load(), {})

    def test_load_non_dict(self):
        self._path.write_text('[1,2,3]', encoding="utf-8")
        self.assertEqual(ls._load(), {})

    def test_save_success(self):
        ok = ls._save({"a": 1})
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), {"a": 1})

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = ls._save({"a": 1})
        self.assertFalse(ok)


class EnsureListTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)

    def test_creates_new(self):
        lst = ls._ensure_list("grocery")
        self.assertEqual(lst["name"], "grocery")
        self.assertEqual(lst["items"], [])
        self.assertIn("created", lst)
        # persisted
        self.assertIn("grocery", ls._load())

    def test_returns_existing(self):
        ls._ensure_list("grocery")
        lst2 = ls._ensure_list("grocery")
        self.assertEqual(lst2["name"], "grocery")
        # no duplicate save? _ensure_list saves on create only
        # (second call doesn't save since name in data)


class ListNamesTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)

    def test_empty(self):
        self.assertEqual(ls.list_names(), [])

    def test_names(self):
        ls._ensure_list("a")
        ls._ensure_list("b")
        self.assertEqual(sorted(ls.list_names()), ["a", "b"])


class AddItemTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)

    def test_add_basic(self):
        e = ls.add_item("grocery", "milk")
        self.assertEqual(e["text"], "milk")
        self.assertFalse(e["checked"])
        self.assertEqual(e["id"], 1)
        self.assertIn("created", e)
        # persisted
        lst = ls.get_list("grocery")
        self.assertEqual(len(lst["items"]), 1)
        self.assertEqual(lst["items"][0]["text"], "milk")

    def test_id_increments(self):
        ls.add_item("g", "a")
        e2 = ls.add_item("g", "b")
        self.assertEqual(e2["id"], 2)

    def test_check_preserved(self):
        ls.add_item("g", "a")
        ls.check_item("g", 1)
        e2 = ls.add_item("g", "b")
        self.assertEqual(e2["id"], 2)


class CheckItemTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)
        ls.add_item("g", "milk")

    def test_check_success(self):
        self.assertTrue(ls.check_item("g", 1))
        self.assertTrue(ls.get_list("g")["items"][0]["checked"])

    def test_check_uncheck(self):
        ls.check_item("g", 1, checked=False)
        self.assertFalse(ls.get_list("g")["items"][0]["checked"])

    def test_check_unknown_list(self):
        self.assertFalse(ls.check_item("nope", 1))

    def test_check_unknown_item(self):
        self.assertFalse(ls.check_item("g", 999))


class RemoveItemTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)
        ls.add_item("g", "milk")
        ls.add_item("g", "bread")

    def test_remove_success(self):
        self.assertTrue(ls.remove_item("g", 1))
        items = ls.get_list("g")["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "bread")

    def test_remove_unknown_list(self):
        self.assertFalse(ls.remove_item("nope", 1))

    def test_remove_unknown_item(self):
        self.assertFalse(ls.remove_item("g", 999))


class GetListTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)

    def test_get_existing(self):
        ls._ensure_list("g")
        lst = ls.get_list("g")
        self.assertEqual(lst["name"], "g")

    def test_get_missing(self):
        self.assertIsNone(ls.get_list("nope"))


class DeleteListTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)
        ls._ensure_list("g")

    def test_delete_success(self):
        self.assertTrue(ls.delete_list("g"))
        self.assertIsNone(ls.get_list("g"))

    def test_delete_missing(self):
        self.assertFalse(ls.delete_list("nope"))


class AddItemsFromTextTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)

    def test_comma_separated(self):
        created = ls.add_items_from_text("g", "milk, bread, eggs")
        self.assertEqual(len(created), 3)
        self.assertEqual([c["text"] for c in created], ["milk", "bread", "eggs"])

    def test_semicolon_and_newline(self):
        created = ls.add_items_from_text("g", "a;b\nc")
        self.assertEqual([c["text"] for c in created], ["a", "b", "c"])

    def test_strips_dots(self):
        created = ls.add_items_from_text("g", "milk., bread")
        self.assertEqual([c["text"] for c in created], ["milk", "bread"])

    def test_empty_items_skipped(self):
        created = ls.add_items_from_text("g", "a,,b,  ,c")
        self.assertEqual(len(created), 3)

    def test_empty_text(self):
        created = ls.add_items_from_text("g", "")
        self.assertEqual(created, [])


class FormatListTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)

    def test_missing_list(self):
        self.assertEqual(ls.format_list("nope"), "📋 List 'nope' nahi mila.")

    def test_empty_list(self):
        ls._ensure_list("g")
        self.assertEqual(ls.format_list("g"), "📋 **G:** (empty)")

    def test_with_items(self):
        ls.add_item("g", "milk")
        ls.add_item("g", "bread")
        ls.check_item("g", 1)
        out = ls.format_list("g")
        self.assertIn("📋 **G:** (2 items, 1 done)", out)
        self.assertIn("⬜ #2 bread", out)
        self.assertIn("✅ #1 ~~milk~~", out)

    def test_all_unchecked(self):
        ls.add_item("g", "milk")
        out = ls.format_list("g")
        self.assertIn("⬜ #1 milk", out)
        self.assertNotIn("✅", out)


class FormatAllListsTests(unittest.TestCase):
    def setUp(self):
        self._orig = ls.LISTS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "lists.json"
        ls.LISTS_FILE = self._path
        self.addCleanup(setattr, ls, "LISTS_FILE", self._orig)

    def test_empty(self):
        self.assertEqual(ls.format_all_lists(), "📋 Koi lists nahi hai. 'create list grocery' bolo.")

    def test_with_lists(self):
        ls.add_item("g", "milk")
        ls.add_item("g", "bread")
        ls.check_item("g", 1)
        out = ls.format_all_lists()
        self.assertIn("📋 **All Lists:**", out)
        self.assertIn("📁 **g:** 1/2 done", out)


if __name__ == "__main__":
    unittest.main()
