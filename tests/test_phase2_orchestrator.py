"""
Phase 2 Orchestrator Consolidation tests
========================================
Covers the canonical task runner added in core/orchestrator.py:
- execute() success / failure / retry-with-backoff
- Agent freeing between retries
- Module-level execute_task() helper
- /api/task endpoints
- Battle prompt suite integrity (100 prompts, 5 categories)
"""

import unittest

from orbit.orbit.core.orchestrator import (
    AgentType,
    Orchestrator,
    TaskStatus,
    execute_task,
)


class TestOrchestratorExecute(unittest.TestCase):
    def test_execute_success(self):
        o = Orchestrator()
        t = o.create_task("ok", "do it", AgentType.GENERAL)
        res = o.execute(t.id, executor=lambda task: "done")
        self.assertEqual(res.status, TaskStatus.COMPLETED)
        self.assertEqual(res.result, "done")

    def test_execute_failure_no_retry_needed(self):
        o = Orchestrator()
        o.retry_limit = 1
        t = o.create_task("f", "boom", AgentType.GENERAL)
        res = o.execute(
            t.id, executor=lambda task: (_ for _ in ()).throw(RuntimeError("x"))
        )
        self.assertEqual(res.status, TaskStatus.FAILED)
        self.assertIn("x", res.error or "")

    def test_execute_retries_then_succeeds(self):
        o = Orchestrator()
        o.retry_limit = 3
        calls = {"n": 0}

        def flaky(task):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("boom")
            return "recovered"

        t = o.create_task("r", "flaky", AgentType.GENERAL)
        res = o.execute(t.id, executor=flaky)
        self.assertEqual(res.status, TaskStatus.COMPLETED)
        self.assertEqual(res.result, "recovered")
        self.assertEqual(calls["n"], 2)

    def test_execute_retry_frees_agent(self):
        o = Orchestrator()
        o.retry_limit = 3
        calls = {"n": 0}

        def flaky(task):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("boom")
            return "ok"

        t = o.create_task("free", "agent must be reusable", AgentType.GENERAL)
        res = o.execute(t.id, executor=flaky)
        self.assertEqual(res.status, TaskStatus.COMPLETED)
        agent = o.agents[AgentType.GENERAL]
        self.assertFalse(agent.is_busy)

    def test_execute_unknown_task_raises(self):
        o = Orchestrator()
        with self.assertRaises(ValueError):
            o.execute("nope")

    def test_execute_task_helper(self):
        t = execute_task(
            "h", "helper", AgentType.GENERAL, executor=lambda task: "via helper"
        )
        self.assertEqual(t.status, TaskStatus.COMPLETED)
        self.assertEqual(t.result, "via helper")

    def test_execute_resolves_real_agent(self):
        o = Orchestrator()
        t = o.create_task("real", "hello agent", AgentType.GENERAL)
        res = o.execute(t.id)
        self.assertEqual(res.status, TaskStatus.COMPLETED)
        self.assertIsInstance(res.result, str)

    def test_execute_waiting_approval(self):
        o = Orchestrator()
        t = o.create_task(
            "wait", "needs approval", AgentType.GENERAL, requires_approval=True
        )
        res = o.execute(t.id, executor=lambda task: "never runs")
        self.assertIn(res.status, (TaskStatus.WAITING_APPROVAL, TaskStatus.PENDING))


class TestTaskApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from orbit.orbit.server import create_app

        cls.app = create_app()

    def setUp(self):
        self.client = self.app.test_client()

    def test_task_execute_endpoint(self):
        r = self.client.post(
            "/api/task",
            json={"name": "t", "description": "ping", "agent_type": "general"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn("task_id", body)
        self.assertEqual(body["status"], "completed")

    def test_task_execute_missing_description(self):
        r = self.client.post("/api/task", json={})
        self.assertEqual(r.status_code, 400)

    def test_task_status_endpoint(self):
        r = self.client.post("/api/task", json={"description": "status check"})
        tid = r.get_json()["task_id"]
        r2 = self.client.get(f"/api/task/{tid}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["id"], tid)

    def test_task_status_unknown(self):
        r = self.client.get("/api/task/doesnotexist")
        self.assertEqual(r.status_code, 404)

    def test_task_queue_endpoint(self):
        r = self.client.get("/api/task")
        self.assertEqual(r.status_code, 200)
        self.assertIn("pending", r.get_json())


class TestBattlePrompts(unittest.TestCase):
    def test_120_prompts_6_categories(self):
        from tests.e2e.battle_prompts import BATTLE_PROMPTS, TOTAL_PROMPTS

        self.assertEqual(TOTAL_PROMPTS, 120)
        self.assertEqual(len(BATTLE_PROMPTS), 6)
        for name, prompts in BATTLE_PROMPTS.items():
            self.assertEqual(len(prompts), 20, f"{name} should have 20 prompts")
            for p in prompts:
                if isinstance(p, list):
                    for turn in p:
                        self.assertTrue(len(turn) > 10)
                else:
                    self.assertTrue(len(p) > 10)


if __name__ == "__main__":
    unittest.main()
