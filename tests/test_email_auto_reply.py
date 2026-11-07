"""Unit tests for orbit/orbit/core/email_auto_reply.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.email_auto_reply import EmailAutoReply, get_email_auto_reply


class TestEmailAutoReply(unittest.TestCase):
    def setUp(self):
        self.r = EmailAutoReply()

    def test_acknowledge(self):
        self.assertEqual(self.r.generate("acknowledge"), "Thanks for reaching out. I'll get back to you shortly.")

    def test_schedule_with_slots(self):
        r = self.r.generate("schedule", {"slots": "Mon 2pm"})
        self.assertEqual(r, "Let's schedule a call. Here are my available slots: Mon 2pm")

    def test_schedule_missing_slots(self):
        r = self.r.generate("schedule")
        self.assertEqual(r, "Let's schedule a call. Here are my available slots: {slots}")

    def test_decline(self):
        self.assertEqual(self.r.generate("decline"), "Thanks, but I won't be able to make it.")

    def test_info(self):
        r = self.r.generate("info", {"info": "the docs"})
        self.assertEqual(r, "Here's the information you requested: the docs")

    def test_info_missing(self):
        r = self.r.generate("info")
        self.assertEqual(r, "Here's the information you requested: {info}")

    def test_unknown_intent_default(self):
        self.assertEqual(self.r.generate("anything"), "Thanks for your email.")

    def test_templates_constant(self):
        self.assertIn("acknowledge", self.r.TEMPLATES)

    def test_singleton(self):
        a = get_email_auto_reply()
        b = get_email_auto_reply()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
