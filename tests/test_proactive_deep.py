"""Deep tests for orbit/proactive.py — legacy outer proactive module (Loop 11/3).

The live implementation moved to orbit.orbit.core.proactive_assistant;
this outer module stays as a guarded shim and must keep working.

Covers every statement:
  * cooldown gate (reset_cooldown / can_proact incl. 180s boundary).
  * get_idle_message — usage_tracker None, empty stats, short session,
    long-session chai-break prompt.
  * get_session_message — no sessions, bad/missing start iso, elapsed
    windows (mins>=45 and mins%15<3), None-safe.
  * get_time_message — morning/night/afternoon windows incl. boundaries
    and mismatched time-of-day combos.
  * get_curious_message — always returns a rotating prompt.
  * get_due_task_message — scheduler None, no due tasks, with/without
    due time, corrupt due date, mark_notified side effect.
  * get_proactive_message — cooldown short-circuit, source priority
    order, state mutation (LAST_PROACTIVE / ACTIVE_PROACTIVE), all-None
    fallthrough.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

import orbit.proactive as pr


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved = (pr.LAST_PROACTIVE, pr.ACTIVE_PROACTIVE,
                       pr.usage_tracker, pr.scheduler, pr.TITLE)

        def _restore():
            (pr.LAST_PROACTIVE, pr.ACTIVE_PROACTIVE, pr.usage_tracker,
             pr.scheduler, pr.TITLE) = self._saved

        self.addCleanup(_restore)
        pr.LAST_PROACTIVE = None
        pr.ACTIVE_PROACTIVE = False


class CooldownTests(_Base):
    def test_fresh_state_can_proact(self):
        self.assertTrue(pr.can_proact())

    def test_reset_cooldown_blocks(self):
        pr.reset_cooldown()
        self.assertIsNotNone(pr.LAST_PROACTIVE)
        self.assertFalse(pr.can_proact())

    def test_cooldown_expires_after_180s(self):
        pr.LAST_PROACTIVE = datetime.now() - timedelta(seconds=181)
        self.assertTrue(pr.can_proact())

    def test_cooldown_boundary_180s(self):
        pr.LAST_PROACTIVE = datetime.now() - timedelta(seconds=180)
        self.assertTrue(pr.can_proact())
        pr.LAST_PROACTIVE = datetime.now() - timedelta(seconds=179)
        self.assertFalse(pr.can_proact())


class IdleMessageTests(_Base):
    def test_no_usage_tracker(self):
        pr.usage_tracker = None
        self.assertIsNone(pr.get_idle_message())

    def test_empty_stats(self):
        m = mock.MagicMock()
        m.get_today_stats.return_value = {}
        pr.usage_tracker = m
        self.assertIsNone(pr.get_idle_message())

    def test_none_stats(self):
        m = mock.MagicMock()
        m.get_today_stats.return_value = None
        pr.usage_tracker = m
        self.assertIsNone(pr.get_idle_message())

    def test_short_session_no_message(self):
        m = mock.MagicMock()
        m.get_today_stats.return_value = {"total_minutes": 30}
        pr.usage_tracker = m
        self.assertIsNone(pr.get_idle_message())

    def test_boundary_45_minutes(self):
        m = mock.MagicMock()
        m.get_today_stats.return_value = {"total_minutes": 45}
        pr.usage_tracker = m
        msg = pr.get_idle_message()
        self.assertIn("45", msg)
        self.assertIn(pr.TITLE, msg)
        self.assertIn("Chai break", msg)

    def test_long_session_message(self):
        m = mock.MagicMock()
        m.get_today_stats.return_value = {"total_minutes": 90.7}
        pr.usage_tracker = m
        msg = pr.get_idle_message()
        self.assertIn("91", msg)  # {mins:.0f} rounds


class SessionMessageTests(_Base):
    def _tracker(self, data):
        m = mock.MagicMock()
        m._load.return_value = data
        pr.usage_tracker = m
        return m

    def test_no_usage_tracker(self):
        pr.usage_tracker = None
        self.assertIsNone(pr.get_session_message())

    def test_no_sessions(self):
        self._tracker({"sessions": []})
        self.assertIsNone(pr.get_session_message())

    def test_sessions_key_missing(self):
        self._tracker({})
        self.assertIsNone(pr.get_session_message())

    def test_bad_start_iso(self):
        self._tracker({"sessions": [{"start": "not-a-date"}]})
        self.assertIsNone(pr.get_session_message())

    def test_missing_start_key(self):
        self._tracker({"sessions": [{"id": 1}]})
        self.assertIsNone(pr.get_session_message())

    def test_none_start(self):
        self._tracker({"sessions": [{"start": None}]})
        self.assertIsNone(pr.get_session_message())

    def test_recent_session_no_message(self):
        start = (datetime.now() - timedelta(minutes=10)).isoformat()
        self._tracker({"sessions": [{"start": start}]})
        self.assertIsNone(pr.get_session_message())

    def test_46_minute_session_message(self):
        # 46 % 15 = 1 < 3 -> inside the notify window
        start = (datetime.now() - timedelta(minutes=46)).isoformat()
        self._tracker({"sessions": [{"start": start}]})
        msg = pr.get_session_message()
        self.assertIn("46 minutes", msg)
        self.assertIn(pr.TITLE, msg)

    def test_48_minute_session_out_of_window(self):
        # 48 % 15 = 3 -> outside the <3 window
        start = (datetime.now() - timedelta(minutes=48)).isoformat()
        self._tracker({"sessions": [{"start": start}]})
        self.assertIsNone(pr.get_session_message())


class TimeMessageTests(_Base):
    def _time_msg(self, tod, hour):
        m = mock.MagicMock()
        m.get_time_of_day.return_value = tod
        pr.usage_tracker = m
        with mock.patch.object(pr, "datetime") as mdt, \
                mock.patch.object(pr, "random") as mrand:
            mdt.now.return_value = datetime(2026, 1, 1, hour, 0)
            mrand.choice.side_effect = lambda msgs: msgs[0]
            return pr.get_time_message()

    def test_no_usage_tracker(self):
        pr.usage_tracker = None
        self.assertIsNone(pr.get_time_message())

    def test_morning_window(self):
        msg = self._time_msg("morning", 8)
        self.assertEqual(msg,
                         f"🌅 Subah subah! Aaj ka plan kya hai {pr.TITLE}?")

    def test_morning_boundary_hour_10(self):
        self.assertIsNone(self._time_msg("morning", 10))

    def test_night_window(self):
        msg = self._time_msg("night", 23)
        self.assertEqual(
            msg, f"🌙 {pr.TITLE}, raat bahot ho gayi. Sone ka time nahi?")

    def test_night_boundary_hour_21(self):
        self.assertIsNone(self._time_msg("night", 21))

    def test_afternoon_window_start(self):
        msg = self._time_msg("afternoon", 13)
        self.assertEqual(msg, f"🍽 {pr.TITLE}, khana kha liya?")

    def test_afternoon_window_end(self):
        msg = self._time_msg("afternoon", 15)
        self.assertEqual(msg, f"🍽 {pr.TITLE}, khana kha liya?")

    def test_afternoon_out_of_window(self):
        self.assertIsNone(self._time_msg("afternoon", 16))
        self.assertIsNone(self._time_msg("afternoon", 12))

    def test_mismatched_tod_and_hour(self):
        self.assertIsNone(self._time_msg("morning", 15))
        self.assertIsNone(self._time_msg("afternoon", 8))
        self.assertIsNone(self._time_msg("evening", 23))

    def test_unknown_tod(self):
        self.assertIsNone(self._time_msg("dinner", 20))


class CuriousMessageTests(_Base):
    def test_always_returns_prompt(self):
        with mock.patch.object(pr, "random") as mrand:
            mrand.choice.side_effect = lambda msgs: msgs[0]
            msg = pr.get_curious_message()
        self.assertIsInstance(msg, str)
        self.assertTrue(msg)
        self.assertEqual(len(mrand.choice.call_args.args[0]), 5)


class DueTaskTests(_Base):
    def _sched(self, due):
        m = mock.MagicMock()
        m.get_due_tasks.return_value = due
        pr.scheduler = m
        return m

    def test_no_scheduler(self):
        pr.scheduler = None
        self.assertIsNone(pr.get_due_task_message())

    def test_no_due_tasks(self):
        self._sched([])
        self.assertIsNone(pr.get_due_task_message())

    def test_task_without_due_time(self):
        s = self._sched([{"id": 7, "title": "Drink water"}])
        msg = pr.get_due_task_message()
        self.assertEqual(
            msg, "⏰ **Reminder:** 'Drink water' abhi ka time hai!")
        s.mark_notified.assert_called_once_with(7)

    def test_task_with_due_time(self):
        s = self._sched([{"id": 8, "title": "Meeting",
                          "due": "2026-01-01T14:30:00"}])
        msg = pr.get_due_task_message()
        self.assertIn("'Meeting'", msg)
        self.assertIn("(2:30 PM)", msg)
        s.mark_notified.assert_called_once_with(8)

    def test_corrupt_due_date_omits_time(self):
        s = self._sched([{"id": 9, "title": "X", "due": "garbage"}])
        msg = pr.get_due_task_message()
        self.assertIn("'X'", msg)
        self.assertNotIn("(", msg.replace("**Reminder:**", ""))
        s.mark_notified.assert_called_once_with(9)


class ProactiveMessageTests(_Base):
    def test_cooldown_short_circuits(self):
        pr.LAST_PROACTIVE = datetime.now()
        with mock.patch.object(pr, "get_due_task_message") as due:
            self.assertIsNone(pr.get_proactive_message())
        due.assert_not_called()

    def test_priority_due_first(self):
        with mock.patch.object(pr, "get_due_task_message",
                               return_value="DUE"), \
                mock.patch.object(pr, "get_time_message") as tmsg:
            msg = pr.get_proactive_message()
        self.assertEqual(msg, "DUE")
        tmsg.assert_not_called()
        self.assertIsNotNone(pr.LAST_PROACTIVE)
        self.assertTrue(pr.ACTIVE_PROACTIVE)

    def test_falls_through_to_time_message(self):
        with mock.patch.object(pr, "get_due_task_message",
                               return_value=None), \
                mock.patch.object(pr, "get_time_message",
                                  return_value="TIME"):
            self.assertEqual(pr.get_proactive_message(), "TIME")

    def test_falls_through_to_idle_then_session(self):
        with mock.patch.object(pr, "get_due_task_message",
                               return_value=None), \
                mock.patch.object(pr, "get_time_message",
                                  return_value=None), \
                mock.patch.object(pr, "get_idle_message",
                                  return_value=None), \
                mock.patch.object(pr, "get_session_message",
                                  return_value="SESSION"):
            self.assertEqual(pr.get_proactive_message(), "SESSION")

    def test_all_sources_none_returns_none(self):
        with mock.patch.object(pr, "get_due_task_message",
                               return_value=None), \
                mock.patch.object(pr, "get_time_message",
                                  return_value=None), \
                mock.patch.object(pr, "get_idle_message",
                                  return_value=None), \
                mock.patch.object(pr, "get_session_message",
                                  return_value=None), \
                mock.patch.object(pr, "get_curious_message",
                                  return_value=None):
            self.assertIsNone(pr.get_proactive_message())
        self.assertFalse(pr.ACTIVE_PROACTIVE)

    def test_state_not_set_when_blocked(self):
        pr.LAST_PROACTIVE = datetime.now()
        pr.ACTIVE_PROACTIVE = False
        pr.get_proactive_message()
        self.assertFalse(pr.ACTIVE_PROACTIVE)


if __name__ == "__main__":
    unittest.main()
