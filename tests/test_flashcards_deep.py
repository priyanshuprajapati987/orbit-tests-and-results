"""Deep tests for orbit/orbit/flashcards.py (Loop 16/5)."""

import json
import random
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit import flashcards as fc


class LoadSaveTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)

    def test_load_missing(self):
        self.assertEqual(fc._load(), [])

    def test_load_valid(self):
        self._path.write_text('[{"id":1}]', encoding="utf-8")
        self.assertEqual(fc._load(), [{"id": 1}])

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        self.assertEqual(fc._load(), [])

    def test_save_success(self):
        ok = fc._save([{"id": 1}])
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), [{"id": 1}])

    def test_save_failure(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")):
            ok = fc._save([{"id": 1}])
        self.assertFalse(ok)


class NextIdTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(fc._next_id([]), 1)

    def test_max_plus_one(self):
        self.assertEqual(fc._next_id([{"id": 3}, {"id": 7}]), 8)


class AddTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)

    def test_add_basic(self):
        c = fc.add("What is Python?", "A language", "python")
        self.assertEqual(c["front"], "What is Python?")
        self.assertEqual(c["back"], "A language")
        self.assertEqual(c["deck"], "python")
        self.assertEqual(c["box"], 0)
        self.assertEqual(c["correct"], 0)
        self.assertEqual(c["wrong"], 0)
        self.assertEqual(c["next_review"], date.today().isoformat())
        self.assertIn("id", c)
        self.assertIn("created", c)
        self.assertEqual(len(fc._load()), 1)

    def test_add_strips(self):
        c = fc.add("  q  ", "  a  ")
        self.assertEqual(c["front"], "q")
        self.assertEqual(c["back"], "a")

    def test_add_default_deck(self):
        c = fc.add("q", "a")
        self.assertEqual(c["deck"], "general")

    def test_add_id_increments(self):
        fc.add("a", "b")
        c2 = fc.add("c", "d")
        self.assertEqual(c2["id"], 2)


class GetAllTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)
        fc.add("q1", "a1", "python")
        fc.add("q2", "a2", "js")

    def test_get_all_no_filter(self):
        self.assertEqual(len(fc.get_all()), 2)

    def test_get_all_by_deck(self):
        r = fc.get_all("python")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["deck"], "python")

    def test_get_all_unknown_deck(self):
        self.assertEqual(fc.get_all("nope"), [])


class GetDecksTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)

    def test_empty_returns_general(self):
        self.assertEqual(fc.get_decks(), ["general"])

    def test_with_cards(self):
        fc.add("q", "a", "python")
        fc.add("q2", "a2", "js")
        decks = fc.get_decks()
        self.assertIn("python", decks)
        self.assertIn("js", decks)


class GetCardTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)
        self.card = fc.add("q", "a")

    def test_found(self):
        c = fc.get_card(self.card["id"])
        self.assertEqual(c["front"], "q")

    def test_not_found(self):
        self.assertIsNone(fc.get_card(99999))


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)
        self.card = fc.add("q", "a")

    def test_delete_success(self):
        self.assertTrue(fc.delete(self.card["id"]))
        self.assertIsNone(fc.get_card(self.card["id"]))

    def test_delete_missing(self):
        self.assertFalse(fc.delete(99999))

    def test_delete_does_not_save_when_missing(self):
        with mock.patch.object(fc, "_save") as sv:
            fc.delete(99999)
        sv.assert_not_called()


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)
        self.card = fc.add("q", "a")

    def test_review_correct_increments_box(self):
        cid = self.card["id"]
        self.assertTrue(fc.review(cid, True))
        c = fc.get_card(cid)
        self.assertEqual(c["box"], 1)
        self.assertEqual(c["correct"], 1)
        self.assertEqual(c["wrong"], 0)
        # next_review = today + 2 days (intervals[1]=2)
        from datetime import date, timedelta
        self.assertEqual(c["next_review"], (date.today() + timedelta(days=2)).isoformat())

    def test_review_correct_caps_box_at_5(self):
        cid = self.card["id"]
        for _ in range(6):
            fc.review(cid, True)
        c = fc.get_card(cid)
        self.assertEqual(c["box"], 5)
        # intervals[5]=32
        from datetime import date, timedelta
        self.assertEqual(c["next_review"], (date.today() + timedelta(days=32)).isoformat())

    def test_review_wrong_decrements_box(self):
        cid = self.card["id"]
        fc.review(cid, True)  # box=1
        fc.review(cid, False)  # box=0
        c = fc.get_card(cid)
        self.assertEqual(c["box"], 0)
        self.assertEqual(c["wrong"], 1)
        self.assertEqual(c["correct"], 1)

    def test_review_wrong_caps_box_at_0(self):
        cid = self.card["id"]
        fc.review(cid, False)  # box already 0, max(0-1,0)=0
        c = fc.get_card(cid)
        self.assertEqual(c["box"], 0)

    def test_review_unknown_returns_false(self):
        self.assertFalse(fc.review(99999, True))

    def test_review_box_2_interval(self):
        cid = self.card["id"]
        fc.review(cid, True)  # box 1
        fc.review(cid, True)  # box 2
        c = fc.get_card(cid)
        from datetime import date, timedelta
        self.assertEqual(c["next_review"], (date.today() + timedelta(days=4)).isoformat())


class GetDueTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)

    def test_due_today(self):
        fc.add("q", "a")
        due = fc.get_due()
        self.assertEqual(len(due), 1)

    def test_due_with_deck_filter(self):
        fc.add("q", "a", "python")
        fc.add("q2", "a2", "js")
        due = fc.get_due("python")
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["deck"], "python")

    def test_not_due(self):
        c = fc.add("q", "a")
        # set next_review to future
        cards = fc._load()
        cards[0]["next_review"] = "2099-12-31"
        fc._save(cards)
        self.assertEqual(fc.get_due(), [])

    def test_empty(self):
        self.assertEqual(fc.get_due(), [])


class GetStatsTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)

    def test_empty(self):
        self.assertEqual(fc.get_stats(), {"total": 0, "due": 0,
                                          "mastered": 0, "avg_correct": 0})

    def test_with_cards(self):
        c = fc.add("q", "a")
        fc.review(c["id"], True)
        fc.review(c["id"], True)
        fc.review(c["id"], True)
        fc.review(c["id"], True)  # box 4 -> mastered
        stats = fc.get_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["mastered"], 1)
        self.assertEqual(stats["avg_correct"], 4.0)
        self.assertEqual(stats["due"], 0)  # next_review future

    def test_due_count(self):
        fc.add("q", "a")
        stats = fc.get_stats()
        self.assertEqual(stats["due"], 1)
        self.assertEqual(stats["mastered"], 0)


class ParseAddTextTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)

    def test_no_slash_returns_none(self):
        self.assertIsNone(fc.parse_add_text("add card hello"))

    def test_basic(self):
        c = fc.parse_add_text("add card What is Python / A language")
        self.assertIsNotNone(c)
        self.assertEqual(c["front"], "What is Python")
        self.assertEqual(c["back"], "A language")
        self.assertEqual(c["deck"], "general")

    def test_deck_suffix(self):
        c = fc.parse_add_text("add card Q / A python")
        self.assertEqual(c["front"], "Q")
        self.assertEqual(c["back"], "A")
        self.assertEqual(c["deck"], "python")

    def test_deck_candidates_endswith(self):
        c = fc.parse_add_text("add card Q / A js")
        self.assertEqual(c["deck"], "js")
        self.assertEqual(c["back"], "A")

    def test_deck_candidates_longer_match(self):
        # "general" is a known deck; ends with "general"
        c = fc.parse_add_text("add card Q / A general")
        self.assertEqual(c["deck"], "general")
        self.assertEqual(c["back"], "A")

    def test_pipe_split(self):
        # re.split uses / only, not |. Test / with deck
        c = fc.parse_add_text("card hello / world english")
        self.assertEqual(c["front"], "hello")
        self.assertEqual(c["back"], "world")
        self.assertEqual(c["deck"], "english")

    def test_empty_front_returns_none(self):
        c = fc.parse_add_text("add card  / A")
        self.assertIsNone(c)

    def test_empty_back_returns_none(self):
        c = fc.parse_add_text("add card Q / ")
        self.assertIsNone(c)

    def test_command_word_stripping(self):
        c = fc.parse_add_text("flashcard Q / A")
        self.assertIsNotNone(c)
        self.assertEqual(c["front"], "Q")

    def test_card_command(self):
        c = fc.parse_add_text("card Q / A")
        self.assertIsNotNone(c)

    def test_new_command(self):
        c = fc.parse_add_text("new card Q / A")
        self.assertIsNotNone(c)

    def test_add_command(self):
        c = fc.parse_add_text("add Q / A")
        self.assertIsNotNone(c)


class FormatCardsTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(fc.format_cards([], "MyCards"),
                         "🃏 MyCards: Koi cards nahi.")

    def test_basic(self):
        cards = [{"id": 1, "deck": "g", "front": "q", "back": "a",
                  "next_review": date.today().isoformat()}]
        out = fc.format_cards(cards, "Title")
        self.assertIn("🃏 **Title:** (1 cards)", out)
        self.assertIn("#1 [g] q — a 🔔", out)

    def test_no_due(self):
        cards = [{"id": 1, "deck": "g", "front": "q", "back": "a",
                  "next_review": "2099-12-31"}]
        out = fc.format_cards(cards)
        self.assertIn("#1 [g] q — a", out)
        self.assertNotIn("🔔", out)

    def test_cap_15(self):
        cards = [{"id": i, "deck": "g", "front": f"q{i}", "back": f"a{i}",
                  "next_review": "2099-12-31"} for i in range(20)]
        out = fc.format_cards(cards)
        self.assertIn("... aur 5 aur", out)
        self.assertEqual(out.count("#"), 15)

    def test_default_title(self):
        out = fc.format_cards([])
        self.assertIn("Cards", out)


class FormatCardTests(unittest.TestCase):
    def test_format(self):
        c = {"id": 1, "deck": "g", "front": "q", "back": "a",
             "box": 2, "correct": 3, "wrong": 1, "next_review": "2026-01-01"}
        out = fc.format_card(c)
        self.assertEqual(out, "🃏 #1 [g]\n  **Q:** q\n  **A:** a\n  Box: 2/5 | ✅3 ❌1 | Next: 2026-01-01")


class StudySessionTests(unittest.TestCase):
    def setUp(self):
        self._orig = fc.CARDS_FILE
        import tempfile
        self._d = tempfile.mkdtemp()
        self._path = Path(self._d) / "flashcards.json"
        fc.CARDS_FILE = self._path
        self.addCleanup(setattr, fc, "CARDS_FILE", self._orig)

    def test_empty(self):
        self.assertEqual(fc.study_session(), [])

    def test_returns_due_capped_10(self):
        for i in range(15):
            fc.add(f"q{i}", f"a{i}")
        due = fc.study_session()
        self.assertEqual(len(due), 10)

    def test_deck_filter(self):
        fc.add("q", "a", "python")
        fc.add("q2", "a2", "js")
        due = fc.study_session("python")
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["deck"], "python")

    def test_shuffled(self):
        for i in range(5):
            fc.add(f"q{i}", f"a{i}")
        due = fc.study_session()
        self.assertEqual(len(due), 5)


if __name__ == "__main__":
    unittest.main()
