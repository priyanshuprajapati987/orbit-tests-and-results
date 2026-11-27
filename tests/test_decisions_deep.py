"""Deep tests for orbit/orbit/decisions.py (Loop 18/2)."""

import json
import re
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit import decisions as dc


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = dc.DECISIONS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "decisions.json"
        dc.DECISIONS_FILE = self._path
        self.addCleanup(setattr, dc, "DECISIONS_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(dc._load(), [])

    def test_load_valid(self):
        self._path.write_text('[{"id":1}]', encoding="utf-8")
        self.assertEqual(dc._load(), [{"id": 1}])

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(dc._load(), [])

    def test_save_success(self):
        ok = dc._save([{"id": 1}])
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), [{"id": 1}])

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = dc._save([{"id": 1}])
        self.assertFalse(ok)


class NextIdTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(dc._next_id([]), 1)

    def test_max_plus_one(self):
        self.assertEqual(dc._next_id([{"id": 3}, {"id": 7}]), 8)


class CreateTests(unittest.TestCase):
    def setUp(self):
        self._orig = dc.DECISIONS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "decisions.json"
        dc.DECISIONS_FILE = self._path
        self.addCleanup(setattr, dc, "DECISIONS_FILE", self._orig)

    def test_create(self):
        d = dc.create("Should I buy a car?")
        self.assertEqual(d["question"], "Should I buy a car?")
        self.assertEqual(d["pros"], [])
        self.assertEqual(d["cons"], [])
        self.assertIn("id", d)
        self.assertIn("created", d)
        self.assertEqual(len(dc.get_all()), 1)

    def test_create_strips_question(self):
        d = dc.create("  hi  ")
        self.assertEqual(d["question"], "hi")


class AddProConTests(unittest.TestCase):
    def setUp(self):
        self._orig = dc.DECISIONS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "decisions.json"
        dc.DECISIONS_FILE = self._path
        self.addCleanup(setattr, dc, "DECISIONS_FILE", self._orig)
        self.d = dc.create("Q")

    def test_add_pro_success(self):
        self.assertTrue(dc.add_pro(self.d["id"], "fast"))
        d = dc.get(self.d["id"])
        self.assertEqual(len(d["pros"]), 1)
        self.assertEqual(d["pros"][0]["text"], "fast")
        self.assertEqual(d["pros"][0]["id"], 1)
        self.assertIn("added", d["pros"][0])

    def test_add_pro_unknown_decision(self):
        self.assertFalse(dc.add_pro(99999, "x"))

    def test_add_con_success(self):
        self.assertTrue(dc.add_con(self.d["id"], "expensive"))
        d = dc.get(self.d["id"])
        self.assertEqual(len(d["cons"]), 1)
        self.assertEqual(d["cons"][0]["text"], "expensive")

    def test_add_con_unknown(self):
        self.assertFalse(dc.add_con(99999, "x"))

    def test_add_pro_id_increments(self):
        dc.add_pro(self.d["id"], "a")
        dc.add_pro(self.d["id"], "b")
        d = dc.get(self.d["id"])
        self.assertEqual(d["pros"][0]["id"], 1)
        self.assertEqual(d["pros"][1]["id"], 2)

    def test_add_con_id_increments(self):
        dc.add_con(self.d["id"], "a")
        dc.add_con(self.d["id"], "b")
        d = dc.get(self.d["id"])
        self.assertEqual(d["cons"][0]["id"], 1)
        self.assertEqual(d["cons"][1]["id"], 2)

    def test_add_pro_strips_text(self):
        dc.add_pro(self.d["id"], "  fast  ")
        d = dc.get(self.d["id"])
        self.assertEqual(d["pros"][0]["text"], "fast")


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self._orig = dc.DECISIONS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "decisions.json"
        dc.DECISIONS_FILE = self._path
        self.addCleanup(setattr, dc, "DECISIONS_FILE", self._orig)
        self.d = dc.create("Q")

    def test_delete_success(self):
        self.assertTrue(dc.delete(self.d["id"]))
        self.assertIsNone(dc.get(self.d["id"]))

    def test_delete_missing(self):
        self.assertFalse(dc.delete(99999))

    def test_delete_does_not_save_when_missing(self):
        with mock.patch.object(dc, "_save") as sv:
            dc.delete(99999)
        sv.assert_not_called()


class DeleteItemTests(unittest.TestCase):
    def setUp(self):
        self._orig = dc.DECISIONS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "decisions.json"
        dc.DECISIONS_FILE = self._path
        self.addCleanup(setattr, dc, "DECISIONS_FILE", self._orig)
        self.d = dc.create("Q")
        dc.add_pro(self.d["id"], "p1")
        dc.add_pro(self.d["id"], "p2")
        dc.add_con(self.d["id"], "c1")

    def test_delete_pro_item(self):
        self.assertTrue(dc.delete_item(self.d["id"], 1, True))
        d = dc.get(self.d["id"])
        self.assertEqual(len(d["pros"]), 1)
        self.assertEqual(d["pros"][0]["text"], "p2")

    def test_delete_con_item(self):
        self.assertTrue(dc.delete_item(self.d["id"], 1, False))
        d = dc.get(self.d["id"])
        self.assertEqual(len(d["cons"]), 0)

    def test_delete_item_unknown_decision(self):
        self.assertFalse(dc.delete_item(99999, 1, True))

    def test_delete_item_unknown_item(self):
        self.assertFalse(dc.delete_item(self.d["id"], 999, True))

    def test_delete_item_does_not_save_when_missing(self):
        with mock.patch.object(dc, "_save") as sv:
            dc.delete_item(self.d["id"], 999, True)
        sv.assert_not_called()

    def test_delete_item_removes_from_both_lists(self):
        # delete_item removes from pros/cons regardless of is_pro for the
        # matching id (code removes from both)
        self.assertTrue(dc.delete_item(self.d["id"], 1, True))
        d = dc.get(self.d["id"])
        self.assertEqual(len(d["pros"]), 1)


class GetTests(unittest.TestCase):
    def setUp(self):
        self._orig = dc.DECISIONS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "decisions.json"
        dc.DECISIONS_FILE = self._path
        self.addCleanup(setattr, dc, "DECISIONS_FILE", self._orig)
        self.d = dc.create("Q1")
        dc.create("Q2")

    def test_get_all(self):
        self.assertEqual(len(dc.get_all()), 2)

    def test_get_found(self):
        d = dc.get(self.d["id"])
        self.assertEqual(d["question"], "Q1")

    def test_get_not_found(self):
        self.assertIsNone(dc.get(99999))


class ParseTextTests(unittest.TestCase):
    def setUp(self):
        self._orig = dc.DECISIONS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "decisions.json"
        dc.DECISIONS_FILE = self._path
        self.addCleanup(setattr, dc, "DECISIONS_FILE", self._orig)

    def test_show_empty(self):
        r = dc.parse_text("show decisions")
        self.assertEqual(r, {"type": "result", "result": "⚖️ Koi decisions nahi hai. 'should I buy a car' bolo."})

    def test_show_all(self):
        dc.create("Q1")
        r = dc.parse_text("list")
        self.assertEqual(r["type"], "result")
        self.assertIn("Decisions:", r["result"])
        self.assertIn("#", r["result"])

    def test_show_dikha(self):
        dc.create("Q1")
        r = dc.parse_text("dikha")
        self.assertEqual(r["type"], "result")

    def test_show_all_keyword(self):
        dc.create("Q1")
        r = dc.parse_text("all")
        self.assertEqual(r["type"], "result")

    def test_show_verdict_do_it(self):
        d = dc.create("Q")
        dc.add_pro(d["id"], "good")
        r = dc.parse_text("show")
        self.assertIn("Do it!", r["result"])

    def test_show_verdict_dont(self):
        d = dc.create("Q")
        dc.add_con(d["id"], "bad")
        r = dc.parse_text("show")
        self.assertIn("Don't!", r["result"])

    def test_show_verdict_neutral(self):
        dc.create("Q")
        r = dc.parse_text("show")
        self.assertIn("Neutral", r["result"])

    def test_delete_success(self):
        d = dc.create("Q")
        r = dc.parse_text(f"delete decision #{d['id']}")
        self.assertEqual(r, {"type": "result", "result": f"🗑 Decision #{d['id']} delete kar diya!"})

    def test_delete_fail(self):
        r = dc.parse_text("delete #999")
        self.assertEqual(r, {"type": "result", "result": "❌ Decision #999 nahi mila."})

    def test_delete_no_id(self):
        r = dc.parse_text("delete decision")
        self.assertEqual(r, {"type": "result", "result": "Kaunsa decision delete? ID batao."})

    def test_delete_via_remove(self):
        d = dc.create("Q")
        r = dc.parse_text(f"remove {d['id']}")
        self.assertEqual(r["type"], "result")
        self.assertIn("delete kar diya", r["result"])

    def test_delete_via_hat(self):
        d = dc.create("Q")
        r = dc.parse_text(f"hat {d['id']}")
        self.assertEqual(r["type"], "result")

    def test_pro_branch(self):
        dc.create("Should I buy a car")
        r = dc.parse_text("pro / expensive")
        self.assertEqual(r["type"], "result")
        self.assertIn("Pro added", r["result"])

    def test_pro_branch_no_decisions(self):
        r = dc.parse_text("pro / expensive")
        self.assertEqual(r, {"type": "result", "result": "Pehle decision banao. Jaise 'should I buy a car'"})

    def test_con_branch(self):
        dc.create("Should I buy a car")
        r = dc.parse_text("con / high maintenance")
        self.assertEqual(r["type"], "result")
        self.assertIn("Con added", r["result"])

    def test_con_branch_no_decisions(self):
        r = dc.parse_text("con / x")
        self.assertEqual(r, {"type": "result", "result": "Pehle decision banao."})

    def test_create_via_should(self):
        r = dc.parse_text("should I buy a car")
        self.assertEqual(r["type"], "result")
        self.assertIn("Decision #", r["result"])
        self.assertIn("created", r["result"])

    def test_create_via_pros_and_cons(self):
        r = dc.parse_text("pros and cons of eating pizza")
        self.assertEqual(r["type"], "result")
        self.assertIn("Decision #", r["result"])

    def test_create_via_pros_cons_amp(self):
        r = dc.parse_text("pros & cons for X")
        self.assertEqual(r["type"], "result")

    def test_create_question_empty_fallback(self):
        r = dc.parse_text("pros and cons of")
        self.assertEqual(r["type"], "result")
        self.assertIn("Decision #", r["result"])

    def test_show_specific_decision(self):
        d = dc.create("Q")
        dc.add_pro(d["id"], "good")
        dc.add_con(d["id"], "bad")
        r = dc.parse_text(f"#{d['id']}")
        self.assertEqual(r["type"], "result")
        # score = 1-1 = 0 -> Neutral
        self.assertIn("Neutral", r["result"])

    def test_show_specific_not_found(self):
        r = dc.parse_text("#999")
        # no decision -> falls through to info
        self.assertEqual(r["type"], "info")

    def test_help_fallthrough(self):
        r = dc.parse_text("hello world")
        self.assertEqual(r["type"], "info")
        self.assertIn("Decision Helper", r["result"])

    def test_pro_regex_variants(self):
        dc.create("Q")
        # "pros ... is ..." variant
        r = dc.parse_text("pros something is reason")
        self.assertEqual(r["type"], "result")
        self.assertIn("Pro added", r["result"])

    def test_con_regex_variants(self):
        dc.create("Q")
        r = dc.parse_text("cons something are reason")
        self.assertEqual(r["type"], "result")
        self.assertIn("Con added", r["result"])


if __name__ == "__main__":
    unittest.main()
