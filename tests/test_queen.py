"""Unit tests for orbit/orbit/agents/queen.py (Qwen/smart-router/agents mocked)."""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.queen import (
    QueenAgent,
    ALL_AGENTS,
    AGENT_CATEGORIES,
    AGENT_CAPABILITIES,
    QUEEN_SYSTEM_PROMPT,
    QUEEN_PLAN_PROMPT,
    _is_agent_error,
)


class TestIsAgentError(unittest.TestCase):
    def test_tas_error(self):
        self.assertTrue(_is_agent_error("[TAS error: boom]"))

    def test_executor_error(self):
        self.assertTrue(_is_agent_error("[Executor error in code: x]"))

    def test_not_available(self):
        self.assertTrue(_is_agent_error("[BrowserTool not available]"))

    def test_legacy_error(self):
        # NOTE: comment in queen.py claims this matches "[Error: ...]", but the
        # regex requires a word boundary before "error" — verified actual behavior:
        self.assertFalse(_is_agent_error("[Error: no provider]"))

    def test_normal_answer(self):
        self.assertFalse(_is_agent_error("Here is your answer with details"))

    def test_non_string(self):
        self.assertFalse(_is_agent_error(None))
        self.assertFalse(_is_agent_error(123))

    def test_empty(self):
        self.assertFalse(_is_agent_error(""))


class TestConstants(unittest.TestCase):
    def test_all_agents(self):
        self.assertEqual(len(ALL_AGENTS), 24)

    def test_categories_reference_known_agents(self):
        for cat, labels in AGENT_CATEGORIES.items():
            for label in labels:
                self.assertIn(label, ALL_AGENTS, f"{label} missing from ALL_AGENTS in {cat}")

    def test_capabilities_cover_most_agents(self):
        for label in AGENT_CAPABILITIES:
            self.assertIn(label, ALL_AGENTS)
        self.assertGreaterEqual(len(AGENT_CAPABILITIES), 20)

    def test_system_prompt(self):
        self.assertIn("QUEEN AGENT", QUEEN_SYSTEM_PROMPT)
        self.assertIn("TAS", QUEEN_SYSTEM_PROMPT)

    def test_plan_prompt(self):
        self.assertIn("{text}", QUEEN_PLAN_PROMPT)


class TestQueenAgentBasics(unittest.TestCase):
    def setUp(self):
        self.queen = QueenAgent()

    def test_instantiation(self):
        self.assertEqual(self.queen.label, "QNN")
        self.assertEqual(self.queen.agents, {})

    def test_can_handle_always(self):
        self.assertTrue(self.queen.can_handle("literally anything"))

    def test_set_agents(self):
        fake = MagicMock()
        self.queen.set_agents({"TAS": fake})
        self.assertIn("TAS", self.queen.agents)

    def test_set_callback_and_emit(self):
        calls = []
        self.queen.set_callback(calls.append)
        self.queen._emit_agent("TAS")
        self.assertEqual(calls, ["TAS"])

    def test_emit_no_callback(self):
        self.queen._emit_agent("TAS")  # no crash

    def test_get_plan_initial(self):
        self.assertIsNone(self.queen.get_plan())

    def test_get_queue_status(self):
        self.assertEqual(self.queen.get_queue_status(), [])

    def test_ensure_agents_noop_when_set(self):
        self.queen.set_agents({"TAS": MagicMock()})
        with patch("orbit.agents.AGENT_REGISTRY", side_effect=AssertionError("should not import")):
            self.queen._ensure_agents()
        self.assertEqual(list(self.queen.agents.keys()), ["TAS"])

    def test_ensure_agents_populates_from_registry(self):
        class FakeAgent:
            def __init__(self, assistant=None):
                self.assistant = assistant

        registry = {"TAS": FakeAgent, "QUEEN": FakeAgent}
        with patch("orbit.agents.AGENT_REGISTRY", registry):
            self.queen._ensure_agents()
        self.assertIn("TAS", self.queen.agents)
        self.assertNotIn("QUEEN", self.queen.agents)

    def test_resolve_agent_unknown(self):
        self.queen.set_agents({"TAS": MagicMock()})
        self.assertIsNone(self.queen._resolve_agent("XXX"))

    def test_resolve_agent_known(self):
        fake = MagicMock()
        self.queen.set_agents({"TAS": fake})
        with patch("orbit.core.agent_awareness.get_awareness_manager", side_effect=RuntimeError("nope")):
            self.assertIs(self.queen._resolve_agent("TAS"), fake)


class TestGeneratePlan(unittest.TestCase):
    def setUp(self):
        self.queen = QueenAgent()

    def test_plain_json(self):
        with patch.object(self.queen, "_call_qwen", return_value='{"plan": ["TAS"], "reasoning": "sys"}'):
            plan = self.queen._generate_plan("open chrome")
        self.assertEqual(plan["plan"], ["TAS"])

    def test_fenced_json(self):
        resp = '```json\n{"plan": ["COD"], "reasoning": "code"}\n```'
        with patch.object(self.queen, "_call_qwen", return_value=resp):
            plan = self.queen._generate_plan("write code")
        self.assertEqual(plan["plan"], ["COD"])

    def test_fenced_plain(self):
        resp = '```\n{"plan": ["RES"], "reasoning": "news"}\n```'
        with patch.object(self.queen, "_call_qwen", return_value=resp):
            plan = self.queen._generate_plan("latest news")
        self.assertEqual(plan["plan"], ["RES"])

    def test_error_response_fallback(self):
        with patch.object(self.queen, "_call_qwen", return_value="[Error: no llm]"):
            plan = self.queen._generate_plan("x")
        self.assertEqual(plan["reasoning"], "fallback")
        self.assertEqual(plan["plan"], [])

    def test_none_response_fallback(self):
        with patch.object(self.queen, "_call_qwen", return_value=None):
            plan = self.queen._generate_plan("x")
        self.assertEqual(plan["reasoning"], "fallback")

    def test_invalid_json_chat(self):
        with patch.object(self.queen, "_call_qwen", return_value="I think you should use TAS"):
            plan = self.queen._generate_plan("x")
        self.assertEqual(plan["reasoning"], "chat")

    def test_braces_in_text_no_crash(self):
        with patch.object(self.queen, "_call_qwen", return_value='{"plan": ["TAS"], "reasoning": "r"}') as m:
            plan = self.queen._generate_plan("format {json} like {this}")
        self.assertEqual(plan["plan"], ["TAS"])
        self.assertIn("{{json}}", m.call_args[0][0])


class TestCallQwen(unittest.TestCase):
    def setUp(self):
        self.queen = QueenAgent()

    def test_ollama_success(self):
        inner = MagicMock()
        inner.read.return_value = json.dumps({"message": {"content": "ollama says hi"}}).encode()
        cm = MagicMock()
        cm.__enter__.return_value = inner
        with patch("urllib.request.urlopen", return_value=cm):
            r = self.queen._call_qwen("prompt")
        self.assertEqual(r, "ollama says hi")

    def test_fallback_to_legacy_router(self):
        with patch("urllib.request.urlopen", side_effect=RuntimeError("no ollama")), \
             patch("orbit.core.llm.legacy_adapter.generate", return_value="legacy reply") as gen:
            r = self.queen._call_qwen("prompt")
        self.assertEqual(r, "legacy reply")
        gen.assert_called_once()

    def test_both_fail_returns_none(self):
        with patch("urllib.request.urlopen", side_effect=RuntimeError("no ollama")), \
             patch("orbit.core.llm.legacy_adapter.generate", side_effect=RuntimeError("no llm")):
            r = self.queen._call_qwen("prompt")
        self.assertIsNone(r)


class TestExecutePlan(unittest.TestCase):
    def setUp(self):
        self.queen = QueenAgent()
        self.tas = MagicMock()
        self.tas.name = "TaskAgent"
        self.tas.execute.return_value = "task result"
        self.cod = MagicMock()
        self.cod.name = "CodeAgent"
        self.cod.execute.return_value = "code result"
        self.queen.set_agents({"TAS": self.tas, "COD": self.cod})

    def test_empty_plan(self):
        self.assertIsNone(self.queen._execute_plan("x", {"plan": []}))

    def test_sequential_no_synth(self):
        r = self.queen._execute_plan("x", {"plan": ["TAS"], "synthesize": False})
        self.assertEqual(r, "[TAS]: task result")
        self.tas.execute.assert_called_once()

    def test_agent_exception_wrapped(self):
        self.tas.execute.side_effect = RuntimeError("boom")
        r = self.queen._execute_plan("x", {"plan": ["TAS"], "synthesize": False})
        self.assertIn("[TAS error: boom]", r)

    def test_unknown_agent_skipped(self):
        r = self.queen._execute_plan("x", {"plan": ["GHOST"], "synthesize": False})
        self.assertEqual(r, "")

    def test_parallel(self):
        r = self.queen._execute_plan("x", {"plan": ["TAS", "COD"], "parallel": True, "synthesize": False})
        self.assertIn("[TAS]: task result", r)
        self.assertIn("[COD]: code result", r)

    def test_prior_results_in_context(self):
        self.queen._execute_plan("x", {"plan": ["TAS", "COD"], "synthesize": False})
        ctx = self.cod.execute.call_args[0][1]
        self.assertIn("prior_results", ctx)
        self.assertIn("TAS", ctx["prior_results"])


class TestCritiqueAndSynthesize(unittest.TestCase):
    def setUp(self):
        self.queen = QueenAgent()
        self.tas = MagicMock()
        self.tas.name = "TaskAgent"
        self.crt = MagicMock()
        self.crt.name = "Critic"
        self.crt.review.return_value = {"quality": "pass", "score": 0.9}
        self.queen.set_agents({"TAS": self.tas, "CRT": self.crt})

    def test_synthesis_with_qwen(self):
        with patch.object(self.queen, "_call_qwen", return_value="combined answer") as qwen:
            r = self.queen._critique_and_synthesize("task", {"TAS": "result text"}, ["TAS"])
        self.assertIn("Multi-Agent Analysis", r)
        self.assertIn("combined answer", r)
        prompt = qwen.call_args[0][0]
        self.assertIn("TaskAgent", prompt)  # agent name included in synthesis prompt
        self.assertIn("quality=pass", prompt)
        self.crt.review.assert_called_once()

    def test_critic_exception_fallback(self):
        self.crt.review.side_effect = RuntimeError("critic broke")
        with patch.object(self.queen, "_call_qwen", return_value="answer"):
            r = self.queen._critique_and_synthesize("task", {"TAS": "result text"}, ["TAS"])
        self.assertIn("Multi-Agent Analysis", r)

    def test_qwen_none_joins_results(self):
        with patch.object(self.queen, "_call_qwen", return_value=None):
            r = self.queen._critique_and_synthesize("task", {"TAS": "aaa", "COD": "bbb"}, ["TAS", "COD"])
        self.assertIn("aaa", r)
        self.assertIn("bbb", r)

    def test_qwen_raises_joins_results(self):
        with patch.object(self.queen, "_call_qwen", side_effect=RuntimeError("down")):
            r = self.queen._critique_and_synthesize("task", {"TAS": "aaa"}, ["TAS"])
        self.assertIn("aaa", r)

    def test_missing_result_skipped(self):
        with patch.object(self.queen, "_call_qwen", return_value="s"):
            r = self.queen._critique_and_synthesize("task", {"TAS": "aaa"}, ["TAS", "COD"])
        self.assertNotIn("CodeAgent", r)


class TestSubmitFeedback(unittest.TestCase):
    def setUp(self):
        self.queen = QueenAgent()
        self.si = MagicMock()
        self.am = MagicMock()
        self.patches = [
            patch("orbit.core.self_improvement.get_self_improvement", return_value=self.si),
            patch("orbit.core.agent_awareness.get_awareness_manager", return_value=self.am),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def _scores(self):
        return {c.kwargs["agent_id"]: c.kwargs["score"] for c in self.si.add_feedback.call_args_list}

    def test_good_long_result_high_score(self):
        self.queen._submit_feedback("task", {"TAS": "x" * 120}, ["TAS"])
        self.assertEqual(self._scores()["TAS"], 0.8)

    def test_error_result_low_score(self):
        self.queen._submit_feedback("task", {"TAS": "[TAS error: boom]"}, ["TAS"])
        self.assertEqual(self._scores()["TAS"], 0.1)

    def test_short_result_default_score(self):
        self.queen._submit_feedback("task", {"TAS": "ok"}, ["TAS"])
        self.assertEqual(self._scores()["TAS"], 0.5)

    def test_feedback_import_failure_swallowed(self):
        with patch("orbit.core.self_improvement.get_self_improvement", side_effect=RuntimeError("down")):
            self.queen._submit_feedback("task", {"TAS": "x"}, ["TAS"])  # no raise


class TestDetectIntent(unittest.TestCase):
    def setUp(self):
        self.queen = QueenAgent()

    def test_smartrouter_high_score(self):
        route = MagicMock()
        route.intent = "task"
        route.agents = [MagicMock(score=0.9)]
        with patch("orbit.core.smart_router.auto_route", return_value=route):
            r = self.queen._detect_intent_simple("run command")
        self.assertEqual(r, "task")

    def test_fallback_keyword_or_chat(self):
        with patch("orbit.core.smart_router.auto_route", side_effect=RuntimeError("no router")):
            r = self.queen._detect_intent_simple("open chrome")
        self.assertIsInstance(r, str)
        self.assertTrue(r)


class TestRun(unittest.TestCase):
    def setUp(self):
        self.queen = QueenAgent()
        self.tas = MagicMock()
        self.tas.name = "TaskAgent"
        self.tas.execute.return_value = "done"
        self.queen.set_agents({"TAS": self.tas})
        self.am = MagicMock()
        self.am.journals = {}
        self.awareness_patch = patch(
            "orbit.core.agent_awareness.get_awareness_manager", return_value=self.am
        )
        self.awareness_patch.start()
        self.addCleanup(self.awareness_patch.stop)

    def test_smartrouter_fast_path(self):
        route = MagicMock()
        route.agents = [MagicMock(label="TAS", score=0.9)]
        with patch("orbit.core.smart_router.auto_route", return_value=route):
            r = self.queen.execute("open chrome")
        self.assertEqual(r, "done")

    def test_error_result_falls_through_to_chat(self):
        route = MagicMock()
        route.agents = [MagicMock(label="TAS", score=0.9)]
        self.tas.execute.side_effect = ["[TAS error: x]", "chat reply"]
        self.tas.can_handle.return_value = True
        with patch("orbit.core.smart_router.auto_route", return_value=route), \
             patch.object(self.queen, "_detect_intent_simple", return_value="chat"):
            r = self.queen.execute("hello")
        self.assertEqual(r, "chat reply")

    def test_chat_intent_no_handler_returns_none(self):
        self.queen.set_agents({})
        route = MagicMock()
        route.agents = []
        with patch("orbit.core.smart_router.auto_route", return_value=route), \
             patch.object(self.queen, "_detect_intent_simple", return_value="chat"):
            r = self.queen.execute("just chatting")
        self.assertIsNone(r)

    def test_plan_path_synthesized(self):
        with patch("orbit.core.smart_router.auto_route", side_effect=RuntimeError("no router")), \
             patch.object(self.queen, "_detect_intent_simple", return_value="task"), \
             patch.object(self.queen, "_generate_plan", return_value={"plan": ["TAS"], "reasoning": "r"}), \
             patch.object(self.queen, "_submit_feedback"), \
             patch.object(self.queen, "_call_qwen", return_value="synth text"):
            r = self.queen.execute("do the task")
        self.assertIn("Multi-Agent Analysis", r)
        self.assertIn("synth text", r)
        self.assertEqual(self.queen.get_plan()["plan"], ["TAS"])

    def test_plan_path_no_synth_combined(self):
        self.queen.set_agents({"TAS": self.tas})
        with patch("orbit.core.smart_router.auto_route", side_effect=RuntimeError("no router")), \
             patch.object(self.queen, "_detect_intent_simple", return_value="task"), \
             patch.object(self.queen, "_generate_plan", return_value={"plan": ["TAS"], "synthesize": False}), \
             patch.object(self.queen, "_submit_feedback"):
            r = self.queen.execute("do the task")
        self.assertEqual(r, "[TAS]: done")

    def test_intent_failure_returns_help_message(self):
        with patch("orbit.core.smart_router.auto_route", side_effect=RuntimeError("no router")), \
             patch.object(self.queen, "_detect_intent_simple", side_effect=RuntimeError("intent broke")):
            r = self.queen.execute("anything")
        self.assertEqual(r, "Let me try to help with that.")

    def test_execute_raises_trace_wrapped(self):
        # BaseAgent.execute catches _run exceptions and returns an error string.
        with patch("orbit.core.smart_router.auto_route", side_effect=RuntimeError("no router")), \
             patch.object(self.queen, "_detect_intent_simple", return_value="task"), \
             patch.object(self.queen, "_generate_plan", side_effect=RuntimeError("plan broke")):
            r = self.queen.execute("anything")
        self.assertIn("encountered an error", r)


if __name__ == "__main__":
    unittest.main()
