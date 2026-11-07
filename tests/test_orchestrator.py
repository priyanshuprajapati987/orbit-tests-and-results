"""Unit tests for orbit/orbit/agents/orchestrator.py (planner/executor/critic/LLM mocked)."""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.orchestrator import PipelineOrchestrator


def _plan(subtasks, parallel=False):
    return json.dumps({"subtasks": subtasks, "parallel": parallel})


PASS_VERDICT = {"quality": "pass", "score": 0.9, "feedback": "ok", "suggested_fix": ""}
FAIL_VERDICT = {"quality": "fail", "score": 0.1, "feedback": "bad", "suggested_fix": "fix it"}


class TestPipelineOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orch = PipelineOrchestrator()

    def test_instantiation(self):
        self.assertIsNotNone(self.orch.planner)
        self.assertIsNotNone(self.orch.executor)
        self.assertIsNotNone(self.orch.memory)
        self.assertIsNotNone(self.orch.critic)

    def test_set_callback_and_emit(self):
        calls = []
        self.orch.set_callback(lambda stage, msg: calls.append(stage))
        self.orch._emit("planning", "x")
        self.assertEqual(calls, ["planning"])

    def test_emit_no_callback(self):
        self.orch._emit("x", "y")  # no crash

    @patch("orbit.agents.orchestrator.llm_router.generate", return_value="synth summary")
    def test_run_sequential_pass(self, _gen):
        with patch.object(self.orch.planner, "execute", return_value=_plan([{"id": 1, "type": "memory", "description": "d", "dependencies": []}])):
            with patch.object(self.orch.executor, "execute_subtask", return_value="step output"):
                with patch.object(self.orch.critic, "review", return_value=PASS_VERDICT):
                    with patch.object(self.orch.critic, "needs_retry", return_value=False):
                        r = self.orch.run("do a task", task_id=12345)
        self.assertEqual(r["task_id"], 12345)
        self.assertEqual(r["status"], "completed")
        self.assertEqual(len(r["steps"]), 1)
        self.assertEqual(r["steps"][0]["quality"], "pass")
        self.assertTrue(r["result"])

    def test_run_auto_task_id(self):
        with patch.object(self.orch.planner, "execute", return_value=_plan([{"id": 1, "type": "memory", "description": "d"}])):
            with patch.object(self.orch.executor, "execute_subtask", return_value="o"):
                with patch.object(self.orch.critic, "review", return_value=PASS_VERDICT):
                    with patch.object(self.orch.critic, "needs_retry", return_value=False):
                        with patch("orbit.agents.orchestrator.llm_router.generate", return_value="s"):
                            r = self.orch.run("t")
        self.assertIsInstance(r["task_id"], int)

    def test_run_invalid_plan_json_fallback(self):
        with patch.object(self.orch.planner, "execute", return_value="not json at all"):
            with patch.object(self.orch.executor, "execute_subtask", return_value="o"):
                with patch.object(self.orch.critic, "review", return_value=PASS_VERDICT):
                    with patch.object(self.orch.critic, "needs_retry", return_value=False):
                        with patch("orbit.agents.orchestrator.llm_router.generate", return_value="s"):
                            r = self.orch.run("task text")
        self.assertEqual(r["status"], "completed")
        self.assertGreaterEqual(len(r["steps"]), 1)

    def test_run_empty_subtasks_fallback(self):
        with patch.object(self.orch.planner, "execute", return_value=_plan([])):
            with patch.object(self.orch.executor, "execute_subtask", return_value="o"):
                with patch.object(self.orch.critic, "review", return_value=PASS_VERDICT):
                    with patch.object(self.orch.critic, "needs_retry", return_value=False):
                        with patch("orbit.agents.orchestrator.llm_router.generate", return_value="s"):
                            r = self.orch.run("task text")
        self.assertEqual(len(r["steps"]), 1)

    def test_run_retry_until_pass(self):
        with patch.object(self.orch.planner, "execute", return_value=_plan([{"id": 1, "type": "code", "description": "d"}])):
            with patch.object(self.orch.executor, "execute_subtask", return_value="code here"):
                with patch.object(self.orch.critic, "review", side_effect=[FAIL_VERDICT, PASS_VERDICT]):
                    with patch.object(self.orch.critic, "needs_retry", side_effect=[True, False]):
                        with patch("orbit.agents.orchestrator.llm_router.generate", return_value="s"):
                            r = self.orch.run("task")
        self.assertEqual(r["steps"][0]["attempt"], 2)

    def test_run_parallel(self):
        subtasks = [{"id": 1, "type": "memory", "description": "a"}, {"id": 2, "type": "memory", "description": "b"}]
        with patch.object(self.orch.planner, "execute", return_value=_plan(subtasks, parallel=True)):
            with patch.object(self.orch.executor, "execute_subtask", return_value="o"):
                with patch.object(self.orch.critic, "review", return_value=PASS_VERDICT):
                    with patch.object(self.orch.critic, "needs_retry", return_value=False):
                        with patch("orbit.agents.orchestrator.llm_router.generate", return_value="s"):
                            r = self.orch.run("task")
        self.assertEqual(r["status"], "completed")
        self.assertEqual(len(r["steps"]), 2)

    def test_synthesize_no_steps(self):
        self.assertEqual(self.orch._synthesize("t", []), "No steps executed.")

    def test_synthesize_all_fail(self):
        steps = [{"id": 1, "type": "code", "result": "x", "quality": "fail"}]
        r = self.orch._synthesize("t", steps)
        self.assertIn("All steps failed", r)

    def test_synthesize_pass_join_fallback(self):
        steps = [{"id": 1, "type": "code", "result": "res1", "quality": "pass"}]
        with patch("orbit.agents.orchestrator.llm_router.generate", return_value=None):
            r = self.orch._synthesize("t", steps)
        self.assertIn("res1", r)

    def test_get_result_wrong_task(self):
        self.assertEqual(self.orch.get_result(999), {})

    def test_clear_results(self):
        self.orch._results[1] = {"a": 1}
        self.orch.clear_results()
        self.assertEqual(self.orch._results, {})

    def test_callback_stages_emitted(self):
        stages = []
        self.orch.set_callback(lambda s, m: stages.append(s))
        with patch.object(self.orch.planner, "execute", return_value=_plan([{"id": 1, "type": "memory", "description": "d"}])):
            with patch.object(self.orch.executor, "execute_subtask", return_value="o"):
                with patch.object(self.orch.critic, "review", return_value=PASS_VERDICT):
                    with patch.object(self.orch.critic, "needs_retry", return_value=False):
                        with patch("orbit.agents.orchestrator.llm_router.generate", return_value="s"):
                            self.orch.run("t", task_id=7)
        self.assertIn("planning", stages)
        self.assertIn("synthesizing", stages)


if __name__ == "__main__":
    unittest.main()
