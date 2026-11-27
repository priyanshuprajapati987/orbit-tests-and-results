"""Deep tests for orbit/orbit/expenses.py (Loop 14/5)."""

import json
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from orbit.orbit import expenses as ex


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(ex._load(), [])

    def test_load_valid(self):
        self._path.write_text('[{"id":1}]', encoding="utf-8")
        self.assertEqual(ex._load(), [{"id": 1}])

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(ex._load(), [])

    def test_save_success(self):
        ok = ex._save([{"id": 1}])
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), [{"id": 1}])

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = ex._save([{"id": 1}])
        self.assertFalse(ok)


class NextIdTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ex._next_id([]), 1)

    def test_max_plus_one(self):
        self.assertEqual(ex._next_id([{"id": 3}, {"id": 7}, {"id": 2}]), 8)


class AddTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)

    def test_add_basic(self):
        e = ex.add(100.5, "food", "lunch")
        self.assertEqual(e["amount"], 100.5)
        self.assertEqual(e["category"], "food")
        self.assertEqual(e["note"], "lunch")
        self.assertEqual(e["id"], 1)
        self.assertEqual(e["date"], date.today().isoformat())
        self.assertIn("created", e)
        # persisted
        self.assertEqual(len(ex._load()), 1)

    def test_add_rounds_amount(self):
        e = ex.add(100.567, "food")
        self.assertEqual(e["amount"], 100.57)

    def test_add_category_lowercased(self):
        e = ex.add(10, "FOOD")
        self.assertEqual(e["category"], "food")

    def test_add_note_stripped(self):
        e = ex.add(10, "food", "  lunch  ")
        self.assertEqual(e["note"], "lunch")

    def test_add_second_increments_id(self):
        ex.add(10, "food")
        e2 = ex.add(20, "transport")
        self.assertEqual(e2["id"], 2)


class GetAllByDateMonthTodayTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)
        # seed
        data = [
            {"id": 1, "amount": 100.0, "category": "food", "note": "a",
             "date": "2026-01-15", "created": "x"},
            {"id": 2, "amount": 50.0, "category": "transport", "note": "b",
             "date": "2026-02-10", "created": "x"},
            {"id": 3, "amount": 30.0, "category": "food", "note": "c",
             "date": date.today().isoformat(), "created": "x"},
        ]
        self._path.write_text(json.dumps(data), encoding="utf-8")

    def test_get_all(self):
        self.assertEqual(len(ex.get_all()), 3)

    def test_get_by_date(self):
        r = ex.get_by_date("2026-01-15")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["id"], 1)

    def test_get_by_month(self):
        r = ex.get_by_month(2026, 1)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["id"], 1)

    def test_get_by_month_zero_padded(self):
        r = ex.get_by_month(2026, 2)
        self.assertEqual(len(r), 1)

    def test_get_today(self):
        r = ex.get_today()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["id"], 3)


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)
        self._path.write_text(json.dumps([
            {"id": 1, "amount": 10.0, "category": "food", "note": "a",
             "date": "2026-01-15", "created": "x"},
            {"id": 2, "amount": 20.0, "category": "food", "note": "b",
             "date": "2026-01-15", "created": "x"},
        ]), encoding="utf-8")

    def test_delete_existing(self):
        self.assertTrue(ex.delete(1))
        self.assertEqual(len(ex._load()), 1)
        self.assertEqual(ex._load()[0]["id"], 2)

    def test_delete_missing(self):
        self.assertFalse(ex.delete(999))
        self.assertEqual(len(ex._load()), 2)

    def test_delete_does_not_save_when_missing(self):
        with mock.patch.object(ex, "_save") as sv:
            ex.delete(999)
        sv.assert_not_called()


class TotalMonthTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)
        data = [
            {"id": 1, "amount": 100.0, "category": "food", "note": "a",
             "date": "2026-01-15", "created": "x"},
            {"id": 2, "amount": 50.0, "category": "food", "note": "b",
             "date": "2026-01-20", "created": "x"},
            {"id": 3, "amount": 30.0, "category": "transport", "note": "c",
             "date": "2026-01-20", "created": "x"},
        ]
        self._path.write_text(json.dumps(data), encoding="utf-8")

    def test_total_month(self):
        s = ex.total_month(2026, 1)
        self.assertEqual(s["total"], 180.0)
        self.assertEqual(s["count"], 3)
        self.assertEqual(s["categories"], {"food": 150.0, "transport": 30.0})

    def test_total_month_empty(self):
        s = ex.total_month(2026, 12)
        self.assertEqual(s, {"total": 0.0, "count": 0, "categories": {}})

    def test_total_today(self):
        # no today entries -> 0
        s = ex.total_today()
        self.assertEqual(s["total"], 0.0)
        self.assertEqual(s["count"], 0)


class TotalTodayWithDataTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)
        today = date.today().isoformat()
        data = [
            {"id": 1, "amount": 10.5, "category": "food", "note": "a",
             "date": today, "created": "x"},
            {"id": 2, "amount": 20.0, "category": "transport", "note": "b",
             "date": today, "created": "x"},
        ]
        self._path.write_text(json.dumps(data), encoding="utf-8")

    def test_total_today(self):
        s = ex.total_today()
        self.assertEqual(s["total"], 30.5)
        self.assertEqual(s["count"], 2)


class ParseAndAddTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)

    def test_no_amount(self):
        r = ex.parse_and_add("kharcha pizza")
        self.assertEqual(r, "Kitna kharch kiya? Jaise: 'kharcha 300 pizza' ya 'expense 500 petrol'")

    def test_basic_add(self):
        r = ex.parse_and_add("kharcha 300 pizza")
        self.assertIn("💰", r)
        self.assertIn("Other", r)
        self.assertIn("300", r)
        self.assertIn("pizza", r)

    def test_category_detection(self):
        r = ex.parse_and_add("expense 500 petrol")
        self.assertIn("Transport", r)

    def test_category_default_other(self):
        r = ex.parse_and_add("spent 100 xyz")
        self.assertIn("Other", r)

    def test_note_fallback_to_category(self):
        # text only has amount + command word -> note becomes category
        r = ex.parse_and_add("expense 50")
        self.assertIn("Other", r)

    def test_comma_decimal(self):
        r = ex.parse_and_add("kharcha 50,5 chai")
        self.assertIn("50.5", r)

    def test_today_total_in_message(self):
        ex.parse_and_add("kharcha 100 food")
        r = ex.parse_and_add("kharcha 50 food")
        self.assertIn("Today:", r)


class FormatMonthTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)

    def test_empty_month(self):
        r = ex.format_month(2026, 1)
        self.assertEqual(r, "💰 **1/2026:** Koi kharcha nahi hai.")

    def test_default_year_month(self):
        r = ex.format_month()
        # today's month, no entries
        today = date.today()
        self.assertIn(f"💰 **{today.month}/{today.year}:**", r)
        self.assertIn("Koi kharcha nahi", r)

    def test_with_entries(self):
        ex.add(100.0, "food", "lunch")
        ex.add(50.0, "transport", "cab")
        today = date.today()
        r = ex.format_month(today.year, today.month)
        self.assertIn("Total", r)
        self.assertIn("2 entries", r)
        self.assertIn("Food", r)
        self.assertIn("Transport", r)
        # bar has 20 chars
        bar_line = [l for l in r.splitlines() if "█" in l][0]
        bar = "".join(c for c in bar_line if c in "█░")
        self.assertEqual(len(bar), 20)


class FormatTodayTests(unittest.TestCase):
    def setUp(self):
        self._orig = ex.EXPENSES_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "expenses.json"
        ex.EXPENSES_FILE = self._path
        self.addCleanup(setattr, ex, "EXPENSES_FILE", self._orig)

    def test_empty(self):
        self.assertEqual(ex.format_today(), "💰 Aaj koi kharcha nahi hai.")

    def test_with_entries(self):
        ex.add(10.5, "food", "lunch")
        r = ex.format_today()
        self.assertIn("Today:", r)
        self.assertIn("1 entries", r)
        self.assertIn("#1", r)
        self.assertIn("lunch", r)


if __name__ == "__main__":
    unittest.main()
