"""Tests for token_budget, semantic_similarity, and prompts modules."""

import os
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


class TestTokenBudget(unittest.TestCase):
    def test_estimate_tokens_basic(self):
        from orbit.orbit.core.token_budget import estimate_tokens

        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("a"), 1)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcdefgh"), 2)

    def test_estimate_tokens_long_text(self):
        from orbit.orbit.core.token_budget import estimate_tokens

        text = "hello world " * 100
        result = estimate_tokens(text)
        self.assertGreater(result, 100)

    def test_budget_allocation_basic(self):
        from orbit.orbit.core.token_budget import budget_allocation

        result = budget_allocation(1000, {"live": 0.5, "chunks": 0.3, "summary": 0.2})
        self.assertEqual(result["live"], 500)
        self.assertEqual(result["chunks"], 300)
        self.assertEqual(result["summary"], 200)

    def test_budget_allocation_sums_to_total(self):
        from orbit.orbit.core.token_budget import budget_allocation

        result = budget_allocation(1000, {"a": 0.33, "b": 0.33, "c": 0.34})
        total = sum(result.values())
        self.assertEqual(total, 1000)

    def test_budget_allocation_zero_budget(self):
        from orbit.orbit.core.token_budget import budget_allocation

        result = budget_allocation(0, {"a": 0.5, "b": 0.5})
        self.assertEqual(result["a"], 0)
        self.assertEqual(result["b"], 0)

    def test_token_tracker_basic(self):
        from orbit.orbit.core.token_budget import TokenTracker

        tracker = TokenTracker()
        tracker.record_turn(100, 50, 20)
        stats = tracker.get_stats()
        self.assertEqual(stats["turns"], 1)
        self.assertEqual(stats["tokens_in"], 100)
        self.assertEqual(stats["tokens_out"], 50)
        self.assertEqual(stats["tokens_compressed"], 20)

    def test_token_tracker_multiple_turns(self):
        from orbit.orbit.core.token_budget import TokenTracker

        tracker = TokenTracker()
        tracker.record_turn(100, 50)
        tracker.record_turn(200, 80)
        stats = tracker.get_stats()
        self.assertEqual(stats["turns"], 2)
        self.assertEqual(stats["tokens_in"], 300)

    def test_token_tracker_empty(self):
        from orbit.orbit.core.token_budget import TokenTracker

        tracker = TokenTracker()
        stats = tracker.get_stats()
        self.assertEqual(stats["turns"], 0)
        self.assertEqual(stats["compression_ratio"], 0.0)


class TestSemanticSimilarity(unittest.TestCase):
    def test_identical_texts(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        score = semantic_similarity("hello world", "hello world")
        self.assertGreater(score, 0.99)

    def test_disjoint_texts(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        score = semantic_similarity("quantum physics", "banana recipe")
        self.assertLess(score, 0.2)

    def test_similar_texts(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        score = semantic_similarity(
            "entangled quantum particles stay connected",
            "quantum entanglement connects particles",
        )
        self.assertGreater(score, 0.3)

    def test_empty_texts(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        score = semantic_similarity("", "")
        self.assertEqual(score, 0.0)

    def test_one_empty(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        score = semantic_similarity("hello world", "")
        self.assertEqual(score, 0.0)

    def test_tfidf_scorer(self):
        from orbit.orbit.core.semantic_similarity import TFIDFScorer

        scorer = TFIDFScorer()
        score = scorer.similarity("hello world", "hello world")
        self.assertGreater(score, 0.99)

    def test_tfidf_scorer_disjoint(self):
        from orbit.orbit.core.semantic_similarity import TFIDFScorer

        scorer = TFIDFScorer()
        score = scorer.similarity("aaa bbb ccc", "xxx yyy zzz")
        self.assertLess(score, 0.2)


class TestPrompts(unittest.TestCase):
    def test_system_prompt_for_reasoning(self):
        from orbit.orbit.core.prompts import system_prompt_for

        prompt = system_prompt_for("reasoning")
        self.assertIn("reasoning", prompt.lower())

    def test_system_prompt_for_coding(self):
        from orbit.orbit.core.prompts import system_prompt_for

        prompt = system_prompt_for("coding")
        self.assertIn("coding", prompt.lower())

    def test_system_prompt_for_creative(self):
        from orbit.orbit.core.prompts import system_prompt_for

        prompt = system_prompt_for("creative")
        self.assertIn("creative", prompt.lower())

    def test_system_prompt_for_facts(self):
        from orbit.orbit.core.prompts import system_prompt_for

        prompt = system_prompt_for("facts")
        self.assertIn("factual", prompt.lower())

    def test_system_prompt_for_general(self):
        from orbit.orbit.core.prompts import system_prompt_for

        prompt = system_prompt_for("general")
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 10)

    def test_system_prompt_for_unknown(self):
        from orbit.orbit.core.prompts import system_prompt_for

        prompt = system_prompt_for("unknown_category")
        self.assertIsInstance(prompt, str)

    def test_system_prompt_for_none(self):
        from orbit.orbit.core.prompts import system_prompt_for

        prompt = system_prompt_for(None)
        self.assertIsInstance(prompt, str)

    def test_category_prompts_dict(self):
        from orbit.orbit.core.prompts import CATEGORY_PROMPTS

        self.assertIn("reasoning", CATEGORY_PROMPTS)
        self.assertIn("coding", CATEGORY_PROMPTS)
        self.assertIn("creative", CATEGORY_PROMPTS)
        self.assertIn("facts", CATEGORY_PROMPTS)
        self.assertIn("general", CATEGORY_PROMPTS)

    def test_adaptive_prompt(self):
        from orbit.orbit.core.prompts import adaptive_prompt

        result = adaptive_prompt("base prompt", {"skill_level": "expert"})
        self.assertIn("detailed technical depth", result)

    def test_adaptive_prompt_no_context(self):
        from orbit.orbit.core.prompts import adaptive_prompt

        result = adaptive_prompt("base prompt", None)
        self.assertEqual(result, "base prompt")


if __name__ == "__main__":
    unittest.main()
