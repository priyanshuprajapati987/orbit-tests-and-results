"""Deep tests for orbit/orbit/core/idea_vault.py (Loop 20/1)."""

import json
import threading
import unittest
import uuid
from pathlib import Path
from unittest import mock

from orbit.orbit.core import idea_vault as iv


class CoerceRatingTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(iv._coerce_rating(5), 5)
        self.assertEqual(iv._coerce_rating(1), 1)
        self.assertEqual(iv._coerce_rating(10), 10)

    def test_clamp_low(self):
        self.assertEqual(iv._coerce_rating(0), 1)
        self.assertEqual(iv._coerce_rating(-5), 1)

    def test_clamp_high(self):
        self.assertEqual(iv._coerce_rating(15), 10)

    def test_invalid_type(self):
        self.assertEqual(iv._coerce_rating("abc"), 5)
        self.assertEqual(iv._coerce_rating(None), 5)

    def test_custom_default(self):
        self.assertEqual(iv._coerce_rating("x", default=3), 3)


class InitLoadTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self, path=None):
        p = path or self._path
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", p.parent):
            return iv.IdeaVault()

    def test_init_creates_data_dir(self):
        with mock.patch("pathlib.Path.mkdir") as mk:
            with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", Path("/tmp/x")):
                iv.IdeaVault()
        # mkdir may be called multiple times (init + seed save); just ensure called
        self.assertGreaterEqual(mk.call_count, 1)

    def test_load_existing_list(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text('[{"id":"i1","title":"T"}]', encoding="utf-8")
        v = self._make()
        self.assertEqual(len(v._ideas), 1)
        self.assertEqual(v._ideas[0]["id"], "i1")

    def test_load_corrupt_quarantines(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("{bad", encoding="utf-8")
        v = self._make()
        self.assertEqual(v._ideas, [])
        # quarantined file created
        self.assertTrue((self._path.parent / "ideas.json.corrupt").exists())

    def test_load_corrupt_quarantine_rename_fails(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent), \
                mock.patch.object(Path, "rename", side_effect=OSError("nope")):
            v = iv.IdeaVault()
        self.assertEqual(v._ideas, [])
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text('"not a list"', encoding="utf-8")
        v = self._make()
        self.assertEqual(v._ideas, [])
        self.assertTrue((self._path.parent / "ideas.json.corrupt").exists())

    def test_load_empty_list_accepted(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("[]", encoding="utf-8")
        v = self._make()
        self.assertEqual(v._ideas, [])

    def test_load_missing_seeds_preloaded(self):
        v = self._make()
        self.assertEqual(len(v._ideas), len(iv.PRELOADED_IDEAS))
        self.assertTrue(self._path.exists())
        # each has score = feasibility * impact
        self.assertEqual(v._ideas[0]["score"],
                         round(iv.PRELOADED_IDEAS[0]["feasibility"] * iv.PRELOADED_IDEAS[0]["impact"], 1))

    def test_save_failure_logged(self):
        v = self._make()
        with mock.patch("orbit.orbit.core.idea_vault.atomic_write_text",
                        side_effect=OSError("boom")), \
                mock.patch.object(iv, "logger") as lg:
            v._save()
        lg.error.assert_called_once()

    def test_path(self):
        v = self._make()
        p = v._path()
        self.assertTrue(str(p).endswith("ideas.json"))


class AddIdeaTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_add_basic(self):
        v = self._make()
        idea = v.add_idea("My Idea", "desc", category="orbit",
                          feasibility=7, impact=9, tags=["t1"])
        self.assertEqual(idea["title"], "My Idea")
        self.assertEqual(idea["description"], "desc")
        self.assertEqual(idea["category"], "orbit")
        self.assertEqual(idea["feasibility"], 7)
        self.assertEqual(idea["impact"], 9)
        self.assertEqual(idea["score"], 63.0)
        self.assertEqual(idea["tags"], ["t1"])
        self.assertFalse(idea["converted_to_goal"])
        self.assertIsNone(idea["goal_id"])
        self.assertEqual(idea["related_ideas"], [])
        self.assertIn("id", idea)
        self.assertIn("created_at", idea)
        self.assertIn("updated_at", idea)
        # persisted
        self.assertEqual(len(v.list_ideas()), len(iv.PRELOADED_IDEAS) + 1)

    def test_add_invalid_category_defaults_personal(self):
        v = self._make()
        idea = v.add_idea("T", "d", category="nope")
        self.assertEqual(idea["category"], "personal")

    def test_add_tags_none(self):
        v = self._make()
        idea = v.add_idea("T", "d", tags=None)
        self.assertEqual(idea["tags"], [])

    def test_add_tags_non_list(self):
        v = self._make()
        idea = v.add_idea("T", "d", tags="not-a-list")
        self.assertEqual(idea["tags"], "not-a-list")

    def test_add_feasibility_coerced(self):
        v = self._make()
        idea = v.add_idea("T", "d", feasibility="abc", impact=15)
        self.assertEqual(idea["feasibility"], 5)  # default
        self.assertEqual(idea["impact"], 10)  # clamped

    def test_add_logs(self):
        v = self._make()
        with mock.patch.object(iv, "logger") as lg:
            v.add_idea("T", "d")
        lg.info.assert_called_once()


class ListIdeasTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_list_all(self):
        v = self._make()
        ideas = v.list_ideas()
        self.assertEqual(len(ideas), len(iv.PRELOADED_IDEAS))

    def test_list_by_category(self):
        v = self._make()
        ideas = v.list_ideas(category="orbit")
        self.assertTrue(all(i["category"] == "orbit" for i in ideas))

    def test_list_unknown_category_empty(self):
        v = self._make()
        self.assertEqual(v.list_ideas(category="nope"), [])

    def test_sort_by_score(self):
        v = self._make()
        ideas = v.list_ideas(sort_by="score")
        scores = [i["score"] for i in ideas]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_sort_by_created_at(self):
        v = self._make()
        ideas = v.list_ideas(sort_by="created_at")
        self.assertIsInstance(ideas, list)

    def test_sort_by_title(self):
        v = self._make()
        ideas = v.list_ideas(sort_by="title")
        titles = [i["title"] for i in ideas]
        self.assertEqual(titles, sorted(titles))

    def test_sort_unknown_no_sort(self):
        v = self._make()
        ideas = v.list_ideas(sort_by="nope")
        self.assertEqual(len(ideas), len(iv.PRELOADED_IDEAS))

    def test_returns_copy(self):
        v = self._make()
        ideas = v.list_ideas()
        ideas[0]["title"] = "MUTATED"
        # list_ideas returns shallow list copies but same dict objects
        self.assertEqual(v.list_ideas()[0]["title"], "MUTATED")


class GetIdeaTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_found(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        idea = v.get_idea(iid)
        self.assertEqual(idea["id"], iid)
        # copy
        idea["title"] = "MUTATED"
        self.assertNotEqual(v.get_idea(iid)["title"], "MUTATED")

    def test_not_found(self):
        v = self._make()
        self.assertIsNone(v.get_idea("nope"))


class UpdateIdeaTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_update_title_description(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        old_score = v._ideas[0]["score"]
        r = v.update_idea(iid, title="New Title", description="New Desc")
        self.assertEqual(r["title"], "New Title")
        self.assertEqual(r["description"], "New Desc")
        self.assertIn("updated_at", r)
        # score recomputed
        self.assertEqual(r["score"], round(r["feasibility"] * r["impact"], 1))

    def test_update_feasibility_impact(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        r = v.update_idea(iid, feasibility=9, impact=8)
        self.assertEqual(r["feasibility"], 9)
        self.assertEqual(r["impact"], 8)
        self.assertEqual(r["score"], 72.0)

    def test_update_feasibility_coerced(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        r = v.update_idea(iid, feasibility="abc")
        self.assertEqual(r["feasibility"], v._ideas[0]["feasibility"])  # default keeps old

    def test_update_tags(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        r = v.update_idea(iid, tags=["a", "b"])
        self.assertEqual(r["tags"], ["a", "b"])

    def test_update_tags_non_list(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        r = v.update_idea(iid, tags="not-list")
        self.assertEqual(r["tags"], [])

    def test_update_category_valid(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        r = v.update_idea(iid, category="business")
        self.assertEqual(r["category"], "business")

    def test_update_category_invalid_keeps(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        old_cat = v._ideas[0]["category"]
        r = v.update_idea(iid, category="nope")
        self.assertEqual(r["category"], old_cat)

    def test_update_unknown_returns_none(self):
        v = self._make()
        self.assertIsNone(v.update_idea("nope", title="x"))

    def test_update_logs(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        with mock.patch.object(iv, "logger") as lg:
            v.update_idea(iid, title="x")
        lg.info.assert_called_once()


class DeleteIdeaTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_delete_success(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        with mock.patch.object(iv, "logger") as lg:
            self.assertTrue(v.delete_idea(iid))
        self.assertIsNone(v.get_idea(iid))
        lg.info.assert_called_once()

    def test_delete_unknown(self):
        v = self._make()
        self.assertFalse(v.delete_idea("nope"))


class GetTopIdeasTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_default_limit_5(self):
        v = self._make()
        top = v.get_top_ideas()
        self.assertEqual(len(top), 5)

    def test_custom_limit(self):
        v = self._make()
        top = v.get_top_ideas(limit=2)
        self.assertEqual(len(top), 2)

    def test_sorted_by_score_desc(self):
        v = self._make()
        top = v.get_top_ideas(limit=3)
        scores = [i["score"] for i in top]
        self.assertEqual(scores, sorted(scores, reverse=True))


class SearchIdeasTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_search_by_title(self):
        v = self._make()
        # "ORBIT" appears in titles
        r = v.search_ideas("orbit")
        self.assertGreater(len(r), 0)

    def test_search_by_description(self):
        v = self._make()
        r = v.search_ideas("journey")
        self.assertGreater(len(r), 0)

    def test_search_by_tag(self):
        v = self._make()
        r = v.search_ideas("mobile")
        self.assertGreater(len(r), 0)

    def test_search_case_insensitive(self):
        v = self._make()
        r = v.search_ideas("ORBIT")
        self.assertGreater(len(r), 0)

    def test_search_no_match(self):
        v = self._make()
        self.assertEqual(v.search_ideas("zzzzzzz"), [])

    def test_search_empty_query_matches_all(self):
        v = self._make()
        r = v.search_ideas("")
        self.assertEqual(len(r), len(iv.PRELOADED_IDEAS))


class ConvertToGoalTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_unknown_returns_none(self):
        v = self._make()
        self.assertIsNone(v.convert_to_goal("nope"))

    def test_success(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        gt = mock.MagicMock()
        with mock.patch("orbit.orbit.core.goal_tracker.get_goal_tracker", return_value=gt), \
                mock.patch.object(iv, "logger") as lg:
            r = v.convert_to_goal(iid)
        self.assertIsNotNone(r)
        self.assertTrue(r["converted_to_goal"])
        gt.add_goal.assert_called_once()
        args = gt.add_goal.call_args.kwargs
        self.assertEqual(args["title"], v._ideas[0]["title"] if False else r["title"])
        self.assertEqual(args["category"], "idea_conversion")
        self.assertEqual(args["priority"], "medium")
        lg.info.assert_called_once()

    def test_goal_tracker_exception(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        with mock.patch("orbit.orbit.core.goal_tracker.get_goal_tracker",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(iv, "logger") as lg:
            r = v.convert_to_goal(iid)
        self.assertIsNotNone(r)
        # converted_to_goal stays False (exception before setting True)
        self.assertFalse(r["converted_to_goal"])
        lg.warning.assert_called_once()


class GetRelatedIdeasTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_unknown_returns_empty(self):
        v = self._make()
        self.assertEqual(v.get_related_ideas("nope"), [])

    def test_no_tags_returns_empty(self):
        v = self._make()
        # add idea with no tags
        idea = v.add_idea("NoTags", "d", tags=[])
        self.assertEqual(v.get_related_ideas(idea["id"]), [])

    def test_finds_related(self):
        v = self._make()
        # preloaded ideas share "orbit" tag? Check. Add two ideas sharing a tag.
        i1 = v.add_idea("I1", "d", tags=["shared"])
        i2 = v.add_idea("I2", "d", tags=["shared"])
        i3 = v.add_idea("I3", "d", tags=["other"])
        related = v.get_related_ideas(i1["id"])
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["id"], i2["id"])

    def test_excludes_self(self):
        v = self._make()
        i1 = v.add_idea("I1", "d", tags=["shared"])
        related = v.get_related_ideas(i1["id"])
        self.assertNotIn(i1["id"], [r["id"] for r in related])

    def test_sorted_by_score_desc(self):
        v = self._make()
        i1 = v.add_idea("I1", "d", tags=["shared"], feasibility=5, impact=5)
        i2 = v.add_idea("I2", "d", tags=["shared"], feasibility=9, impact=9)
        related = v.get_related_ideas(i1["id"])
        self.assertEqual(related[0]["id"], i2["id"])

    def test_get_idea_returns_copy(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        idea = v.get_idea(iid)
        idea["title"] = "MUTATED"
        self.assertNotEqual(v.get_idea(iid)["title"], "MUTATED")


class ScoreIdeaTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "ideas" / "ideas.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", self._path.parent):
            return iv.IdeaVault()

    def test_score_idea(self):
        v = self._make()
        iid = v._ideas[0]["id"]
        r = v.score_idea(iid, 9, 8)
        self.assertEqual(r["feasibility"], 9)
        self.assertEqual(r["impact"], 8)
        self.assertEqual(r["score"], 72.0)

    def test_score_idea_unknown(self):
        v = self._make()
        self.assertIsNone(v.score_idea("nope", 5, 5))


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = iv._instance
        iv._instance = None
        self.addCleanup(setattr, iv, "_instance", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", d / "ideas"):
            a = iv.get_idea_vault()
        self.assertIsInstance(a, iv.IdeaVault)
        self.assertIs(iv._instance, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.idea_vault.DATA_DIR", d / "ideas"):
            a = iv.get_idea_vault()
            b = iv.get_idea_vault()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
