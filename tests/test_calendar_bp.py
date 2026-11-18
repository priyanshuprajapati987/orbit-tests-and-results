"""Unit tests for orbit/orbit/core/calendar_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.calendar_bp import calendar_bp, _tool


def _patch_tool():
    mock = MagicMock()
    return patch.object(
        sys.modules["orbit.core.calendar_bp"], "_tool", mock
    ), mock


class CalendarBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(calendar_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(calendar_bp.name, "calendar_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/calendar/events", "/api/calendar/today",
                  "/api/calendar/upcoming", "/api/calendar/search",
                  "/api/calendar/events/<event_id>",
                  "/api/calendar/events/<event_id>/complete"]:
            self.assertIn(p, rules)
        # methods on the /api/calendar/events rule (both GET & POST registered)
        ev_rules = [r for r in self.app.url_map.iter_rules() if r.rule == "/api/calendar/events"]
        ev_methods = set()
        for r in ev_rules:
            ev_methods |= set(r.methods) - {"HEAD", "OPTIONS"}
        self.assertEqual(ev_methods, {"GET", "POST"})


class TestListEvents(CalendarBpBase):
    def test_list_default(self):
        p, m = _patch_tool()
        with p:
            m.list_events.return_value = [{"id": "e1"}]
            r = self.client.get("/api/calendar/events")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        m.list_events.assert_called_once_with(None, None, False)

    def test_list_filters(self):
        p, m = _patch_tool()
        with p:
            m.list_events.return_value = []
            r = self.client.get("/api/calendar/events?from=2026-01-01&to=2026-02-01&completed=true")
        m.list_events.assert_called_once_with("2026-01-01", "2026-02-01", True)

    def test_list_completed_case_insensitive(self):
        p, m = _patch_tool()
        with p:
            m.list_events.return_value = []
            r = self.client.get("/api/calendar/events?completed=TRUE")
        m.list_events.assert_called_once_with(None, None, True)

    def test_list_exception_500(self):
        p, m = _patch_tool()
        m.list_events.side_effect = RuntimeError("boom")
        with p:
            r = self.client.get("/api/calendar/events")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")


class TestToday(CalendarBpBase):
    def test_today(self):
        p, m = _patch_tool()
        with p:
            m.get_today.return_value = [{"id": "e1"}]
            r = self.client.get("/api/calendar/today")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 1)

    def test_today_exception_500(self):
        p, m = _patch_tool()
        m.get_today.side_effect = RuntimeError("x")
        with p:
            r = self.client.get("/api/calendar/today")
        self.assertEqual(r.status_code, 500)


class TestUpcoming(CalendarBpBase):
    def test_upcoming_default_days(self):
        p, m = _patch_tool()
        with p:
            m.get_upcoming.return_value = []
            r = self.client.get("/api/calendar/upcoming")
        m.get_upcoming.assert_called_once_with(7)

    def test_upcoming_custom_days(self):
        p, m = _patch_tool()
        with p:
            m.get_upcoming.return_value = []
            r = self.client.get("/api/calendar/upcoming?days=14")
        m.get_upcoming.assert_called_once_with(14)

    def test_upcoming_exception_500(self):
        p, m = _patch_tool()
        m.get_upcoming.side_effect = RuntimeError("x")
        with p:
            r = self.client.get("/api/calendar/upcoming")
        self.assertEqual(r.status_code, 500)


class TestCreateEvent(CalendarBpBase):
    def test_create_defaults(self):
        p, m = _patch_tool()
        with p:
            m.create_event.return_value = {"id": "e1", "title": "T"}
            r = self.client.post("/api/calendar/events", json={"title": "T", "date": "2026-01-01"})
        self.assertEqual(r.status_code, 200)
        m.create_event.assert_called_once_with(
            title="T", date="2026-01-01", time="00:00", duration_minutes=60,
            description="", recurrence="", reminder_minutes=15)

    def test_create_all_fields(self):
        p, m = _patch_tool()
        with p:
            m.create_event.return_value = {"id": "e2"}
            r = self.client.post("/api/calendar/events", json={
                "title": "T", "date": "2026-01-01", "time": "10:30",
                "duration_minutes": 30, "description": "D",
                "recurrence": "daily", "reminder_minutes": 5,
            })
        m.create_event.assert_called_once_with(
            title="T", date="2026-01-01", time="10:30", duration_minutes=30,
            description="D", recurrence="daily", reminder_minutes=5)

    def test_create_missing_title_400(self):
        r = self.client.post("/api/calendar/events", json={"date": "2026-01-01"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("title and date required", r.get_json()["error"])

    def test_create_missing_date_400(self):
        r = self.client.post("/api/calendar/events", json={"title": "T"})
        self.assertEqual(r.status_code, 400)

    def test_create_no_body_400(self):
        r = self.client.post("/api/calendar/events")
        self.assertEqual(r.status_code, 400)

    def test_create_exception_500(self):
        p, m = _patch_tool()
        m.create_event.side_effect = RuntimeError("x")
        with p:
            r = self.client.post("/api/calendar/events", json={"title": "T", "date": "2026-01-01"})
        self.assertEqual(r.status_code, 500)


class TestGetEvent(CalendarBpBase):
    def test_get_found(self):
        p, m = _patch_tool()
        with p:
            m.get_event.return_value = {"id": "e1"}
            r = self.client.get("/api/calendar/events/e1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "e1")

    def test_get_not_found_404(self):
        p, m = _patch_tool()
        with p:
            m.get_event.return_value = None
            r = self.client.get("/api/calendar/events/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Event not found")

    def test_get_exception_500(self):
        p, m = _patch_tool()
        m.get_event.side_effect = RuntimeError("x")
        with p:
            r = self.client.get("/api/calendar/events/e1")
        self.assertEqual(r.status_code, 500)


class TestUpdateEvent(CalendarBpBase):
    def test_update_success(self):
        p, m = _patch_tool()
        with p:
            m.update_event.return_value = True
            r = self.client.put("/api/calendar/events/e1", json={"title": "New"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        m.update_event.assert_called_once_with("e1", title="New")

    def test_update_pops_event_id(self):
        p, m = _patch_tool()
        with p:
            m.update_event.return_value = True
            r = self.client.put("/api/calendar/events/e1", json={"event_id": "hax", "title": "N"})
        # event_id stripped from kwargs
        m.update_event.assert_called_once_with("e1", title="N")

    def test_update_not_found_404(self):
        p, m = _patch_tool()
        with p:
            m.update_event.return_value = False
            r = self.client.put("/api/calendar/events/nope", json={"title": "x"})
        self.assertEqual(r.status_code, 404)

    def test_update_no_body(self):
        p, m = _patch_tool()
        with p:
            m.update_event.return_value = True
            r = self.client.put("/api/calendar/events/e1")
        self.assertEqual(r.status_code, 200)
        m.update_event.assert_called_once_with("e1")

    def test_update_exception_500(self):
        p, m = _patch_tool()
        m.update_event.side_effect = RuntimeError("x")
        with p:
            r = self.client.put("/api/calendar/events/e1", json={"title": "x"})
        self.assertEqual(r.status_code, 500)


class TestDeleteEvent(CalendarBpBase):
    def test_delete_ok(self):
        p, m = _patch_tool()
        with p:
            m.delete_event.return_value = True
            r = self.client.delete("/api/calendar/events/e1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])

    def test_delete_not_found_404(self):
        p, m = _patch_tool()
        with p:
            m.delete_event.return_value = False
            r = self.client.delete("/api/calendar/events/nope")
        self.assertEqual(r.status_code, 404)

    def test_delete_exception_500(self):
        p, m = _patch_tool()
        m.delete_event.side_effect = RuntimeError("x")
        with p:
            r = self.client.delete("/api/calendar/events/e1")
        self.assertEqual(r.status_code, 500)


class TestCompleteEvent(CalendarBpBase):
    def test_complete_ok(self):
        p, m = _patch_tool()
        with p:
            m.complete_event.return_value = True
            r = self.client.post("/api/calendar/events/e1/complete")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])

    def test_complete_not_found_404(self):
        p, m = _patch_tool()
        with p:
            m.complete_event.return_value = False
            r = self.client.post("/api/calendar/events/nope/complete")
        self.assertEqual(r.status_code, 404)

    def test_complete_exception_500(self):
        p, m = _patch_tool()
        m.complete_event.side_effect = RuntimeError("x")
        with p:
            r = self.client.post("/api/calendar/events/e1/complete")
        self.assertEqual(r.status_code, 500)


class TestSearch(CalendarBpBase):
    def test_search_success(self):
        p, m = _patch_tool()
        with p:
            m.search_events.return_value = [{"id": "e1"}]
            r = self.client.get("/api/calendar/search?q=meeting")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 1)
        m.search_events.assert_called_once_with("meeting")

    def test_search_missing_q_400(self):
        r = self.client.get("/api/calendar/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("q parameter required", r.get_json()["error"])

    def test_search_blank_q_400(self):
        r = self.client.get("/api/calendar/search?q=")
        self.assertEqual(r.status_code, 400)

    def test_search_exception_500(self):
        p, m = _patch_tool()
        m.search_events.side_effect = RuntimeError("x")
        with p:
            r = self.client.get("/api/calendar/search?q=x")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
