"""True ground-truth eval tests: curated answer keys, deterministic scoring."""

import asyncio
import unittest
from unittest import mock

from orbit.orbit.core.ground_truth import (
    GROUND_TRUTH,
    GroundTruthBenchmark,
    GroundTruthItem,
    get_ground_truth,
    run_ground_truth,
    score_response,
    summarize,
)


class TestGroundTruthItem(unittest.TestCase):
    def test_substring_match(self):
        item = GroundTruthItem(
            prompt="cap of australia",
            answer="Canberra",
            required=["canberra"],
            category="facts",
        )
        ok = score_response("The capital of Australia is Canberra.", item)
        self.assertTrue(ok["correct"])
        self.assertEqual(ok["required_found"], ["canberra"])

    def test_missing_answer_wrong(self):
        item = GroundTruthItem(
            prompt="cap of france", answer="Paris", required=["paris"], category="facts"
        )
        ok = score_response("The capital is Lyon.", item)
        self.assertFalse(ok["correct"])
        self.assertEqual(ok["coverage"], 0.0)

    def test_any_of_match(self):
        item = GroundTruthItem(
            prompt="paint mona lisa",
            answer="Leonardo da Vinci",
            any_of=["da vinci", "leonardo"],
            category="facts",
        )
        ok = score_response("It was painted by Leonardo da Vinci.", item)
        self.assertTrue(ok["correct"])

    def test_numeric_match_within_tolerance(self):
        item = GroundTruthItem(
            prompt="boiling point water",
            answer="100 C",
            number=100.0,
            tolerance=0.001,
            category="facts",
        )
        ok = score_response("100 degrees Celsius", item)
        self.assertTrue(ok["correct"])
        self.assertEqual(ok["numeric_ok"], True)

    def test_numeric_wrong(self):
        item = GroundTruthItem(
            prompt="boiling point water",
            answer="100 C",
            number=100.0,
            tolerance=0.001,
            category="facts",
        )
        ok = score_response("120 degrees", item)
        self.assertFalse(ok["correct"])

    def test_partial_required_coverage(self):
        item = GroundTruthItem(
            prompt="gcd",
            required=["gcd", "greatest"],
            answer="greatest common divisor",
            category="math",
        )
        ok = score_response("the gcd is the greatest common divisor", item)
        self.assertEqual(ok["coverage"], 1.0)

    def test_empty_response_fails(self):
        item = GroundTruthItem(prompt="x", answer="y", required=["y"], category="facts")
        ok = score_response("", item)
        self.assertFalse(ok["correct"])
        self.assertEqual(ok["coverage"], 0.0)

    def test_comma_normalized_numeric(self):
        item = GroundTruthItem(
            prompt="speed of light",
            answer="299792458",
            any_of=["299792458"],
            category="facts",
        )
        ok = score_response(
            "The speed of light is 299,792,458 meters per second.", item
        )
        self.assertTrue(ok["correct"])

    def test_sqrt_latex_normalized(self):
        item = GroundTruthItem(
            prompt="simplify sqrt 50",
            answer="5*sqrt(2)",
            any_of=["5 sqrt", "5√2", "5sqrt2"],
            category="math",
        )
        ok = score_response(r"The simplified form is \(5\sqrt{2}\).", item)
        self.assertTrue(ok["correct"])

    def test_any_of_single_synonym_suffices(self):
        item = GroundTruthItem(
            prompt="supervised vs unsupervised",
            answer="labeled data",
            any_of=["labeled", "unlabeled", "labels"],
            category="general",
        )
        ok = score_response("Supervised learning uses labeled data.", item)
        self.assertTrue(ok["correct"])

    def test_numeric_matches_without_text_key(self):
        item = GroundTruthItem(
            prompt="circle area",
            answer="154",
            number=154.0,
            tolerance=0.5,
            category="math",
        )
        ok = score_response("approximately 153.94", item)
        self.assertTrue(ok["correct"])

    def test_wrong_numeric_not_saved_by_generic_text(self):
        item = GroundTruthItem(
            prompt="train meet",
            answer="1.2h",
            any_of=["1.2", "3.2"],
            number=1.2,
            category="reasoning",
        )
        ok = score_response("They meet 2 hours later.", item)
        self.assertFalse(ok["correct"])


class TestGroundTruthSuite(unittest.TestCase):
    def test_suite_has_all_categories(self):
        cats = {i.category for i in GROUND_TRUTH}
        self.assertEqual(cats, {"facts", "math", "coding", "reasoning", "general"})
        self.assertGreaterEqual(len(GROUND_TRUTH), 90)

    def test_get_ground_truth_slicing(self):
        got = get_ground_truth(category="math", n=5)
        self.assertTrue(all(i.category == "math" for i in got))
        self.assertEqual(len(got), 5)
        self.assertEqual(len(get_ground_truth(n=3)), 3)

    def test_get_ground_truth_bad_category(self):
        with self.assertRaises(ValueError):
            get_ground_truth(category="nope")

    def test_summarize(self):
        results = [
            score_response("Canberra", get_ground_truth(category="facts", n=1)[0]),
            score_response("totally wrong", get_ground_truth(category="math", n=1)[0]),
        ]
        summary = summarize(results)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["correct"], 1)
        self.assertAlmostEqual(summary["overall_accuracy"], 0.5)
        self.assertEqual(summary["categories"][0]["category"], "facts")

    def test_summarize_empty(self):
        summary = summarize([])
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["overall_accuracy"], 0.0)


class TestGroundTruthBenchmark(unittest.TestCase):
    def _patch_router(self):
        calls = []

        class _FakeRouter:
            async def generate(self, request):
                calls.append(request)
                from orbit.orbit.core.llm.router import LLMResponse

                return LLMResponse(
                    content="The capital is Canberra.",
                    provider="mock",
                    model="m",
                    latency_ms=5,
                    success=True,
                )

        return calls, mock.patch(
            "orbit.orbit.core.llm.router.get_router", return_value=_FakeRouter()
        )

    def test_run_scores_and_reports(self):
        calls, patcher = self._patch_router()
        with patcher:
            payload = run_ground_truth(category="facts", n=3)
        self.assertIn("summary", payload)
        self.assertEqual(payload["summary"]["total"], 3)
        self.assertEqual(len(payload["results"]), 3)
        self.assertEqual(len(calls), 3)

    def test_run_respects_max_tokens_and_cache(self):
        calls, patcher = self._patch_router()
        with patcher:
            run_ground_truth(category="math", n=2, max_tokens=40, use_cache=False)
        for req in calls:
            self.assertEqual(req.max_tokens, 40)
            self.assertFalse(req.use_cache)

    def test_benchmark_class_direct(self):
        _calls, patcher = self._patch_router()
        with patcher:
            bench = GroundTruthBenchmark()
            payload = asyncio.run(bench.run(category="coding", n=2))
        self.assertEqual(len(payload["results"]), 2)
        self.assertIn("category", payload["results"][0])
        self.assertIn("correct", payload["results"][0])


class TestKeyFixRegressions20261006(unittest.TestCase):
    """2026-10-06 scoring-key fixes (claim-closure round): sin(30)
    required-AND authoring bug + farmer wrong key (17/13 = 86 legs != 74)."""

    @staticmethod
    def _item(prefix):
        for it in GROUND_TRUTH:
            if it.prompt.startswith(prefix):
                return it
        raise AssertionError(f"item not found: {prefix}")

    def test_sin30_any_of_or_semantics(self):
        item = self._item("What is the value of sin(30 degrees)?")
        self.assertIn("0.5", item.any_of)
        scored = score_response("The value of sin(30 degrees) is 0.5.", item)
        self.assertTrue(scored["correct"], scored)

    def test_sin30_wrong_value_fails(self):
        item = self._item("What is the value of sin(30 degrees)?")
        scored = score_response("The value of sin(30 degrees) is 0.866.", item)
        self.assertFalse(scored["correct"], scored)

    def test_farmer_key_is_23_chickens_7_cows(self):
        item = self._item("A farmer has chickens and cows")
        self.assertEqual(item.required, ["23", "7"])
        scored = score_response("Final answer: 23 chickens and 7 cows.", item)
        self.assertTrue(scored["correct"], scored)

    def test_farmer_old_wrong_key_does_not_pass(self):
        item = self._item("A farmer has chickens and cows")
        scored = score_response("There are 17 cows and 13 chickens.", item)
        self.assertFalse(scored["correct"], scored)


class TestDay55KeyAndPromptFixes(unittest.TestCase):
    """GT gap-closure fixes (2026-10-17): 2 key-authoring bugs + router prompts."""

    def _item(self, prefix, category=None):
        for it in GROUND_TRUTH:
            if it.prompt.startswith(prefix) and (category is None or it.category == category):
                return it
        raise AssertionError(f"item not found: {prefix}")

    # -- second-largest key: "code" prompt must accept non-def code forms --
    def test_second_largest_correct_code_without_def_passes(self):
        item = self._item("Write Python code to find the second largest")
        response = (
            "```python\nsorted_list = sorted(list(set(my_list)))\n"
            "second_largest = sorted_list[-2] if len(sorted_list) >= 2 else None\n```"
        )
        scored = score_response(response, item)
        self.assertTrue(scored["correct"], scored)

    def test_second_largest_prose_without_code_fails(self):
        item = self._item("Write Python code to find the second largest")
        scored = score_response("You can sort the list and pick the second item from the end.", item)
        self.assertFalse(scored["correct"], scored)

    # -- clock-3:15 key: accept degree-symbol form (was required-AND "7.5 degrees") --
    def test_clock_750_degree_symbol_form_passes(self):
        item = self._item("A clock shows 3:15", category="math")
        response = (
            "The minute hand at 15 minutes is at 90 deg. The hour hand at 3:15 is "
            "90 deg + 7.5 deg = 97.5 deg. The angle between them is 7.5 deg. Final answer: 7.5\u00b0."
        )
        self.assertTrue(score_response(response, item)["correct"])

    def test_clock_750_word_form_passes(self):
        item = self._item("A clock shows 3:15", category="math")
        self.assertTrue(score_response("The angle between the hands is 7.5 degrees.", item)["correct"])

    def test_clock_old_wrong_225_answer_still_fails(self):
        item = self._item("A clock shows 3:15", category="math")
        wrong = (
            "The minute hand is at 90 degrees, and the hour hand is at 112.5 degrees, "
            "so the angle between them is 22.5 degrees."
        )
        self.assertFalse(score_response(wrong, item)["correct"])

    # -- router category prompts: math wired, coding code-first, single source --
    def test_math_category_uses_reasoning_prompt(self):
        from orbit.orbit.core.prompts import REASONING_PROMPT, system_prompt_for

        self.assertEqual(system_prompt_for("math"), REASONING_PROMPT)

    def test_coding_prompt_is_code_first(self):
        from orbit.orbit.core.prompts import CODING_PROMPT

        low = CODING_PROMPT.lower()
        self.assertIn("coding", low)
        self.assertIn("```python", low)
        self.assertIn("never answer with only a description", low)

    def test_system_prompt_for_uses_category_prompts_source(self):
        from orbit.orbit.core.prompts import (
            CODING_PROMPT,
            FACTS_PROMPT,
            GENERAL_PROMPT,
            REASONING_PROMPT,
            system_prompt_for,
        )

        # aliases and previously-unmapped categories resolve via CATEGORY_PROMPTS
        self.assertEqual(system_prompt_for("code"), CODING_PROMPT)
        self.assertEqual(system_prompt_for("fast"), GENERAL_PROMPT)
        self.assertEqual(system_prompt_for("chat"), GENERAL_PROMPT)
        self.assertEqual(system_prompt_for("search"), FACTS_PROMPT)
        self.assertEqual(system_prompt_for("reasoning"), REASONING_PROMPT)
        # unknown/None still fall back to GENERAL
        self.assertEqual(system_prompt_for("unknown_category"), GENERAL_PROMPT)
        self.assertEqual(system_prompt_for(None), GENERAL_PROMPT)

    def test_category_prompts_has_math(self):
        from orbit.orbit.core.prompts import CATEGORY_PROMPTS, REASONING_PROMPT

        self.assertEqual(CATEGORY_PROMPTS.get("math"), REASONING_PROMPT)


if __name__ == "__main__":
    unittest.main()
