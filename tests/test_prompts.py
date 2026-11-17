"""Unit tests for orbit/orbit/core/prompts.py — gap coverage."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.prompts import (
    REASONING_PROMPT,
    CODING_PROMPT,
    CREATIVE_PROMPT,
    FACTS_PROMPT,
    GENERAL_PROMPT,
    CATEGORY_PROMPTS,
    adaptive_prompt,
    get_user_skill_level,
    system_prompt_for,
)


class TestPromptConstants(unittest.TestCase):
    def test_reasoning_prompt_content(self):
        self.assertIn("1-3 sentences", REASONING_PROMPT)
        self.assertIn("calculation", REASONING_PROMPT)

    def test_coding_prompt_content(self):
        self.assertIn("```python", CODING_PROMPT)

    def test_creative_prompt(self):
        self.assertIn("creative", CREATIVE_PROMPT.lower())

    def test_facts_prompt(self):
        self.assertIn("1 sentence", FACTS_PROMPT)

    def test_general_prompt(self):
        self.assertIn("1-2 sentences", GENERAL_PROMPT)

    def test_category_map_complete(self):
        expected = ["reasoning", "code", "coding", "creative", "search",
                    "facts", "fast", "chat", "general", "math"]
        for k in expected:
            self.assertIn(k, CATEGORY_PROMPTS)

    def test_aliases_share_prompt(self):
        self.assertIs(CATEGORY_PROMPTS["code"], CATEGORY_PROMPTS["coding"])
        self.assertIs(CATEGORY_PROMPTS["search"], CATEGORY_PROMPTS["facts"])
        self.assertIs(CATEGORY_PROMPTS["fast"], CATEGORY_PROMPTS["general"])
        self.assertIs(CATEGORY_PROMPTS["chat"], CATEGORY_PROMPTS["general"])

    def test_math_maps_to_reasoning(self):
        self.assertIs(CATEGORY_PROMPTS["math"], REASONING_PROMPT)


class TestAdaptivePrompt(unittest.TestCase):
    def test_no_context_returns_base(self):
        self.assertEqual(adaptive_prompt("base"), "base")
        self.assertEqual(adaptive_prompt("base", None), "base")
        self.assertEqual(adaptive_prompt("base", {}), "base")

    def test_expert_skill(self):
        r = adaptive_prompt("base", {"skill_level": "expert"})
        self.assertIn("detailed technical depth", r)
        self.assertTrue(r.startswith("base"))

    def test_beginner_skill(self):
        r = adaptive_prompt("base", {"skill_level": "beginner"})
        self.assertIn("analogies", r)

    def test_intermediate_skill_no_suffix(self):
        r = adaptive_prompt("base", {"skill_level": "intermediate"})
        self.assertEqual(r, "base")

    def test_recent_topics(self):
        r = adaptive_prompt("base", {"recent_topics": ["ai", "ml", "nlp", "extra"]})
        # only first 3 topics
        self.assertIn("User's recent interests: ai, ml, nlp", r)
        self.assertNotIn("extra", r)

    def test_recent_topics_empty(self):
        r = adaptive_prompt("base", {"recent_topics": []})
        self.assertEqual(r, "base")

    def test_response_style(self):
        r = adaptive_prompt("base", {"response_style": "formal"})
        self.assertIn("Preferred style: formal", r)

    def test_multiple_parts_joined(self):
        r = adaptive_prompt("base", {
            "skill_level": "expert",
            "recent_topics": ["x"],
            "response_style": "casual",
        })
        self.assertIn("detailed technical depth", r)
        self.assertIn("User's recent interests: x", r)
        self.assertIn("Preferred style: casual", r)
        # parts joined by space
        self.assertIn(". User's recent", r)

    def test_unknown_skill_ignored(self):
        r = adaptive_prompt("base", {"skill_level": "wizard"})
        self.assertEqual(r, "base")


class TestGetUserSkillLevel(unittest.TestCase):
    def test_expert_when_avg_len_high(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gm:
            gm.return_value.get_stats.return_value = {"avg_query_length": 30}
            self.assertEqual(get_user_skill_level(), "expert")

    def test_beginner_when_avg_len_low(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gm:
            gm.return_value.get_stats.return_value = {"avg_query_length": 2}
            self.assertEqual(get_user_skill_level(), "beginner")

    def test_intermediate_when_avg_len_mid(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gm:
            gm.return_value.get_stats.return_value = {"avg_query_length": 10}
            self.assertEqual(get_user_skill_level(), "intermediate")

    def test_intermediate_boundary_20(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gm:
            gm.return_value.get_stats.return_value = {"avg_query_length": 20}
            self.assertEqual(get_user_skill_level(), "intermediate")

    def test_intermediate_boundary_5(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gm:
            gm.return_value.get_stats.return_value = {"avg_query_length": 5}
            self.assertEqual(get_user_skill_level(), "intermediate")

    def test_exception_returns_intermediate(self):
        with patch("orbit.core.smart_memory.get_smart_memory", side_effect=RuntimeError("x")):
            self.assertEqual(get_user_skill_level(), "intermediate")

    def test_no_stats_returns_intermediate(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gm:
            gm.return_value.get_stats.return_value = {}
            self.assertEqual(get_user_skill_level(), "intermediate")

    def test_no_get_stats_method(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gm:
            del gm.return_value.get_stats  # hasattr check -> False
            self.assertEqual(get_user_skill_level(), "intermediate")


class TestSystemPromptFor(unittest.TestCase):
    def test_math_uses_reasoning(self):
        self.assertEqual(system_prompt_for("math"), REASONING_PROMPT)

    def test_code_uses_coding(self):
        self.assertEqual(system_prompt_for("code"), CODING_PROMPT)

    def test_case_insensitive(self):
        self.assertEqual(system_prompt_for("MATH"), REASONING_PROMPT)
        self.assertEqual(system_prompt_for("Code"), CODING_PROMPT)

    def test_unknown_type_defaults_general(self):
        self.assertEqual(system_prompt_for("unknown"), GENERAL_PROMPT)

    def test_none_defaults_general(self):
        self.assertEqual(system_prompt_for(None), GENERAL_PROMPT)

    def test_empty_string_defaults_general(self):
        self.assertEqual(system_prompt_for(""), GENERAL_PROMPT)

    def test_with_user_context(self):
        r = system_prompt_for("math", {"skill_level": "expert"})
        self.assertEqual(r.split("\n\n")[0], REASONING_PROMPT)
        self.assertIn("detailed technical depth", r)


if __name__ == "__main__":
    unittest.main()
