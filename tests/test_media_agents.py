"""Unit tests for orbit/orbit/agents/media_agents.py (screen/n8n/meeting/LLM mocked)."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.media_agents import ScreenAgent, SocialAgent, MeetingAgent


class TestScreenAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ScreenAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "SCR")
        self.assertIsNone(self.agent._cua)

    def test_can_handle_two_keywords(self):
        self.assertTrue(self.agent.can_handle("take a screenshot of screen"))

    def test_can_handle_intent_single(self):
        self.assertTrue(self.agent.can_handle("screenshot", intent="screen"))

    def test_can_handle_single_no_intent(self):
        self.assertFalse(self.agent.can_handle("please capture"))

    def test_can_handle_none(self):
        self.assertFalse(self.agent.can_handle("hello world"))

    def test_run_ui_tree(self):
        cua = MagicMock()
        cua.get_desktop_state.return_value = {"tree_markdown": "Window A\nButton B"}
        with patch.object(self.agent, "_get_cua", return_value=cua):
            r = self.agent.execute("show ui tree")
        self.assertIn("Desktop UI Tree", r)
        cua.get_desktop_state.assert_called_once()

    def test_run_ui_tree_error_falls_through(self):
        cua = MagicMock()
        cua.get_desktop_state.return_value = {"error": "no uia"}
        with patch.object(self.agent, "_get_cua", return_value=cua), \
             patch("orbit.screen.capture_screen", return_value=None):
            r = self.agent.execute("desktop state")
        self.assertIn("capture failed", r)

    def test_run_apps_running(self):
        cua = MagicMock()
        cua.list_apps.return_value = {"apps": [{"name": "Chrome", "pid": 1, "running": True}, {"name": "Idle", "pid": 2, "running": False}]}
        with patch.object(self.agent, "_get_cua", return_value=cua):
            r = self.agent.execute("show window list")
        self.assertIn("Running Apps (2)", r)
        self.assertIn("Chrome", r)

    def test_run_capture_success(self):
        with patch.object(self.agent, "_get_cua", return_value=None), \
             patch("orbit.screen.capture_screen", return_value="/tmp/shot.png"), \
             patch("orbit.screen.analyze_screenshot", return_value="analysis text"), \
             patch("orbit.screen.cleanup") as cleanup:
            r = self.agent.execute("screenshot the screen")
        self.assertEqual(r, "analysis text")
        cleanup.assert_called_once_with("/tmp/shot.png")

    def test_run_capture_failure(self):
        with patch.object(self.agent, "_get_cua", return_value=None), \
             patch("orbit.screen.capture_screen", return_value=None):
            r = self.agent.execute("screenshot the screen")
        self.assertIn("capture failed", r)

    def test_run_capture_empty_analysis(self):
        with patch.object(self.agent, "_get_cua", return_value=None), \
             patch("orbit.screen.capture_screen", return_value="/s.png"), \
             patch("orbit.screen.analyze_screenshot", return_value=""), \
             patch("orbit.screen.cleanup"):
            r = self.agent.execute("screenshot the screen")
        self.assertIn("no result", r)


class TestSocialAgent(unittest.TestCase):
    def setUp(self):
        self.agent = SocialAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "SOC")
        self.assertIsNone(self.agent._tool)

    def test_detect_platforms(self):
        self.assertEqual(self.agent._detect_platforms("post this on twitter"), ["twitter"])
        self.assertIn("instagram", self.agent._detect_platforms("insta reel banao"))
        self.assertEqual(self.agent._detect_platforms("hello"), [])

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("make a tweet"))
        self.assertFalse(self.agent.can_handle("hello there"))

    def test_run_n8n_offline_falls_to_llm(self):
        tool = MagicMock()
        tool.check_status.return_value = {"online": False}
        with patch.object(self.agent, "_get_tool", return_value=tool), \
             patch("orbit.agents.media_agents.llm_router.generate", return_value="llm text") as gen:
            r = self.agent.execute("write a linkedin post")
        self.assertEqual(r, "llm text")
        self.assertIn("linkedin", gen.call_args.kwargs["system_prompt"])

    def test_run_no_tool_falls_to_llm(self):
        with patch.object(self.agent, "_get_tool", return_value=None), \
             patch("orbit.agents.media_agents.llm_router.generate", return_value="llm text"):
            r = self.agent.execute("make a tweet")
        self.assertEqual(r, "llm text")

    def test_run_workflow_trigger(self):
        tool = MagicMock()
        tool.check_status.return_value = {"online": True}
        tool.trigger_workflow_by_name.return_value = "wf result"
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("trigger post_tweet now")
        self.assertIn("Social workflow triggered", r)

    def test_run_list_workflows(self):
        tool = MagicMock()
        tool.check_status.return_value = {"online": True}
        tool.handle_natural.return_value = "wf1, wf2"
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("list workflows")
        self.assertIn("Available social workflows", r)

    def test_run_action_publish(self):
        tool = MagicMock()
        tool.check_status.return_value = {"online": True}
        tool.trigger_workflow_by_name.return_value = "posted ok"
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("please publish this content")
        self.assertIn("Social workflow triggered (post)", r)

    def test_run_action_not_found_fallback_handle(self):
        tool = MagicMock()
        tool.check_status.return_value = {"online": True}
        tool.trigger_workflow_by_name.return_value = "workflow not found"
        tool.handle_natural.return_value = "handled result"
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("schedule a post for tomorrow")
        self.assertIn("n8n result", r)

    def test_run_tool_error_falls_to_llm(self):
        tool = MagicMock()
        tool.check_status.side_effect = RuntimeError("n8n down")
        with patch.object(self.agent, "_get_tool", return_value=tool), \
             patch("orbit.agents.media_agents.llm_router.generate", return_value="llm text"):
            r = self.agent.execute("post something")
        self.assertEqual(r, "llm text")

    def test_run_context_appended(self):
        with patch.object(self.agent, "_get_tool", return_value=None), \
             patch("orbit.agents.media_agents.llm_router.generate", return_value="x") as gen:
            self.agent.execute("make a post", context="ctx info")
        self.assertIn("[Context]", gen.call_args.kwargs["system_prompt"])


class TestMeetingAgent(unittest.TestCase):
    def setUp(self):
        self.agent = MeetingAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "MTG")

    def test_can_handle_intent(self):
        self.assertTrue(self.agent.can_handle("meeting", intent="meeting"))

    def test_can_handle_two_keywords(self):
        self.assertTrue(self.agent.can_handle("record meeting now"))

    def test_can_handle_single_no_intent(self):
        self.assertFalse(self.agent.can_handle("just meeting"))

    def test_can_handle_none(self):
        self.assertFalse(self.agent.can_handle("hello world"))

    def test_calendar_today(self):
        cal = MagicMock()
        cal.get_today.return_value = [{"title": "Standup", "time": "10:00"}]
        with patch("orbit.tools.calendar_tool.CalendarTool", return_value=cal):
            r = self.agent.execute("any calendar today")
        self.assertIn("Standup", r)

    def test_calendar_create(self):
        cal = MagicMock()
        cal.create_event.return_value = {"success": True}
        with patch("orbit.tools.calendar_tool.CalendarTool", return_value=cal):
            r = self.agent.execute("create event Team sync")
        self.assertIn("Event created", r)

    def test_calendar_create_failure(self):
        cal = MagicMock()
        cal.create_event.return_value = {"success": False, "error": "busy"}
        with patch("orbit.tools.calendar_tool.CalendarTool", return_value=cal):
            r = self.agent.execute("create event Team sync")
        self.assertIn("Could not create", r)

    def test_calendar_error(self):
        with patch("orbit.tools.calendar_tool.CalendarTool", side_effect=RuntimeError("cal broke")):
            r = self.agent.execute("show my schedule")
        self.assertIn("Calendar tool error", r)

    def test_join_no_url(self):
        r = self.agent.execute("join the meeting")
        self.assertIn("URL share karo", r)

    def test_join_ok(self):
        with patch("orbit.meeting.join_meeting", return_value=True):
            r = self.agent.execute("join https://zoom.us/j/123")
        self.assertIn("Meeting link open kiya", r)

    def test_join_and_record(self):
        with patch("orbit.meeting.join_meeting", return_value=True), \
             patch("orbit.meeting.start_meeting", return_value={"success": True, "title": "t"}):
            r = self.agent.execute("join https://x.co/m and record")
        self.assertIn("recording start", r)

    def test_join_fail(self):
        with patch("orbit.meeting.join_meeting", return_value=False):
            r = self.agent.execute("join https://bad.url/x")
        self.assertIn("nahi ho payi", r)

    def test_start_meeting(self):
        with patch("orbit.meeting.start_meeting", return_value={"success": True, "title": "daily"}) as m:
            r = self.agent.execute("start meeting daily standup")
        self.assertIn("recording start", r.lower())
        m.assert_called_once()

    def test_start_meeting_failure(self):
        with patch("orbit.meeting.start_meeting", return_value={"success": False, "error": "mic missing"}):
            r = self.agent.execute("start meeting x")
        self.assertIn("mic missing", r)

    def test_stop_meeting_summary(self):
        with patch("orbit.meeting.stop_meeting", return_value={
            "success": True,
            "meeting": {"title": "Sync", "duration_seconds": 125, "summary": "sum", "action_items": ["do x"]},
        }):
            r = self.agent.execute("stop the meeting")
        self.assertIn("khatam", r)
        self.assertIn("2m 5s", r)
        self.assertIn("do x", r)

    def test_stop_meeting_no_details(self):
        with patch("orbit.meeting.stop_meeting", return_value={"success": True}):
            r = self.agent.execute("end meeting")
        self.assertIn("Meeting stopped", r)

    def test_stop_meeting_error(self):
        with patch("orbit.meeting.stop_meeting", return_value={"success": False, "error": "not active"}):
            r = self.agent.execute("stop meeting")
        self.assertIn("not active", r)

    def test_delete_meeting(self):
        with patch("orbit.meeting.delete_meeting", return_value=True):
            r = self.agent.execute("delete meeting abc123")
        self.assertIn("delete ho gayi", r)

    def test_delete_meeting_not_found(self):
        with patch("orbit.meeting.delete_meeting", return_value=False):
            r = self.agent.execute("delete meeting abc123")
        self.assertIn("nahi mili", r)

    def test_delete_no_id(self):
        r = self.agent.execute("delete meeting")
        self.assertIn("ID batao", r)

    def test_history_empty(self):
        with patch("orbit.meeting.list_meetings", return_value=[]):
            r = self.agent.execute("show meeting history")
        self.assertIn("No meetings recorded", r)

    def test_history_items(self):
        with patch("orbit.meeting.list_meetings", return_value=[{"title": "A", "date": "2026-01-01", "duration_seconds": 600}]):
            r = self.agent.execute("show meetings")
        self.assertIn("Meeting History", r)
        self.assertIn("A", r)

    def test_search_found(self):
        with patch("orbit.meeting.search_meetings", return_value=[{"title": "Proj X", "date": "d"}]):
            r = self.agent.execute("search meeting for proj")
        self.assertIn("Proj X", r)

    def test_search_not_found(self):
        with patch("orbit.meeting.search_meetings", return_value=[]):
            r = self.agent.execute("search meeting for zzz")
        self.assertIn("nahi mili", r)

    def test_export_all(self):
        with patch("orbit.meeting.export_all_meetings", return_value="/path/out.md"):
            r = self.agent.execute("export all meetings")
        self.assertIn("exported", r)

    def test_export_all_fail(self):
        with patch("orbit.meeting.export_all_meetings", return_value=None):
            r = self.agent.execute("export all meetings")
        self.assertIn("Export failed", r)

    def test_export_single(self):
        with patch("orbit.meeting.export_meeting", return_value="/p.md"):
            r = self.agent.execute("export meeting abc")
        self.assertIn("Meeting exported", r)

    def test_export_no_id(self):
        r = self.agent.execute("export meeting")
        self.assertIn("ID batao", r)

    def test_action_items(self):
        with patch("orbit.meeting.list_meetings", return_value=[{"title": "A", "action_items": ["item1"]}]):
            r = self.agent.execute("show action items")
        self.assertIn("item1", r)

    def test_action_items_empty(self):
        with patch("orbit.meeting.list_meetings", return_value=[{"title": "A", "action_items": []}]):
            r = self.agent.execute("show action items")
        self.assertIn("No action items", r)

    def test_save_to_notes(self):
        with patch("orbit.meeting.save_meeting_to_notes", return_value={"success": True, "path": "/n.md"}):
            r = self.agent.execute("save meeting to notes abc")
        self.assertIn("saved to notes", r)

    def test_save_to_notes_fail(self):
        with patch("orbit.meeting.save_meeting_to_notes", return_value={"success": False}):
            r = self.agent.execute("save meeting to notes abc")
        self.assertIn("Save failed", r)

    def test_simulate_llm(self):
        with patch("orbit.agents.media_agents.llm_router.generate", return_value="simulated discussion") as gen:
            r = self.agent.execute("simulate meeting about hiring")
        self.assertEqual(r, "simulated discussion")
        self.assertIn("Simulate a meeting", gen.call_args.kwargs["system_prompt"])

    def test_stats_empty(self):
        with patch("orbit.meeting.list_meetings", return_value=[]):
            r = self.agent.execute("meeting stats")
        self.assertIn("No meeting stats", r)

    def test_stats_values(self):
        meetings = [
            {"title": "A", "duration_seconds": 3600, "action_items": [1, 2]},
            {"title": "B", "duration_seconds": 600, "action_items": []},
        ]
        with patch("orbit.meeting.list_meetings", return_value=meetings):
            r = self.agent.execute("show meeting stats")
        self.assertIn("Total meetings: 2", r)
        self.assertIn("Total action items: 2", r)

    def test_fallback_llm(self):
        with patch("orbit.agents.media_agents.llm_router.generate", return_value="llm answer") as gen:
            r = self.agent.execute("hello buddy")
        self.assertEqual(r, "llm answer")
        self.assertIn("MEETING specialist", gen.call_args.kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()
