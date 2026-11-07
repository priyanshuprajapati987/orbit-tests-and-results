"""Unit tests for orbit/orbit/agents/briefing_agent.py."""

import os
import sys
import unittest
from datetime import datetime

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.briefing_agent import (
    BriefingSection,
    DailyBriefingAgent,
    get_briefing_agent,
    DATA_DIR,
)


class TestBriefingSection(unittest.TestCase):
    def test_defaults(self):
        s = BriefingSection(title="T", icon="i")
        self.assertEqual(s.items, [])
        self.assertEqual(s.status, "ok")


class TestDailyBriefingAgent(unittest.TestCase):
    def setUp(self):
        self.agent = DailyBriefingAgent()

    def test_init_creates_dir(self):
        self.assertTrue(DATA_DIR.exists())

    def test_greeting_morning(self):
        from datetime import datetime as dt
        g = self.agent._greeting(dt(2026, 1, 1, 8, 0))
        self.assertIn("Good morning", g)

    def test_greeting_afternoon(self):
        from datetime import datetime as dt
        g = self.agent._greeting(dt(2026, 1, 1, 14, 0))
        self.assertIn("Good afternoon", g)

    def test_greeting_evening(self):
        from datetime import datetime as dt
        g = self.agent._greeting(dt(2026, 1, 1, 20, 0))
        self.assertIn("Good evening", g)

    def test_sections_present(self):
        for name in (
            "_get_tech_scout_section",
            "_get_agent_activity_section",
            "_get_pending_approvals_section",
            "_get_learning_section",
            "_get_health_section",
        ):
            sec = getattr(self.agent, name)()
            self.assertIsInstance(sec, BriefingSection)
            self.assertTrue(sec.title)

    def test_generate_briefing(self):
        r = self.agent.generate_briefing()
        self.assertIn("timestamp", r)
        self.assertIn("sections", r)
        self.assertEqual(len(r["sections"]), 5)
        self.assertIn("summary", r)
        self.assertIn(r["summary"]["status"], ("alert", "all_clear"))

    def test_save_and_get_today(self):
        self.agent.generate_briefing()
        r = self.agent.get_today()
        self.assertIsNotNone(r)
        self.assertIn("sections", r)

    def test_get_history(self):
        self.agent.generate_briefing()
        r = self.agent.get_history(days=2)
        self.assertIsInstance(r, list)
        self.assertGreaterEqual(len(r), 1)

    def test_get_history_zero_days(self):
        r = self.agent.get_history(days=0)
        self.assertEqual(r, [])

    def test_singleton(self):
        a = get_briefing_agent()
        b = get_briefing_agent()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
