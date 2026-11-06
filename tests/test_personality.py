"""Unit tests for orbit/orbit/core/personality.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.personality import (
    orbitPersonality, get_personality, get_boot_message, get_system_prompt,
    emergency_response, success_response,
)


class TestOrbitPersonality(unittest.TestCase):
    def setUp(self):
        self.p = orbitPersonality()

    def test_instantiation(self):
        self.assertIsNotNone(self.p)
        self.assertIsInstance(self.p.personality_prompt, str)

    def test_get_system_prompt(self):
        r = self.p.get_system_prompt("base", "coding")
        self.assertIsInstance(r, str)
        self.assertIn("base", r)

    def test_get_system_prompt_no_base(self):
        r = self.p.get_system_prompt(task_type="chat")
        self.assertIsInstance(r, str)

    def test_get_tone_coding(self):
        r = self.p._get_tone("coding")
        self.assertIn("Precise", r)

    def test_get_tone_unknown(self):
        r = self.p._get_tone("zzz")
        self.assertIsInstance(r, str)

    def test_get_boot_message(self):
        r = self.p.get_boot_message()
        self.assertIsInstance(r, str)
        self.assertIn("ORBIT", r)

    def test_emergency_response(self):
        r = self.p.emergency_response("boom")
        self.assertIn("boom", r)

    def test_success_response(self):
        r = self.p.success_response("done")
        self.assertIn("done", r)

    def test_filter_response(self):
        r = self.p.filter_response("hello world reply", "chat")
        self.assertIsInstance(r, str)

    def test_filter_response_empty(self):
        self.assertEqual(self.p.filter_response("", "chat"), "")

    def test_get_soul_section(self):
        r = self.p.get_soul_section("nonexistent")
        self.assertIsInstance(r, str)

    def test_singleton(self):
        a = get_personality()
        b = get_personality()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_get_boot_message_func(self):
        r = get_boot_message()
        self.assertIsInstance(r, str)

    def test_get_system_prompt_func(self):
        r = get_system_prompt("base", "chat")
        self.assertIsInstance(r, str)

    def test_emergency_response_func(self):
        r = emergency_response("err")
        self.assertIsInstance(r, str)

    def test_success_response_func(self):
        r = success_response("ok")
        self.assertIsInstance(r, str)


if __name__ == "__main__":
    unittest.main()
