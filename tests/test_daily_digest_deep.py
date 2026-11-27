"""Deep tests for orbit/orbit/core/daily_digest.py (Loop 15/1)."""

import json
import threading
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

from orbit.orbit.core import daily_digest as dd


class InitTests(unittest.TestCase):
    def test_init_creates_data_dir(self):
        with mock.patch("pathlib.Path.mkdir") as mk:
            d = dd.DailyDigest()
        mk.assert_called_once_with(parents=True, exist_ok=True)
        self.assertTrue(hasattr(d, "_lock"))


class DigestPathTests(unittest.TestCase):
    def test_default_today(self):
        d = dd.DailyDigest.__new__(dd.DailyDigest)
        p = d._digest_path()
        self.assertTrue(str(p).endswith(f"{date.today().isoformat()}.json"))

    def test_specific_day(self):
        d = dd.DailyDigest.__new__(dd.DailyDigest)
        p = d._digest_path(date(2026, 1, 5))
        self.assertTrue(str(p).endswith("2026-01-05.json"))


class LoadDigestTests(unittest.TestCase):
    def setUp(self):
        self.d = dd.DailyDigest.__new__(dd.DailyDigest)
        self.d._lock = threading.Lock()

    def test_load_missing(self):
        with mock.patch.object(self.d, "_digest_path") as dp:
            dp.return_value = Path("/tmp/nope.json")
            # exists False
            p = Path("/tmp/nope.json")
            with mock.patch.object(Path, "exists", return_value=False):
                self.assertIsNone(self.d._load_digest(date(2026, 1, 1)))

    def test_load_valid(self):
        p = Path("/tmp/d.json")
        with mock.patch.object(self.d, "_digest_path", return_value=p), \
                mock.patch.object(Path, "exists", return_value=True), \
                mock.patch.object(Path, "read_text", return_value='{"a":1}'):
            self.assertEqual(self.d._load_digest(date(2026, 1, 1)), {"a": 1})

    def test_load_corrupt(self):
        p = Path("/tmp/d.json")
        with mock.patch.object(self.d, "_digest_path", return_value=p), \
                mock.patch.object(Path, "exists", return_value=True), \
                mock.patch.object(Path, "read_text", return_value="{bad"):
            self.assertIsNone(self.d._load_digest(date(2026, 1, 1)))


class SaveDigestTests(unittest.TestCase):
    def setUp(self):
        self.d = dd.DailyDigest.__new__(dd.DailyDigest)
        self.d._lock = threading.Lock()

    def test_save_success(self):
        p = Path("/tmp/d.json")
        tmp = mock.MagicMock()
        with mock.patch.object(self.d, "_digest_path", return_value=p), \
                mock.patch.object(Path, "with_name", return_value=tmp):
            ok = self.d._save_digest({"a": 1})
        # _save_digest returns None on success
        self.assertIsNone(ok)
        tmp.write_text.assert_called_once()
        tmp.replace.assert_called_once_with(p)

    def test_save_failure(self):
        p = Path("/tmp/d.json")
        tmp = mock.MagicMock()
        tmp.write_text.side_effect = OSError("boom")
        with mock.patch.object(self.d, "_digest_path", return_value=p), \
                mock.patch.object(Path, "with_name", return_value=tmp), \
                mock.patch.object(dd, "logger") as lg:
            ok = self.d._save_digest({"a": 1})
        self.assertFalse(ok)
        lg.error.assert_called_once()


class GatherTests(unittest.TestCase):
    def setUp(self):
        self.d = dd.DailyDigest.__new__(dd.DailyDigest)
        self.d._lock = threading.Lock()

    def test_gather_agent_activity_success(self):
        pool = mock.MagicMock()
        pool.get_stats.return_value = {"total_memories": 5, "by_agent": {"a": 1, "b": 2}}
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory", return_value=pool):
            r = self.d._gather_agent_activity()
        self.assertEqual(r, {"total_actions": 5, "agents_used": ["a", "b"]})

    def test_gather_agent_activity_exception(self):
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory", side_effect=RuntimeError("boom")), \
                mock.patch.object(dd, "logger") as lg:
            r = self.d._gather_agent_activity()
        self.assertEqual(r, {"total_actions": 0, "agents_used": []})
        lg.debug.assert_called_once()

    def test_gather_goal_progress_success(self):
        tracker = mock.MagicMock()
        tracker.get_all.return_value = [{"title": "G1", "progress": 30},
                                       {"title": "G2", "progress": 80}]
        with mock.patch("orbit.orbit.core.goal_tracker.get_goal_tracker", return_value=tracker):
            r = self.d._gather_goal_progress()
        self.assertEqual(r, [{"title": "G1", "progress": 30},
                             {"title": "G2", "progress": 80}])

    def test_gather_goal_progress_exception(self):
        with mock.patch("orbit.orbit.core.goal_tracker.get_goal_tracker", side_effect=RuntimeError("boom")), \
                mock.patch.object(dd, "logger") as lg:
            r = self.d._gather_goal_progress()
        self.assertEqual(r, [])
        lg.debug.assert_called_once()

    def test_gather_tech_scout_list(self):
        scout = mock.MagicMock()
        scout.get_latest.return_value = [{"a": 1}, {"b": 2}, {"c": 3},
                                        {"d": 4}, {"e": 5}, {"f": 6}]
        with mock.patch("orbit.orbit.core.tech_scout.get_scout", return_value=scout):
            r = self.d._gather_tech_scout()
        self.assertEqual(len(r), 5)

    def test_gather_tech_scout_non_list(self):
        scout = mock.MagicMock()
        scout.get_latest.return_value = "not a list"
        with mock.patch("orbit.orbit.core.tech_scout.get_scout", return_value=scout):
            r = self.d._gather_tech_scout()
        self.assertEqual(r, [])

    def test_gather_tech_scout_exception(self):
        with mock.patch("orbit.orbit.core.tech_scout.get_scout", side_effect=RuntimeError("boom")), \
                mock.patch.object(dd, "logger") as lg:
            r = self.d._gather_tech_scout()
        self.assertEqual(r, [])
        lg.debug.assert_called_once()

    def test_gather_lessons_success(self):
        kb = mock.MagicMock()
        kb.get_all.return_value = [{"title": "L1"}, {"title": "L2"}]
        with mock.patch("orbit.orbit.core.knowledge_base.get_knowledge_base", return_value=kb):
            r = self.d._gather_lessons()
        self.assertEqual(r, ["L1", "L2"])

    def test_gather_lessons_exception(self):
        with mock.patch("orbit.orbit.core.knowledge_base.get_knowledge_base", side_effect=RuntimeError("boom")), \
                mock.patch.object(dd, "logger") as lg:
            r = self.d._gather_lessons()
        self.assertEqual(r, [])
        lg.debug.assert_called_once()


class GenerateDigestTests(unittest.TestCase):
    def setUp(self):
        self.d = dd.DailyDigest.__new__(dd.DailyDigest)
        self.d._lock = threading.Lock()
        # patch gather methods
        self.d._gather_agent_activity = mock.MagicMock(return_value={"total_actions": 0, "agents_used": []})
        self.d._gather_goal_progress = mock.MagicMock(return_value=[
            {"title": "G1", "progress": 30}, {"title": "G2", "progress": 80}])
        self.d._gather_tech_scout = mock.MagicMock(return_value=[])
        self.d._gather_lessons = mock.MagicMock(return_value=[])
        self.d._save_digest = mock.MagicMock(return_value=None)

    def test_generates_with_suggestions(self):
        with mock.patch.object(dd, "logger") as lg:
            d = self.d.generate_digest()
        self.assertEqual(d["date"], date.today().isoformat())
        self.assertIn("generated_at", d)
        self.assertEqual(d["tomorrows_suggestions"],
                         ["Focus on: G1 (only 30% done)"])
        self.d._save_digest.assert_called_once_with(d)
        lg.info.assert_called_once()

    def test_all_goals_on_track(self):
        self.d._gather_goal_progress = mock.MagicMock(return_value=[
            {"title": "G1", "progress": 80}])
        d = self.d.generate_digest()
        self.assertEqual(d["tomorrows_suggestions"],
                         ["All goals on track — keep pushing!"])

    def test_coerce_float_handles_string(self):
        self.d._gather_goal_progress = mock.MagicMock(return_value=[
            {"title": "G1", "progress": "40"}])
        d = self.d.generate_digest()
        self.assertEqual(d["tomorrows_suggestions"],
                         ["Focus on: G1 (only 40% done)"])

    def test_empty_goals(self):
        self.d._gather_goal_progress = mock.MagicMock(return_value=[])
        d = self.d.generate_digest()
        self.assertEqual(d["tomorrows_suggestions"],
                         ["All goals on track — keep pushing!"])


class GetTodayDigestTests(unittest.TestCase):
    def setUp(self):
        self.d = dd.DailyDigest.__new__(dd.DailyDigest)
        self.d._lock = threading.Lock()

    def test_existing_returned(self):
        with mock.patch.object(self.d, "_load_digest", return_value={"cached": True}), \
                mock.patch.object(self.d, "generate_digest") as gd:
            r = self.d.get_today_digest()
        self.assertEqual(r, {"cached": True})
        gd.assert_not_called()

    def test_none_generates(self):
        with mock.patch.object(self.d, "_load_digest", return_value=None), \
                mock.patch.object(self.d, "generate_digest", return_value={"fresh": True}) as gd:
            r = self.d.get_today_digest()
        self.assertEqual(r, {"fresh": True})
        gd.assert_called_once()


class GetHistoryTests(unittest.TestCase):
    def setUp(self):
        self.d = dd.DailyDigest.__new__(dd.DailyDigest)
        self.d._lock = threading.Lock()

    def test_reads_files(self):
        import tempfile, os
        d = tempfile.mkdtemp()
        p1 = Path(d) / "a.json"
        p2 = Path(d) / "b.json"
        p1.write_text('{"a":1}', encoding="utf-8")
        p2.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.daily_digest.DATA_DIR") as dd_dir:
            dd_dir.glob.return_value = [p1, p2]
            r = self.d.get_history(5)
        self.assertEqual(r, [{"a": 1}])

    def test_empty_dir(self):
        with mock.patch("orbit.orbit.core.daily_digest.DATA_DIR") as dd_dir:
            dd_dir.glob.return_value = []
            self.assertEqual(self.d.get_history(), [])

    def test_limit(self):
        import tempfile
        d = tempfile.mkdtemp()
        paths = []
        for i in range(10):
            p = Path(d) / f"{i}.json"
            p.write_text('{"x":1}', encoding="utf-8")
            paths.append(p)
        with mock.patch("orbit.orbit.core.daily_digest.DATA_DIR") as dd_dir:
            dd_dir.glob.return_value = paths
            r = self.d.get_history(3)
        self.assertEqual(len(r), 3)


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = dd._instance
        dd._instance = None
        self.addCleanup(setattr, dd, "_instance", self._saved)

    def test_creates(self):
        with mock.patch("orbit.orbit.core.daily_digest.DATA_DIR") as dd_dir:
            dd_dir.mkdir = mock.MagicMock()
            a = dd.get_daily_digest()
        self.assertIsInstance(a, dd.DailyDigest)
        self.assertIs(dd._instance, a)

    def test_reuses(self):
        with mock.patch("orbit.orbit.core.daily_digest.DATA_DIR") as dd_dir:
            dd_dir.mkdir = mock.MagicMock()
            a = dd.get_daily_digest()
            b = dd.get_daily_digest()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
