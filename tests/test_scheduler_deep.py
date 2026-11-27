"""Deep tests for orbit/orbit/core/scheduler.py (Loop 19/5)."""

import json
import os
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit.core import scheduler as sch


class ScheduleTypeTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(sch.ScheduleType.ONCE, "once")
        self.assertEqual(sch.ScheduleType.DAILY, "daily")
        self.assertEqual(sch.ScheduleType.WEEKLY, "weekly")
        self.assertEqual(sch.ScheduleType.MONTHLY, "monthly")
        self.assertEqual(sch.ScheduleType.HOURLY, "hourly")
        self.assertEqual(sch.ScheduleType.INTERVAL, "interval")


class ScheduledTaskTests(unittest.TestCase):
    def test_defaults(self):
        t = sch.ScheduledTask("id1", "name", "action", "once", {})
        self.assertEqual(t.task_id, "id1")
        self.assertEqual(t.name, "name")
        self.assertEqual(t.action, "action")
        self.assertEqual(t.schedule_type, "once")
        self.assertEqual(t.schedule_config, {})
        self.assertEqual(t.parameters, {})
        self.assertTrue(t.enabled)
        self.assertIsNone(t.last_run)
        self.assertIsNone(t.next_run)
        self.assertEqual(t.run_count, 0)
        self.assertIsNone(t.last_status)
        self.assertTrue(t.created_at)


class InitLoadSaveTests(unittest.TestCase):
    def _tmp_path(self):
        import tempfile
        d = tempfile.mkdtemp()
        return str(Path(d) / "tasks.json")

    def test_init_creates_storage_dir(self):
        p = self._tmp_path()
        s = sch.ORBITcheduler(storage_file=p)
        self.assertTrue(Path(p).parent.exists())
        s.stop()

    def test_load_missing(self):
        p = self._tmp_path()
        s = sch.ORBITcheduler(storage_file=p)
        self.assertEqual(s.tasks, {})
        s.stop()

    def test_load_existing(self):
        p = self._tmp_path()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps({"t1": {"task_id": "t1", "name": "n"}}),
                           encoding="utf-8")
        s = sch.ORBITcheduler(storage_file=p)
        self.assertEqual(s.tasks, {"t1": {"task_id": "t1", "name": "n"}})
        s.stop()

    def test_load_corrupt(self):
        p = self._tmp_path()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text("{bad", encoding="utf-8")
        s = sch.ORBITcheduler(storage_file=p)
        self.assertEqual(s.tasks, {})
        s.stop()

    def test_load_non_dict(self):
        p = self._tmp_path()
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text("[1,2]", encoding="utf-8")
        s = sch.ORBITcheduler(storage_file=p)
        self.assertEqual(s.tasks, {})
        s.stop()

    def test_save_success(self):
        p = self._tmp_path()
        s = sch.ORBITcheduler(storage_file=p)
        s.tasks["t1"] = {"task_id": "t1"}
        s._save_tasks()
        self.assertTrue(Path(p).exists())
        data = json.loads(Path(p).read_text("utf-8"))
        self.assertEqual(data, {"t1": {"task_id": "t1"}})
        s.stop()

    def test_save_failure_logged(self):
        p = self._tmp_path()
        s = sch.ORBITcheduler(storage_file=p)
        s.tasks["t1"] = {"task_id": "t1"}
        with mock.patch("builtins.open", side_effect=OSError("boom")), \
                mock.patch.object(sch, "logger") as lg:
            s._save_tasks()
        lg.error.assert_called_once()


class RegisterHandlerTests(unittest.TestCase):
    def test_register(self):
        p = self._tmp_path() if False else None
        import tempfile
        p = str(Path(tempfile.mkdtemp()) / "t.json")
        s = sch.ORBITcheduler(storage_file=p)
        cb = lambda x: x
        s.register_handler("act", cb)
        self.assertIs(s.handlers["act"], cb)
        s.stop()


class ScheduleTaskTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._p = str(Path(tempfile.mkdtemp()) / "t.json")
        self.s = sch.ORBITcheduler(storage_file=self._p)
        self.addCleanup(self.s.stop)

    def test_schedule_basic(self):
        tid = self.s.schedule_task("name", "action", "once", {"run_at": "2026-01-01"})
        self.assertTrue(tid.startswith("task_"))
        self.assertIn(tid, self.s.tasks)
        task = self.s.tasks[tid]
        self.assertEqual(task["name"], "name")
        self.assertEqual(task["action"], "action")
        self.assertEqual(task["schedule_type"], "once")
        self.assertEqual(task["schedule_config"], {"run_at": "2026-01-01"})
        self.assertEqual(task["parameters"], {})
        self.assertTrue(task["enabled"])
        self.assertEqual(task["run_count"], 0)
        self.assertIsNone(task["last_run"])
        self.assertIsNone(task["last_status"])
        self.assertIn("created_at", task)
        self.assertEqual(task["next_run"], "2026-01-01")

    def test_schedule_with_params(self):
        tid = self.s.schedule_task("n", "a", "interval", {"interval_seconds": 60},
                                   parameters={"x": 1}, enabled=False)
        task = self.s.tasks[tid]
        self.assertEqual(task["parameters"], {"x": 1})
        self.assertFalse(task["enabled"])

    def test_schedule_persisted(self):
        tid = self.s.schedule_task("n", "a", "once", {})
        data = json.loads(Path(self._p).read_text("utf-8"))
        self.assertIn(tid, data)


class CalculateNextRunTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._p = str(Path(tempfile.mkdtemp()) / "t.json")
        self.s = sch.ORBITcheduler(storage_file=self._p)
        self.addCleanup(self.s.stop)

    def _patch_now(self, dt):
        return mock.patch("orbit.orbit.core.scheduler.datetime", wraps=__import__("datetime").datetime)

    def test_once(self):
        r = self.s._calculate_next_run("once", {"run_at": "2026-05-01T10:00:00"})
        self.assertEqual(r, "2026-05-01T10:00:00")

    def test_once_default_now(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            dt.now.return_value.isoformat.return_value = "2026-01-01T00:00:00"
            r = self.s._calculate_next_run("once", {})
        self.assertEqual(r, "2026-01-01T00:00:00")

    def test_hourly(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 10, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("hourly", {})
        # now + 1 hour
        self.assertEqual(r, (now + timedelta(hours=1)).isoformat())

    def test_daily_future_today(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 8, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("daily", {"hour": 9, "minute": 30})
        self.assertEqual(r, now.replace(hour=9, minute=30, second=0).isoformat())

    def test_daily_past_today_rolls(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 10, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("daily", {"hour": 9, "minute": 0})
        expected = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0)
        self.assertEqual(r, expected.isoformat())

    def test_daily_defaults(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 8, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("daily", {})
        self.assertEqual(r, now.replace(hour=9, minute=0, second=0).isoformat())

    def test_weekly(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 8, 0)  # Thursday (weekday 3)
            dt.now.return_value = now
            # target weekday 0 (Monday), days_ahead = 0-3 = -3 -> +7 = 4
            r = self.s._calculate_next_run("weekly", {"weekday": 0, "hour": 9, "minute": 0})
        expected = (now + timedelta(days=4)).replace(hour=9, minute=0, second=0)
        self.assertEqual(r, expected.isoformat())

    def test_weekly_same_day_rolls_next_week(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 5, 8, 0)  # Monday (weekday 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("weekly", {"weekday": 0, "hour": 9, "minute": 0})
        # days_ahead = 0-0 = 0 -> <=0 -> +7 = 7
        expected = (now + timedelta(days=7)).replace(hour=9, minute=0, second=0)
        self.assertEqual(r, expected.isoformat())

    def test_weekly_defaults(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 8, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("weekly", {})
        self.assertIsInstance(r, str)

    def test_monthly_past_day_rolls_next_month(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 15, 8, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("monthly", {"day": 10, "hour": 9, "minute": 0})
        expected = now.replace(month=2, day=10, hour=9, minute=0, second=0)
        self.assertEqual(r, expected.isoformat())

    def test_monthly_past_day_december_rolls_year(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 12, 15, 8, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("monthly", {"day": 10, "hour": 9, "minute": 0})
        expected = now.replace(year=2027, month=1, day=10, hour=9, minute=0, second=0)
        self.assertEqual(r, expected.isoformat())

    def test_monthly_future_day_same_month(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 5, 8, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("monthly", {"day": 10, "hour": 9, "minute": 0})
        expected = now.replace(day=10, hour=9, minute=0, second=0)
        self.assertEqual(r, expected.isoformat())

    def test_monthly_defaults(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 5, 8, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("monthly", {})
        self.assertIsInstance(r, str)

    def test_interval(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 10, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("interval", {"interval_seconds": 120})
        self.assertEqual(r, (now + timedelta(seconds=120)).isoformat())

    def test_interval_default(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 10, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("interval", {})
        self.assertEqual(r, (now + timedelta(seconds=3600)).isoformat())

    def test_unknown_type_fallback(self):
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt:
            now = datetime(2026, 1, 1, 10, 0)
            dt.now.return_value = now
            r = self.s._calculate_next_run("nope", {})
        self.assertEqual(r, (now + timedelta(hours=1)).isoformat())


class EnableDisableDeleteTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._p = str(Path(tempfile.mkdtemp()) / "t.json")
        self.s = sch.ORBITcheduler(storage_file=self._p)
        self.addCleanup(self.s.stop)
        self.tid = self.s.schedule_task("n", "a", "once", {})

    def test_enable(self):
        self.s.disable_task(self.tid)
        self.assertTrue(self.s.enable_task(self.tid))
        self.assertTrue(self.s.tasks[self.tid]["enabled"])

    def test_enable_unknown(self):
        self.assertFalse(self.s.enable_task("nope"))

    def test_disable(self):
        self.assertTrue(self.s.disable_task(self.tid))
        self.assertFalse(self.s.tasks[self.tid]["enabled"])

    def test_disable_unknown(self):
        self.assertFalse(self.s.disable_task("nope"))

    def test_delete(self):
        self.assertTrue(self.s.delete_task(self.tid))
        self.assertNotIn(self.tid, self.s.tasks)

    def test_delete_unknown(self):
        self.assertFalse(self.s.delete_task("nope"))

    def test_delete_persisted(self):
        self.s.delete_task(self.tid)
        data = json.loads(Path(self._p).read_text("utf-8"))
        self.assertNotIn(self.tid, data)


class GetTaskListTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._p = str(Path(tempfile.mkdtemp()) / "t.json")
        self.s = sch.ORBITcheduler(storage_file=self._p)
        self.addCleanup(self.s.stop)
        self.t1 = self.s.schedule_task("b", "a", "once", {"run_at": "2026-01-02"})
        self.t2 = self.s.schedule_task("a", "a", "once", {"run_at": "2026-01-01"})
        self.s.disable_task(self.t2)

    def test_get_task(self):
        self.assertEqual(self.s.get_task(self.t1)["name"], "b")
        self.assertIsNone(self.s.get_task("nope"))

    def test_list_tasks_sorted(self):
        tasks = self.s.list_tasks()
        self.assertEqual(len(tasks), 2)
        # sorted by next_run
        self.assertEqual(tasks[0]["task_id"], self.t2)

    def test_list_tasks_enabled_only(self):
        tasks = self.s.list_tasks(enabled_only=True)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], self.t1)


class GetDueTasksTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._p = str(Path(tempfile.mkdtemp()) / "t.json")
        self.s = sch.ORBITcheduler(storage_file=self._p)
        self.addCleanup(self.s.stop)

    def test_due_task(self):
        tid = self.s.schedule_task("n", "a", "once", {"run_at": "2020-01-01"})
        due = self.s.get_due_tasks()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["task_id"], tid)

    def test_not_due(self):
        self.s.schedule_task("n", "a", "once", {"run_at": "2099-01-01"})
        self.assertEqual(self.s.get_due_tasks(), [])

    def test_disabled_not_due(self):
        tid = self.s.schedule_task("n", "a", "once", {"run_at": "2020-01-01"}, enabled=False)
        self.assertEqual(self.s.get_due_tasks(), [])

    def test_invalid_next_run_skipped(self):
        tid = self.s.schedule_task("n", "a", "once", {"run_at": "2020-01-01"})
        self.s.tasks[tid]["next_run"] = "not-a-date"
        self.assertEqual(self.s.get_due_tasks(), [])

    def test_missing_next_run_skipped(self):
        tid = self.s.schedule_task("n", "a", "once", {"run_at": "2020-01-01"})
        self.s.tasks[tid]["next_run"] = None
        self.assertEqual(self.s.get_due_tasks(), [])


class ExecuteTaskTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._p = str(Path(tempfile.mkdtemp()) / "t.json")
        self.s = sch.ORBITcheduler(storage_file=self._p)
        self.addCleanup(self.s.stop)
        self.tid = self.s.schedule_task("n", "a", "once", {"run_at": "2020-01-01"})

    def test_no_task_returns_false(self):
        self.assertFalse(self.s.execute_task("nope"))

    def test_no_action_returns_false(self):
        self.s.tasks[self.tid]["action"] = ""
        self.assertFalse(self.s.execute_task(self.tid))

    def test_no_handler_returns_false(self):
        self.assertFalse(self.s.execute_task(self.tid))

    def test_success(self):
        cb = mock.MagicMock()
        self.s.register_handler("a", cb)
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt, \
                mock.patch.object(self.s, "_save_tasks"):
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            ok = self.s.execute_task(self.tid)
        self.assertTrue(ok)
        cb.assert_called_once_with({})
        task = self.s.tasks[self.tid]
        self.assertEqual(task["last_run"], "2026-01-01T10:00:00")
        self.assertEqual(task["run_count"], 1)
        self.assertEqual(task["last_status"], "success")
        self.assertIsNotNone(task["next_run"])

    def test_success_with_params(self):
        self.s.tasks[self.tid]["parameters"] = {"x": 1}
        cb = mock.MagicMock()
        self.s.register_handler("a", cb)
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt, \
                mock.patch.object(self.s, "_save_tasks"):
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            self.s.execute_task(self.tid)
        cb.assert_called_once_with({"x": 1})

    def test_deleted_mid_run(self):
        cb = mock.MagicMock(side_effect=lambda p: self.s.delete_task(self.tid))
        self.s.register_handler("a", cb)
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt, \
                mock.patch.object(self.s, "_save_tasks"):
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            ok = self.s.execute_task(self.tid)
        self.assertTrue(ok)

    def test_exception(self):
        cb = mock.MagicMock(side_effect=RuntimeError("boom"))
        self.s.register_handler("a", cb)
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt, \
                mock.patch.object(self.s, "_save_tasks"):
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            ok = self.s.execute_task(self.tid)
        self.assertFalse(ok)
        task = self.s.tasks[self.tid]
        self.assertEqual(task["last_status"], "error: boom")
        self.assertEqual(task["run_count"], 0)

    def test_exception_task_deleted(self):
        cb = mock.MagicMock(side_effect=RuntimeError("boom"))

        def handler(p):
            self.s.delete_task(self.tid)
            raise RuntimeError("boom")

        self.s.register_handler("a", handler)
        with mock.patch("orbit.orbit.core.scheduler.datetime") as dt, \
                mock.patch.object(self.s, "_save_tasks"):
            dt.now.return_value.isoformat.return_value = "2026-01-01T10:00:00"
            ok = self.s.execute_task(self.tid)
        self.assertFalse(ok)


class StartStopTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._p = str(Path(tempfile.mkdtemp()) / "t.json")
        self.s = sch.ORBITcheduler(storage_file=self._p)
        self.addCleanup(self.s.stop)

    def test_start(self):
        with mock.patch.object(self.s, "_run_loop"):
            self.s.start()
        self.assertTrue(self.s.running)
        self.assertIsNotNone(self.s._thread)

    def test_start_noop_if_running(self):
        self.s.running = True
        self.s.start()
        self.assertIsNone(self.s._thread)

    def test_stop(self):
        self.s.running = True
        t = mock.MagicMock()
        self.s._thread = t
        self.s.stop()
        self.assertFalse(self.s.running)
        t.join.assert_called_once_with(timeout=5)

    def test_stop_no_thread(self):
        self.s.running = False
        self.s._thread = None
        self.s.stop()  # no crash

    def test_run_loop(self):
        self.s.running = True
        call_count = {"n": 0}

        def get_due():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                self.s.running = False
            return []

        with mock.patch.object(self.s, "get_due_tasks", side_effect=get_due), \
                mock.patch("time.sleep"):
            self.s._run_loop()
        self.assertFalse(self.s.running)

    def test_run_loop_executes_due(self):
        tid = self.s.schedule_task("n", "a", "once", {"run_at": "2020-01-01"})
        self.s.register_handler("a", mock.MagicMock())
        self.s.running = True
        call_count = {"n": 0}

        def get_due():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                self.s.running = False
                return [self.s.tasks[tid]]
            return []

        with mock.patch.object(self.s, "get_due_tasks", side_effect=get_due), \
                mock.patch("time.sleep"), \
                mock.patch.object(self.s, "execute_task") as ex:
            self.s._run_loop()
        ex.assert_called_once_with(tid)

    def test_run_loop_exception(self):
        self.s.running = True
        call_count = {"n": 0}

        def get_due():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                self.s.running = False
            raise RuntimeError("boom")

        with mock.patch.object(self.s, "get_due_tasks", side_effect=get_due), \
                mock.patch("time.sleep"), \
                mock.patch.object(sch, "logger") as lg:
            self.s._run_loop()
        lg.error.assert_called()


class GetStatisticsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._p = str(Path(tempfile.mkdtemp()) / "t.json")
        self.s = sch.ORBITcheduler(storage_file=self._p)
        self.addCleanup(self.s.stop)

    def test_empty(self):
        r = self.s.get_statistics()
        self.assertEqual(r, {"total_tasks": 0, "enabled_tasks": 0,
                             "total_runs": 0, "by_type": {}})

    def test_with_tasks(self):
        t1 = self.s.schedule_task("n1", "a", "once", {})
        t2 = self.s.schedule_task("n2", "a", "daily", {})
        self.s.disable_task(t2)
        # simulate run_count
        self.s.tasks[t1]["run_count"] = 3
        r = self.s.get_statistics()
        self.assertEqual(r["total_tasks"], 2)
        self.assertEqual(r["enabled_tasks"], 1)
        self.assertEqual(r["total_runs"], 3)
        self.assertEqual(r["by_type"], {"once": 1, "daily": 1})


class ModuleLevelTests(unittest.TestCase):
    def test_get_scheduler_singleton(self):
        sch._scheduler = None
        a = sch.get_scheduler()
        b = sch.get_scheduler()
        self.assertIs(a, b)
        sch._scheduler = None

    def test_schedule_task_module(self):
        sch._scheduler = None
        with mock.patch.object(sch, "get_scheduler") as gs:
            sched = mock.MagicMock()
            sched.schedule_task.return_value = "tid1"
            gs.return_value = sched
            r = sch.schedule_task("n", "a", "once", {}, {"x": 1}, False)
        self.assertEqual(r, "tid1")
        sched.schedule_task.assert_called_once_with("n", "a", "once", {}, {"x": 1}, False)
        sch._scheduler = None

    def test_get_due_tasks_module(self):
        sch._scheduler = None
        with mock.patch.object(sch, "get_scheduler") as gs:
            sched = mock.MagicMock()
            sched.get_due_tasks.return_value = [{"id": 1}]
            gs.return_value = sched
            r = sch.get_due_tasks()
        self.assertEqual(r, [{"id": 1}])
        sch._scheduler = None

    def test_list_tasks_module(self):
        sch._scheduler = None
        with mock.patch.object(sch, "get_scheduler") as gs:
            sched = mock.MagicMock()
            sched.list_tasks.return_value = [{"id": 1}]
            gs.return_value = sched
            r = sch.list_tasks(enabled_only=True)
        self.assertEqual(r, [{"id": 1}])
        sched.list_tasks.assert_called_once_with(True)
        sch._scheduler = None

    def test_start_scheduler_module(self):
        sch._scheduler = None
        with mock.patch.object(sch, "get_scheduler") as gs:
            sched = mock.MagicMock()
            gs.return_value = sched
            sch.start_scheduler()
        sched.start.assert_called_once()
        sch._scheduler = None

    def test_stop_scheduler_module(self):
        sch._scheduler = None
        with mock.patch.object(sch, "get_scheduler") as gs:
            sched = mock.MagicMock()
            gs.return_value = sched
            sch.stop_scheduler()
        sched.stop.assert_called_once()
        sch._scheduler = None


if __name__ == "__main__":
    unittest.main()
