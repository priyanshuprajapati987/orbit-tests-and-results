"""Deep tests for orbit/orbit/skill_library.py (Loop 21/3)."""

import json
import math
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit import skill_library as sl


class SkillStepSkillTests(unittest.TestCase):
    def test_skill_step_defaults(self):
        s = sl.SkillStep()
        self.assertEqual(s.order, 0)
        self.assertEqual(s.action, "")
        self.assertEqual(s.tool, "")
        self.assertEqual(s.params, {})
        self.assertEqual(s.description, "")

    def test_skill_defaults(self):
        s = sl.Skill()
        self.assertTrue(s.id)
        self.assertEqual(s.name, "")
        self.assertEqual(s.task_pattern, "")
        self.assertEqual(s.steps, [])
        self.assertEqual(s.tools_used, [])
        self.assertEqual(s.success_count, 0)
        self.assertEqual(s.fail_count, 0)
        self.assertEqual(s.avg_duration_ms, 0.0)
        self.assertEqual(s.tags, [])
        self.assertEqual(s.version, 1)
        self.assertTrue(s.created_at)
        self.assertTrue(s.last_used)


class InitLoadTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self, path=None):
        p = path or self._path
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir",
                        return_value=self._d):
            return sl.SkillLibrary(storage_file=str(p))

    def test_init_creates(self):
        lib = self._make()
        self.assertEqual(lib._skills, {})
        self.assertTrue(hasattr(lib, "_lock"))

    def test_load_existing(self):
        self._path.write_text(json.dumps({"skills": [
            {"id": "s1", "name": "n", "task_pattern": "t", "description": "d",
             "steps": [], "tools_used": [], "agent_id": "a", "success_count": 2,
             "fail_count": 1, "avg_duration_ms": 10.0, "tags": ["x"],
             "created_at": "2026-01-01", "last_used": "2026-01-02", "version": 2}]}),
            encoding="utf-8")
        lib = self._make()
        self.assertIn("s1", lib._skills)
        sk = lib._skills["s1"]
        self.assertEqual(sk.name, "n")
        self.assertEqual(sk.success_count, 2)
        self.assertEqual(sk.fail_count, 1)

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        lib = self._make()
        self.assertEqual(lib._skills, {})

    def test_load_missing(self):
        lib = self._make()
        self.assertEqual(lib._skills, {})

    def test_save_success(self):
        lib = self._make()
        lib._skills["s1"] = sl.Skill(id="s1", name="n")
        lib._save()
        self.assertTrue(self._path.exists())
        data = json.loads(self._path.read_text("utf-8"))
        self.assertEqual(len(data["skills"]), 1)
        self.assertIn("updated_at", data)

    def test_save_failure_logged(self):
        lib = self._make()
        with mock.patch.object(Path, "mkdir", side_effect=OSError("boom")), \
                mock.patch.object(sl, "logger") as lg:
            lib._save()
        lg.error.assert_called_once()


class GenerateNameTests(unittest.TestCase):
    def test_meaningful_words(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        lib._skills = {}
        name = lib._generate_name("send email to Priyanshu about meeting")
        self.assertEqual(name, "send_email_priyanshu_about_meeting")

    def test_all_stop_words(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        lib._skills = {}
        name = lib._generate_name("the a an to for")
        self.assertTrue(name.startswith("skill_"))

    def test_caps_5_words(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        lib._skills = {}
        name = lib._generate_name("one two three four five six seven")
        self.assertEqual(len(name.split("_")), 5)


class FindSimilarTests(unittest.TestCase):
    def test_no_skills(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        lib._skills = {}
        self.assertIsNone(lib._find_similar("task"))

    def test_no_match_below_threshold(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        lib._skills = {"s1": sl.Skill(id="s1", task_pattern="completely different words here")}
        self.assertIsNone(lib._find_similar("send email"))

    def test_match_above_threshold(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        lib._skills = {"s1": sl.Skill(id="s1", task_pattern="send email to priyanshu")}
        self.assertIsNotNone(lib._find_similar("send email to priyanshu about meeting"))

    def test_empty_pattern_skipped(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        lib._skills = {"s1": sl.Skill(id="s1", task_pattern="")}
        self.assertIsNone(lib._find_similar("task"))

    def test_best_score_selected(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        lib._skills = {
            "s1": sl.Skill(id="s1", task_pattern="send email to priyanshu"),
            "s2": sl.Skill(id="s2", task_pattern="send email to priyanshu about meeting today"),
        }
        # task closer to s2
        r = lib._find_similar("send email to priyanshu about meeting today now")
        self.assertEqual(r.id, "s2")

    def test_exact_threshold_boundary(self):
        lib = sl.SkillLibrary.__new__(sl.SkillLibrary)
        # task_words and pattern_words share exactly 0.5+? need > 0.5
        lib._skills = {"s1": sl.Skill(id="s1", task_pattern="a b c d")}
        # task = "a b c d e" -> intersection 4, union 5 -> score 0.8 > 0.5 -> match
        self.assertIsNotNone(lib._find_similar("a b c d e"))


class CrystallizeTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=self._d):
            return sl.SkillLibrary(storage_file=str(self._path))

    def test_create_new(self):
        lib = self._make()
        skill = lib.crystallize(task="send email", steps=[{"a": 1}], tools_used=["EmailTool"],
                                agent_id="TAS", success=True, tags=["email"],
                                duration_ms=100.0)
        self.assertTrue(skill.id)
        self.assertTrue(skill.name)
        self.assertEqual(skill.task_pattern, "send email")
        self.assertEqual(skill.steps, [{"a": 1}])
        self.assertEqual(skill.tools_used, ["EmailTool"])
        self.assertEqual(skill.agent_id, "TAS")
        self.assertEqual(skill.success_count, 1)
        self.assertEqual(skill.fail_count, 0)
        self.assertEqual(skill.avg_duration_ms, 100.0)
        self.assertEqual(skill.tags, ["email"])
        self.assertEqual(len(lib._skills), 1)
        # persisted
        self.assertTrue(self._path.exists())

    def test_create_failure(self):
        lib = self._make()
        skill = lib.crystallize(task="t", steps=[], success=False)
        self.assertEqual(skill.success_count, 0)
        self.assertEqual(skill.fail_count, 1)

    def test_create_default_tools_tags(self):
        lib = self._make()
        skill = lib.crystallize(task="t", steps=[])
        self.assertEqual(skill.tools_used, [])
        self.assertEqual(skill.tags, [])

    def test_create_logs(self):
        lib = self._make()
        with mock.patch.object(sl, "logger") as lg:
            lib.crystallize(task="t", steps=[])
        lg.info.assert_called_once()

    def test_update_existing(self):
        lib = self._make()
        s1 = lib.crystallize(task="send email to priyanshu", steps=[{"a": 1}],
                             tools_used=["EmailTool"], agent_id="TAS", success=True,
                             duration_ms=100.0)
        # similar task -> update
        s2 = lib.crystallize(task="send email to priyanshu about meeting",
                             steps=[{"b": 2}], tools_used=["CalendarTool"],
                             agent_id="TAS", success=True, duration_ms=200.0)
        self.assertIs(s2, s1)
        self.assertEqual(s1.success_count, 2)
        self.assertEqual(s1.fail_count, 0)
        self.assertEqual(s1.version, 2)
        self.assertEqual(s1.tools_used, ["EmailTool", "CalendarTool"])
        # avg duration updated
        self.assertAlmostEqual(s1.avg_duration_ms, 150.0, places=1)
        # last_used updated
        self.assertTrue(s1.last_used)

    def test_update_fail_increments_fail(self):
        lib = self._make()
        s1 = lib.crystallize(task="send email to priyanshu", steps=[], success=True)
        s2 = lib.crystallize(task="send email to priyanshu about meeting",
                             steps=[], success=False)
        self.assertEqual(s1.success_count, 1)
        self.assertEqual(s1.fail_count, 1)

    def test_update_avg_duration_first_total(self):
        # total=1 -> avg = duration_ms (the else branch)
        lib = self._make()
        s1 = lib.crystallize(task="send email to priyanshu", steps=[], success=True,
                             duration_ms=100.0)
        # force a second crystallize that updates but total becomes 2 -> first branch
        # To hit else branch (total=1 after increment? no, total = success+fail = 2)
        # The else branch is when total==1 which can't happen after increment (success_count becomes 2)
        # Actually: existing.success_count += 1 -> if was 1, now 2, total=2 -> first branch
        # So else branch only if success_count was 0 and success=True -> total=1
        lib2 = self._make()
        s = lib2.crystallize(task="t task pattern here", steps=[], success=False)  # success_count=0
        # now crystallize similar with success=True -> success_count becomes 1, total=1 -> else branch
        s2 = lib2.crystallize(task="t task pattern here now", steps=[], success=True,
                              duration_ms=50.0)
        self.assertEqual(s2.avg_duration_ms, 25.0)

    def test_update_no_tools_does_not_extend(self):
        lib = self._make()
        s1 = lib.crystallize(task="send email to priyanshu", steps=[], tools_used=["E"])
        s2 = lib.crystallize(task="send email to priyanshu about meeting",
                             steps=[], tools_used=None)
        self.assertEqual(s1.tools_used, ["E"])

    def test_update_logs(self):
        lib = self._make()
        lib.crystallize(task="send email to priyanshu", steps=[])
        with mock.patch.object(sl, "logger") as lg:
            lib.crystallize(task="send email to priyanshu about meeting", steps=[])
        lg.info.assert_called_once()


class RecallTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=self._d):
            return sl.SkillLibrary(storage_file=str(self._path))

    def test_recall_empty(self):
        lib = self._make()
        self.assertEqual(lib.recall("task"), [])

    def test_recall_match(self):
        lib = self._make()
        lib.crystallize(task="send email to priyanshu", steps=[{"a": 1}],
                        tools_used=["EmailTool"], agent_id="TAS", success=True)
        results = lib.recall("send email to priyanshu about meeting", limit=5)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertIn("id", r)
        self.assertIn("name", r)
        self.assertIn("task_pattern", r)
        self.assertIn("description", r)
        self.assertIn("steps", r)
        self.assertIn("tools_used", r)
        self.assertIn("success_rate", r)
        self.assertIn("uses", r)
        self.assertIn("relevance_score", r)
        self.assertIn("version", r)
        self.assertEqual(r["success_rate"], 1.0)
        self.assertEqual(r["uses"], 1)

    def test_recall_no_match_below_threshold(self):
        lib = self._make()
        s = lib.crystallize(task="send email to priyanshu", steps=[], success=False)
        s.last_used = "2020-01-01T00:00:00"
        results = lib.recall("completely unrelated task xyz")
        self.assertEqual(results, [])

    def test_recall_limit(self):
        lib = self._make()
        for i in range(10):
            lib.crystallize(task=f"send email to person{i}", steps=[])
        results = lib.recall("send email to person0", limit=3)
        self.assertLessEqual(len(results), 3)

    def test_recall_success_rate_zero(self):
        lib = self._make()
        s = lib.crystallize(task="send email to priyanshu", steps=[], success=False)
        results = lib.recall("send email to priyanshu about meeting")
        self.assertEqual(results[0]["success_rate"], 0.0)

    def test_recall_recency_boost_invalid_last_used(self):
        lib = self._make()
        s = lib.crystallize(task="send email to priyanshu", steps=[])
        s.last_used = "not-a-date"
        results = lib.recall("send email to priyanshu about meeting")
        # recency_boost = 0.5 fallback; still returns result
        self.assertEqual(len(results), 1)

    def test_recall_empty_pattern_skipped(self):
        lib = self._make()
        lib._skills["s1"] = sl.Skill(id="s1", task_pattern="")
        results = lib.recall("task")
        self.assertEqual(results, [])

    def test_recall_score_threshold_0_1(self):
        lib = self._make()
        s = lib.crystallize(task="send email to priyanshu", steps=[], success=False)
        s.last_used = "2020-01-01T00:00:00"
        results = lib.recall("zzzzz")
        self.assertEqual(results, [])


class GetSkillTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=self._d):
            return sl.SkillLibrary(storage_file=str(self._path))

    def test_found(self):
        lib = self._make()
        s = lib.crystallize(task="t", steps=[])
        r = lib.get_skill(s.id)
        self.assertEqual(r["id"], s.id)
        # asdict copy
        r["name"] = "MUTATED"
        self.assertNotEqual(lib.get_skill(s.id)["name"], "MUTATED")

    def test_not_found(self):
        lib = self._make()
        self.assertIsNone(lib.get_skill("nope"))


class ListSkillsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=self._d):
            return sl.SkillLibrary(storage_file=str(self._path))

    def test_empty(self):
        lib = self._make()
        self.assertEqual(lib.list_skills(), [])

    def test_list_all(self):
        lib = self._make()
        lib.crystallize(task="t1", steps=[])
        lib.crystallize(task="t2", steps=[])
        r = lib.list_skills()
        self.assertEqual(len(r), 2)

    def test_filter_by_tag(self):
        lib = self._make()
        lib.crystallize(task="t1", steps=[], tags=["email"])
        lib.crystallize(task="t2", steps=[], tags=["other"])
        r = lib.list_skills(tag="email")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["tags"], ["email"])

    def test_limit(self):
        lib = self._make()
        for i in range(10):
            lib.crystallize(task=f"t{i}", steps=[])
        r = lib.list_skills(limit=3)
        self.assertEqual(len(r), 3)

    def test_sorted_by_last_used_desc(self):
        lib = self._make()
        s1 = lib.crystallize(task="t1", steps=[])
        import time
        time.sleep(0.01)
        s2 = lib.crystallize(task="t2", steps=[])
        r = lib.list_skills()
        # most recent first
        self.assertEqual(r[0]["id"], s2.id)


class DeleteSkillTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=self._d):
            return sl.SkillLibrary(storage_file=str(self._path))

    def test_delete_success(self):
        lib = self._make()
        s = lib.crystallize(task="t", steps=[])
        self.assertTrue(lib.delete_skill(s.id))
        self.assertIsNone(lib.get_skill(s.id))

    def test_delete_missing(self):
        lib = self._make()
        self.assertFalse(lib.delete_skill("nope"))


class UpdateSkillTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=self._d):
            return sl.SkillLibrary(storage_file=str(self._path))

    def test_update_success(self):
        lib = self._make()
        s = lib.crystallize(task="t", steps=[])
        old_version = s.version
        old_last = s.last_used
        import time
        time.sleep(0.01)
        r = lib.update_skill(s.id, name="new name", foo="bar")
        self.assertEqual(r.name, "new name")
        # hasattr check: foo is not a field -> not set
        self.assertFalse(hasattr(r, "foo") and r.foo == "bar")
        self.assertEqual(r.version, old_version + 1)
        self.assertNotEqual(r.last_used, old_last)

    def test_update_unknown(self):
        lib = self._make()
        self.assertIsNone(lib.update_skill("nope", name="x"))

    def test_update_persists(self):
        lib = self._make()
        s = lib.crystallize(task="t", steps=[])
        lib.update_skill(s.id, name="updated")
        # reload
        lib2 = self._make()
        self.assertEqual(lib2.get_skill(s.id)["name"], "updated")


class StatsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=self._d):
            return sl.SkillLibrary(storage_file=str(self._path))

    def test_empty(self):
        lib = self._make()
        s = lib.stats()
        self.assertEqual(s["total_skills"], 0)
        self.assertEqual(s["total_uses"], 0)
        self.assertEqual(s["success_rate"], 0)
        self.assertEqual(s["by_agent"], {})
        self.assertEqual(s["by_tool"], {})

    def test_populated(self):
        lib = self._make()
        lib.crystallize(task="t1", steps=[], tools_used=["A", "B"],
                        agent_id="agent1", success=True)
        lib.crystallize(task="t2", steps=[], tools_used=["A"],
                        agent_id="agent2", success=False)
        s = lib.stats()
        self.assertEqual(s["total_skills"], 2)
        self.assertEqual(s["total_uses"], 2)
        self.assertEqual(s["success_rate"], 0.5)
        self.assertEqual(s["by_agent"], {"agent1": 1, "agent2": 1})
        self.assertEqual(s["by_tool"], {"A": 2, "B": 1})


class CrystallizeFromExecutionTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._path = self._d / "skill_library.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=self._d):
            return sl.SkillLibrary(storage_file=str(self._path))

    def test_bulk(self):
        lib = self._make()
        log = [
            {"task": "t1", "steps": [{"a": 1}], "tools_used": ["X"],
             "agent_id": "a", "success": True, "duration_ms": 50.0,
             "tags": ["tag1"]},
            {"task": "t2", "steps": [], "success": False},
        ]
        skills = lib.crystallize_from_execution(log)
        self.assertEqual(len(skills), 2)
        self.assertEqual(skills[0].task_pattern, "t1")
        self.assertEqual(skills[1].success_count, 0)
        self.assertEqual(skills[1].fail_count, 1)

    def test_empty_log(self):
        lib = self._make()
        self.assertEqual(lib.crystallize_from_execution([]), [])

    def test_defaults_in_entry(self):
        lib = self._make()
        skills = lib.crystallize_from_execution([{}])
        self.assertEqual(skills[0].task_pattern, "")
        self.assertEqual(skills[0].steps, [])
        self.assertEqual(skills[0].tools_used, [])
        self.assertEqual(skills[0].agent_id, "")
        self.assertTrue(skills[0].success_count == 1)  # success default True


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = sl._library
        sl._library = None
        self.addCleanup(setattr, sl, "_library", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=d):
            a = sl.get_skill_library()
        self.assertIsInstance(a, sl.SkillLibrary)
        self.assertIs(sl._library, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        with mock.patch("orbit.orbit.skill_library.orbit_data_dir", return_value=d):
            a = sl.get_skill_library()
            b = sl.get_skill_library()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
