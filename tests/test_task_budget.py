"""Tests for TaskBudget + semantic loop detection + orchestrator enforcement
+ observability wiring (Roadmap P2-finalize + P3-enforcement, 2026-10-23)."""

import json
import time
from pathlib import Path

import pytest

from orbit.orbit.core.task_budget import BudgetLimits, TaskBudget, get_task_budget


@pytest.fixture
def budget():
    b = TaskBudget(BudgetLimits())
    return b


class TestBudgetLimits:
    def test_defaults_positive(self):
        lim = BudgetLimits()
        assert lim.max_iterations > 0
        assert lim.max_runtime_s > 0
        assert lim.max_retries >= 0
        assert lim.max_tool_calls > 0
        assert lim.max_agent_hops > 0
        assert lim.semantic_loop_threshold >= 2

    def test_as_dict_has_all_keys(self):
        d = BudgetLimits().as_dict()
        for k in (
            "max_iterations",
            "max_runtime_s",
            "max_retries",
            "max_cost_usd",
            "max_tool_calls",
            "max_agent_hops",
            "semantic_loop_threshold",
        ):
            assert k in d


class TestBudgetCounters:
    def test_record_iteration_increments(self, budget):
        budget.record_iteration("t1", cost_usd=0.01)
        budget.record_iteration("t1", cost_usd=0.02)
        u = budget.get_task("t1")
        assert u["iterations"] == 2
        assert u["cost_usd"] == pytest.approx(0.03, abs=1e-6)

    def test_record_retry_tool_hop(self, budget):
        budget.record_retry("t1")
        budget.record_tool_call("t1")
        budget.record_tool_call("t1")
        budget.record_agent_hop("t1")
        u = budget.get_task("t1")
        assert u["retries"] == 1
        assert u["tool_calls"] == 2
        assert u["agent_hops"] == 1

    def test_negative_cost_clamped(self, budget):
        budget.record_iteration("t1", cost_usd=-5.0)
        assert budget.get_task("t1")["cost_usd"] == 0.0

    def test_finish_moves_to_ring(self, budget):
        budget.record_iteration("t1")
        budget.finish("t1")
        assert "t1" not in budget.get_active()
        assert budget.get_task("t1") is not None  # still readable

    def test_finished_ring_prune(self, budget):
        for i in range(budget._max_finished + 5):
            budget.record_iteration(f"t{i}")
            budget.finish(f"t{i}")
        assert len(budget._finished) <= budget._max_finished

    def test_unknown_task_returns_none(self, budget):
        assert budget.get_task("nope") is None


class TestCheckReasons:
    def test_no_active_task_allowed(self, budget):
        assert budget.check("x")["allowed"] is True

    def test_allowed_with_usage_and_remaining(self, budget):
        budget.record_iteration("t1")
        r = budget.check("t1")
        assert r["allowed"] is True
        assert "usage" in r and "remaining" in r
        assert r["remaining"]["iterations"] == budget.limits.max_iterations - 1

    def test_max_iterations_blocks(self, budget):
        for _ in range(budget.limits.max_iterations):
            budget.record_iteration("t1")
        r = budget.check("t1")
        assert r["allowed"] is False
        assert r["reason"] == "max_iterations"

    def test_max_retries_blocks(self, budget):
        for _ in range(budget.limits.max_retries):
            budget.record_retry("t1")
        assert budget.check("t1")["reason"] == "max_retries"

    def test_max_tool_calls_blocks(self, budget):
        for _ in range(budget.limits.max_tool_calls):
            budget.record_tool_call("t1")
        assert budget.check("t1")["reason"] == "max_tool_calls"

    def test_max_agent_hops_blocks(self, budget):
        for _ in range(budget.limits.max_agent_hops):
            budget.record_agent_hop("t1")
        assert budget.check("t1")["reason"] == "max_agent_hops"

    def test_max_cost_blocks(self, budget):
        budget.record_iteration("t1", cost_usd=budget.limits.max_cost_usd + 0.1)
        assert budget.check("t1")["reason"] == "max_cost"

    def test_max_runtime_blocks(self, budget):
        budget.record_iteration("t1")  # create usage
        budget._tasks["t1"].started_at = time.time() - budget.limits.max_runtime_s - 1
        assert budget.check("t1")["reason"] == "max_runtime"

    def test_blocked_reason_sticky(self, budget):
        for _ in range(budget.limits.max_iterations):
            budget.record_iteration("t1")
        budget.check("t1")
        assert budget.get_task("t1")["iterations"] == budget.limits.max_iterations


class TestSemanticLoop:
    def test_three_identical_actions_detects(self, budget):
        n = budget.limits.semantic_loop_threshold
        for _ in range(n):
            budget.record_action("t1", "TAS", "file.write", "wrote x.txt")
        assert budget.get_task("t1")["loop_detected"] is True

    def test_different_results_no_detect(self, budget):
        for i in range(budget.limits.semantic_loop_threshold + 2):
            budget.record_action("t1", "TAS", "file.write", f"wrote x{i}.txt")
        assert budget.get_task("t1")["loop_detected"] is False

    def test_loop_blocks_check(self, budget):
        n = budget.limits.semantic_loop_threshold
        for _ in range(n):
            budget.record_action("t1", "RES", "web.search", "same")
        r = budget.check("t1")
        assert r["allowed"] is False
        assert r["reason"] == "semantic_loop"

    def test_result_truncated_for_hash(self, budget):
        long_a = "x" * 1000
        long_b = "x" * 1000 + "DIFFERENT"
        budget.record_action("t1", "A", "act", long_a)
        budget.record_action("t1", "A", "act", long_b)
        # first 300 chars identical -> same hash -> count 2 (not yet loop)
        assert budget.get_task("t1")["loop_detected"] is False
        budget.record_action("t1", "A", "act", long_a)
        assert budget.get_task("t1")["loop_detected"] is True


class TestFailOpen:
    def test_check_survives_broken_internal(self, budget):
        # Unhashable task_id -> dict.get raises TypeError -> fail-open allow
        r = budget.check([])  # type: ignore[arg-type]
        assert r["allowed"] is True
        assert r["reason"] == "fail_open"

    def test_record_methods_never_raise(self, budget):
        # broken limits threshold (negative) must not raise
        budget._limits.semantic_loop_threshold = 0  # every hit "exceeds" but >=0 always true
        budget.record_action("t1", "A", "a", "r")  # must not raise
        assert budget.get_task("t1")["loop_detected"] is True


class TestSetLimits:
    def test_set_limits_updates(self, budget):
        new = budget.set_limits(max_iterations=3, max_retries=1)
        assert new["max_iterations"] == 3
        assert budget.limits.max_retries == 1

    def test_set_limits_ignores_type_mismatch(self, budget):
        old = budget.limits.max_iterations
        new = budget.set_limits(max_iterations="not-an-int")
        assert new["max_iterations"] == old


# ── Orchestrator enforcement ────────────────────────────────────────────────


class _StubPlanner:
    def __init__(self, subtasks):
        self._subtasks = subtasks

    def execute(self, task):
        return json.dumps({"subtasks": self._subtasks, "parallel": False})


class _StubExecutor:
    def __init__(self, result="ok result"):
        self.result = result
        self.calls = 0

    def execute_subtask(self, subtask, context):
        self.calls += 1
        return self.result


class _StubCritic:
    MAX_RETRIES = 2

    def review(self, subtask, result, attempt):
        return {"quality": "pass", "score": 0.9, "feedback": "", "suggested_fix": ""}

    def needs_retry(self, verdict, attempt):
        return False


class _StubMemory:
    def save_result(self, *a, **k):
        pass


def _make_orchestrator(subtasks, result="ok result"):
    from orbit.orbit.agents.orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator(assistant=None)
    orch.planner = _StubPlanner(subtasks)
    orch.executor = _StubExecutor(result)
    orch.critic = _StubCritic()
    orch.memory = _StubMemory()
    return orch


@pytest.fixture(autouse=True)
def _fresh_budget(monkeypatch):
    b = TaskBudget(BudgetLimits())
    monkeypatch.setattr("orbit.orbit.core.task_budget._budget", b)
    yield b


class TestOrchestratorEnforcement:
    def test_two_subtasks_blocked_at_second_by_iterations(self, monkeypatch):
        monkeypatch.setattr("orbit.orbit.core.task_budget._budget", None)
        b = TaskBudget(BudgetLimits(max_iterations=1))
        monkeypatch.setattr("orbit.orbit.core.task_budget._budget", b)
        subtasks = [{"id": 1, "type": "ask", "description": "a"}, {"id": 2, "type": "ask", "description": "b"}]
        orch = _make_orchestrator(subtasks)
        out = orch.run("do things", task_id=42)
        # first subtask runs (iter 0 -> allowed, then 1); second blocked
        assert orch.executor.calls == 1
        assert out["status"] == "budget_exhausted"
        blocked = [s for s in out["steps"] if s.get("blocked")]
        assert blocked and blocked[0]["blocked"] == "max_iterations"

    def test_normal_run_status_completed(self, monkeypatch):
        b = TaskBudget(BudgetLimits())
        monkeypatch.setattr("orbit.orbit.core.task_budget._budget", b)
        orch = _make_orchestrator([{"id": 1, "type": "ask", "description": "a"}])
        out = orch.run("task", task_id=7)
        assert out["status"] == "completed"
        assert out["budget"]["iterations"] == 1
        assert out["budget"]["agent_hops"] == 1

    def test_semantic_loop_flips_status(self, monkeypatch):
        b = TaskBudget(BudgetLimits(semantic_loop_threshold=2))
        monkeypatch.setattr("orbit.orbit.core.task_budget._budget", b)
        # identical type+result across 3 subtasks -> loop at 2nd, blocked at 3rd
        subtasks = [{"id": i, "type": "memory", "description": f"s{i}"} for i in range(1, 4)]
        orch = _make_orchestrator(subtasks, result="SAME RESULT")
        out = orch.run("task", task_id=9)
        assert out["status"] == "loop_detected"
        # third dispatch blocked by semantic_loop
        blocked = [s for s in out["steps"] if s.get("blocked")]
        assert blocked and blocked[0]["blocked"] == "semantic_loop"

    def test_broken_budget_module_never_bricks(self, monkeypatch):
        class BrokenBudget:
            def check(self, task_id):
                raise RuntimeError("exploded")

            def record_iteration(self, *a, **k):
                raise RuntimeError("exploded")

            def record_agent_hop(self, *a, **k):
                raise RuntimeError("exploded")

            def record_action(self, *a, **k):
                raise RuntimeError("exploded")

            def record_retry(self, *a, **k):
                raise RuntimeError("exploded")

            def get_task(self, *a, **k):
                raise RuntimeError("exploded")

            def finish(self, *a, **k):
                raise RuntimeError("exploded")

        monkeypatch.setattr("orbit.orbit.core.task_budget._budget", BrokenBudget())
        orch = _make_orchestrator([{"id": 1, "type": "ask", "description": "a"}])
        out = orch.run("task", task_id=1)
        assert out["status"] == "completed"
        assert orch.executor.calls == 1


# ── Observability wiring (hook-presence + live feed) ────────────────────────


class TestObservabilityWiring:
    def test_chat_api_records_observability(self):
        src = Path("orbit/orbit/core/chat_api.py").read_text(encoding="utf-8")
        assert "get_observability" in src
        assert "record_task" in src
        assert "record_routing" in src

    def test_policy_engine_records_tool(self):
        src = Path("orbit/orbit/core/policy_engine.py").read_text(encoding="utf-8")
        assert "record_tool" in src

    def test_dashboard_records_and_aggregates(self, tmp_path):
        from orbit.orbit.core.observability import ObservabilityDashboard

        obs = ObservabilityDashboard(data_dir=tmp_path / "obs")
        obs.record_routing("what is 2+2", "QNT", True, 0.9)
        obs.record_routing("capital of france", "RES", False, 0.4)
        obs.record_task("t1", True, 120.0, "TAS")
        obs.record_task("t2", False, 340.0, "RES")
        obs.record_tool("file.read", True, 5.0, "TAS")
        obs.record_tool("file.write", False, 9.0, "TAS")
        d = obs.get_dashboard()
        assert d["routing"]["total"] == 2
        assert d["routing"]["accuracy"] == 50.0  # percent
        assert d["tasks"]["total"] == 2
        # tools is per-tool dict: {"file.read": {"total": 1, ...}, ...}
        assert sum(v["total"] for v in d["tools"].values()) == 2
        assert d["tools"]["file.read"]["success"] == 1
        assert d["tools"]["file.write"]["success"] == 0


# ── Budget API routes ───────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch, tmp_path):
    from flask import Flask

    from orbit.orbit.core.loop_detector_bp import loop_detector_bp

    app = Flask(__name__)
    app.register_blueprint(loop_detector_bp)
    b = TaskBudget(BudgetLimits())
    monkeypatch.setattr("orbit.orbit.core.task_budget._budget", b)
    return app.test_client()


class TestBudgetRoutes:
    def test_limits(self, client):
        r = client.get("/api/loops/budget/limits")
        assert r.status_code == 200
        assert "max_iterations" in r.get_json()

    def test_all_active(self, client):
        r = client.get("/api/loops/budget")
        assert r.status_code == 200
        data = r.get_json()
        assert "stats" in data and "active" in data

    def test_single_task_404(self, client):
        r = client.get("/api/loops/budget/ghost")
        assert r.status_code == 404

    def test_single_task_usage(self, client):
        get_task_budget().record_iteration("t9")
        r = client.get("/api/loops/budget/t9")
        assert r.status_code == 200
        assert r.get_json()["usage"]["iterations"] == 1

    def test_reset_single(self, client):
        get_task_budget().record_iteration("t1")
        r = client.post("/api/loops/budget/reset", json={"task_id": "t1"})
        assert r.status_code == 200
        assert get_task_budget().get_active() == {}

    def test_reset_limits(self, client):
        r = client.post("/api/loops/budget/reset", json={"limits": {"max_iterations": 5}})
        assert r.status_code == 200
        assert r.get_json()["limits"]["max_iterations"] == 5

    def test_reset_all(self, client):
        get_task_budget().record_iteration("t1")
        r = client.post("/api/loops/budget/reset", json={})
        assert r.status_code == 200
        assert get_task_budget().get_active() == {}
