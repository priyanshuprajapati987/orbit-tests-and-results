# ruff: noqa: DTZ005 — source engine uses naive datetime.now()
"""
Context Engine — Tests

Tests calendar tracking, meeting prediction, and auto-briefings.

Key test: "Meeting in 1 hour → Briefing ready by 2:30"
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbit.orbit.core.context_engine import (
    ContextEngine,
    get_context_engine,
)

TEST_EVENTS = [
    {
        "id": "evt_meeting_1",
        "title": "Sprint Planning",
        "date": (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d"),
        "time": (datetime.now() + timedelta(hours=1)).strftime("%H:%M"),
        "duration_minutes": 60,
        "description": "Weekly sprint planning with team",
        "completed": False,
    },
    {
        "id": "evt_meeting_2",
        "title": "Client Call - Project Review",
        "date": (datetime.now() + timedelta(hours=5)).strftime("%Y-%m-%d"),
        "time": (datetime.now() + timedelta(hours=5)).strftime("%H:%M"),
        "duration_minutes": 30,
        "description": "Review project milestones with client",
        "completed": False,
    },
]


class MockCalendarTool:
    def __init__(self, events=None):
        self.events = events or []

    def list_events(self):
        return self.events

    def get_event(self, event_id):
        for e in self.events:
            if e["id"] == event_id:
                return e
        return None


class TestContextEngineCore(unittest.TestCase):
    def setUp(self):
        self.engine = ContextEngine(calendar_tool=MockCalendarTool([]))
        self.engine.reset()

    def test_01_import(self):
        from orbit.orbit.core.context_engine import ContextEngine

        self.assertTrue(ContextEngine)

    def test_02_singleton_getter(self):

        instance = get_context_engine()
        self.assertIsInstance(instance, ContextEngine)
        self.assertIs(instance, get_context_engine())

    def test_03_predict_briefing_needs_immediate(self):
        now = datetime.now()
        meeting_time = now + timedelta(minutes=30)
        eng = ContextEngine(calendar_tool=MockCalendarTool([]))
        eng.reset()
        with patch.object(eng, "get_upcoming_meetings") as mock_get:
            mock_get.return_value = [
                {
                    "id": "evt_now",
                    "title": "Urgent Standup",
                    "date": meeting_time.strftime("%Y-%m-%d"),
                    "time": meeting_time.strftime("%H:%M"),
                    "duration_minutes": 15,
                }
            ]
            predictions = eng.predict_briefing_needs()
            self.assertEqual(len(predictions), 1)
            self.assertTrue(predictions[0]["needs_briefing"])
            self.assertEqual(predictions[0]["event_id"], "evt_now")

    def test_04_predict_briefing_needs_far_away(self):
        far_time = datetime.now() + timedelta(hours=5)
        eng = ContextEngine(calendar_tool=MockCalendarTool([]))
        eng.reset()
        with patch.object(eng, "get_upcoming_meetings") as mock_get:
            mock_get.return_value = [
                {
                    "id": "evt_far",
                    "title": "Distant Meeting",
                    "date": far_time.strftime("%Y-%m-%d"),
                    "time": far_time.strftime("%H:%M"),
                    "duration_minutes": 60,
                }
            ]
            predictions = eng.predict_briefing_needs()
            self.assertEqual(len(predictions), 0)

    def test_05_generate_briefing(self):
        event = {
            "id": "evt_brief_test",
            "title": "Strategy Session",
            "date": "2026-07-30",
            "time": "14:30",
            "duration_minutes": 90,
            "description": "Q3 strategy planning",
        }
        engine = ContextEngine(calendar_tool=MockCalendarTool([event]))
        engine.reset()
        briefing = engine.generate_briefing("evt_brief_test")
        self.assertIsNotNone(briefing)
        self.assertEqual(briefing["event_title"], "Strategy Session")
        self.assertEqual(briefing["status"], "active")
        self.assertIn("content", briefing)
        self.assertIn("preparation", briefing["content"])
        self.assertIn("agenda_items", briefing["content"])
        self.assertGreater(len(briefing["content"]["preparation"]), 0)
        self.assertGreater(len(briefing["content"]["agenda_items"]), 0)

    def test_06_generate_briefing_twice_returns_same(self):
        event = {
            "id": "evt_dup",
            "title": "Duplicate Test",
            "date": "2026-07-30",
            "time": "15:00",
            "duration_minutes": 30,
        }
        engine = ContextEngine(calendar_tool=MockCalendarTool([event]))
        engine.reset()
        b1 = engine.generate_briefing("evt_dup")
        b2 = engine.generate_briefing("evt_dup")
        self.assertEqual(b1["id"], b2["id"])

    def test_07_dismiss_briefing(self):
        event = {
            "id": "evt_dismiss",
            "title": "Dismiss Test",
            "date": "2026-07-30",
            "time": "16:00",
            "duration_minutes": 30,
        }
        engine = ContextEngine(calendar_tool=MockCalendarTool([event]))
        engine.reset()
        briefing = engine.generate_briefing("evt_dismiss")
        self.assertEqual(briefing["status"], "active")
        ok = engine.dismiss_briefing(briefing["id"])
        self.assertTrue(ok)
        active = engine.get_active_briefings()
        self.assertEqual(len(active), 0)
        all_briefs = engine.get_all_briefings()
        dismissed = [b for b in all_briefs if b["id"] == briefing["id"]]
        self.assertEqual(dismissed[0]["status"], "dismissed")

    def test_08_record_accuracy_feedback(self):
        event = {
            "id": "evt_feedback",
            "title": "Feedback Test",
            "date": "2026-07-30",
            "time": "17:00",
            "duration_minutes": 30,
        }
        engine = ContextEngine(calendar_tool=MockCalendarTool([event]))
        engine.reset()
        briefing = engine.generate_briefing("evt_feedback")
        ok = engine.record_accuracy_feedback(briefing["id"], True)
        self.assertTrue(ok)
        stats = engine.get_stats()
        self.assertEqual(stats["feedback_count"], 1)
        self.assertEqual(stats["correct_count"], 1)
        self.assertEqual(stats["accuracy_pct"], 100.0)

    def test_09_accuracy_multiple_feedback(self):
        events = [
            {
                "id": "evt_acc_0",
                "title": "Accuracy 0",
                "date": "2026-07-30",
                "time": "10:00",
                "duration_minutes": 30,
            },
            {
                "id": "evt_acc_1",
                "title": "Accuracy 1",
                "date": "2026-07-30",
                "time": "11:00",
                "duration_minutes": 30,
            },
            {
                "id": "evt_acc_2",
                "title": "Accuracy 2",
                "date": "2026-07-30",
                "time": "12:00",
                "duration_minutes": 30,
            },
            {
                "id": "evt_acc_3",
                "title": "Accuracy 3",
                "date": "2026-07-30",
                "time": "13:00",
                "duration_minutes": 30,
            },
        ]
        engine = ContextEngine(calendar_tool=MockCalendarTool([]))
        engine.reset()
        for i, event in enumerate(events):
            sub = ContextEngine(calendar_tool=MockCalendarTool([event]))
            sub.reset()
            briefing = sub.generate_briefing(event["id"])
            engine._briefings.append(dict(briefing))
            engine.record_accuracy_feedback(briefing["id"], i < 3)
        stats = engine.get_stats()
        self.assertEqual(stats["feedback_count"], 4)
        self.assertEqual(stats["correct_count"], 3)
        self.assertEqual(stats["accuracy_pct"], 75.0)

    def test_10_stats_empty(self):
        engine = ContextEngine(calendar_tool=MockCalendarTool([]))
        engine.reset()
        stats = engine.get_stats()
        self.assertEqual(stats["total_predictions"], 0)
        self.assertEqual(stats["total_briefings"], 0)
        self.assertIsNone(stats["accuracy_pct"])

    def test_11_get_predictions(self):
        engine = ContextEngine(calendar_tool=MockCalendarTool([]))
        engine.reset()
        preds = engine.get_predictions()
        self.assertIsInstance(preds, list)
        self.assertEqual(len(preds), 0)

    def test_12_get_upcoming_meetings(self):
        engine = ContextEngine(calendar_tool=MockCalendarTool(TEST_EVENTS))
        engine.reset()
        meetings = engine.get_upcoming_meetings(hours_ahead=24)
        self.assertIsInstance(meetings, list)

    def test_13_dismiss_nonexistent_briefing(self):
        engine = ContextEngine(calendar_tool=MockCalendarTool([]))
        ok = engine.dismiss_briefing("nonexistent")
        self.assertFalse(ok)

    def test_14_feedback_nonexistent_briefing(self):
        engine = ContextEngine(calendar_tool=MockCalendarTool([]))
        ok = engine.record_accuracy_feedback("nonexistent", True)
        self.assertFalse(ok)

    def test_15_generate_briefing_nonexistent_event(self):
        engine = ContextEngine(calendar_tool=MockCalendarTool([]))
        engine.reset()
        briefing = engine.generate_briefing("nonexistent")
        self.assertIsNone(briefing)

    def test_16_briefing_content_structure(self):
        event = {
            "id": "evt_content",
            "title": "Content Check",
            "date": "2026-07-30",
            "time": "18:00",
            "duration_minutes": 45,
            "description": "Verify content structure",
        }
        engine = ContextEngine(calendar_tool=MockCalendarTool([event]))
        engine.reset()
        briefing = engine.generate_briefing("evt_content")
        content = briefing["content"]
        self.assertIn("preparation", content)
        self.assertIn("agenda_items", content)
        self.assertIn("attendees", content)
        self.assertIn("description_summary", content)
        self.assertIn("suggested_duration", content)
        self.assertEqual(content["suggested_duration"], "45 minutes")

    def test_17_generate_briefing_for_event_with_description(self):
        event = {
            "id": "evt_desc",
            "title": "With Description",
            "date": "2026-07-30",
            "time": "19:00",
            "duration_minutes": 60,
            "description": "Has a real description",
        }
        engine = ContextEngine(calendar_tool=MockCalendarTool([event]))
        engine.reset()
        briefing = engine.generate_briefing("evt_desc")
        self.assertEqual(
            briefing["content"]["description_summary"], "Has a real description"
        )


if __name__ == "__main__":
    unittest.main()
