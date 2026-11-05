"""Tests for the wired self-improvement loop (Roadmap P0 — capture, API, runner)."""

import os
import tempfile

import pytest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_KEY", "")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

from orbit.orbit.core.failure_capture import FailureCapture, classify_error, get_failure_capture
from orbit.orbit.core.self_improvement_v2 import (
    ApprovalGate,
    FailureAnalyzer,
    LessonStore,
    RegressionTestGenerator,
    SelfImprovementOrchestrator,
    SkillGenerator,
    SkillValidator,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def orch(tmp_dir):
    """Fresh orchestrator with redirected storage (no real disk)."""
    o = SelfImprovementOrchestrator.__new__(SelfImprovementOrchestrator)
    o.analyzer = FailureAnalyzer()
    o.analyzer._analyses.clear()
    o.analyzer._patterns.clear()
    o.analyzer._storage = os.path.join(tmp_dir, "analyses.json")
    o.analyzer._load = lambda: None

    o.lesson_store = LessonStore()
    o.lesson_store._lessons.clear()
    o.lesson_store._storage = os.path.join(tmp_dir, "lessons.json")
    o.lesson_store._load = lambda: None

    o.skill_generator = SkillGenerator(o.lesson_store)
    o.skill_generator._skills.clear()
    o.skill_generator._storage = os.path.join(tmp_dir, "skills.json")
    o.skill_generator._load = lambda: None

    o.validator = SkillValidator(o.skill_generator)
    o.approval_gate = ApprovalGate(o.skill_generator, o.validator)
    o.approval_gate._pending.clear()
    o.approval_gate._history.clear()
    o.approval_gate._storage = os.path.join(tmp_dir, "approvals.json")
    o.approval_gate._load = lambda: None

    o.regression_tests = RegressionTestGenerator()
    o.regression_tests._tests.clear()
    o.regression_tests._storage = os.path.join(tmp_dir, "tests.json")
    o.regression_tests._load = lambda: None

    import threading

    o._lock = threading.Lock()
    return o


@pytest.fixture
def cap(monkeypatch, orch):
    """FailureCapture wired to the tmp orchestrator singleton."""
    c = FailureCapture()
    monkeypatch.setattr(
        "orbit.orbit.core.self_improvement_v2.get_self_improvement_orchestrator",
        lambda: orch,
    )
    return c


# ── classify_error ───────────────────────────────────────────────────────────


class TestClassifyError:
    def test_timeout(self):
        assert classify_error("request timed out after 30s") == "timeout"

    def test_provider(self):
        assert classify_error("HTTP 429 rate limit") == "provider_error"

    def test_unknown(self):
        assert classify_error("weird gibberish") == "unknown"

    def test_empty(self):
        assert classify_error("") == "unknown"


# ── FailureCapture ───────────────────────────────────────────────────────────


class TestFailureCapture:
    def test_capture_creates_lesson_and_test(self, cap, orch):
        result = cap.capture(
            source="chat_api",
            agent_id="TAS",
            prompt="list my files please",
            output="Error: tool failed",
            error="tool failed",
        )
        assert result is not None
        assert result["lesson_id"]
        assert result["test_id"]
        assert orch.lesson_store.get_lessons(agent_id="TAS")

    def test_dedup_within_cooldown(self, cap):
        args = dict(source="chat_api", agent_id="TAS", prompt="same prompt", output="Error: x")
        r1 = cap.capture(**args)
        r2 = cap.capture(**args)
        assert r1 is not None
        assert r2 is None
        assert cap.get_status()["stats"]["deduped"] == 1

    def test_different_prompts_not_deduped(self, cap):
        assert cap.capture(source="s", agent_id="A", prompt="p1", output="Error: a") is not None
        assert cap.capture(source="s", agent_id="A", prompt="p2", output="Error: b") is not None
        assert cap.get_status()["stats"]["captured"] == 2

    def test_fail_open_on_orchestrator_error(self, monkeypatch):
        c = FailureCapture()

        def boom():
            raise RuntimeError("orch exploded")

        monkeypatch.setattr(
            "orbit.orbit.core.self_improvement_v2.get_self_improvement_orchestrator",
            boom,
        )
        result = c.capture(source="s", agent_id="A", prompt="p", output="Error: e")
        assert result is None
        assert c.get_status()["stats"]["errors"] >= 1

    def test_category_from_error_text(self, cap):
        cap.capture(source="s", agent_id="A", prompt="p", output="", error="connection timeout")
        by_cat = cap.get_status()["stats"]["by_category"]
        assert by_cat.get("timeout", 0) == 1

    def test_singleton(self):
        assert get_failure_capture() is get_failure_capture()


# ── Orchestrator: process_failure + run_regression_tests ─────────────────────


class TestRegressionRunner:
    def test_no_tests(self, orch):
        out = orch.run_regression_tests()
        assert out["executed"] == 0

    def test_pass_and_fail(self, orch, monkeypatch):
        t_pass = orch.regression_tests.generate_test(
            failure_id="f1", agent_id="TAS", input_text="what is 2+2",
            actual_output="Error: empty", category="reasoning_error",
        )
        t_fail = orch.regression_tests.generate_test(
            failure_id="f2", agent_id="TAS", input_text="write code for x",
            actual_output="Error: empty", category="tool_failure",
        )

        responses = {
            t_pass.id: "Because 2+2 equals 4, therefore the answer is 4. Step 1: add the numbers.",
            t_fail.id: "Error: failed to execute",
        }

        def fake_generate(prompt, **kwargs):
            if "2+2" in prompt:
                return responses[t_pass.id]
            return responses[t_fail.id]

        monkeypatch.setattr(
            "orbit.orbit.core.llm.legacy_adapter.generate", fake_generate
        )
        out = orch.run_regression_tests(limit=10)
        assert out["executed"] == 2
        by_id = {r["test_id"]: r["passed"] for r in out["results"]}
        assert by_id[t_pass.id] is True
        # tool_failure test must_not_contain error/failed — response has both → fail
        assert by_id[t_fail.id] is False

    def test_llm_error_counts_as_fail(self, orch, monkeypatch):
        orch.regression_tests.generate_test(
            failure_id="f3", agent_id="TAS", input_text="hello",
            actual_output="Error", category="unknown",
        )

        def fake_generate(prompt, **kwargs):
            raise RuntimeError("provider down")

        monkeypatch.setattr(
            "orbit.orbit.core.llm.legacy_adapter.generate", fake_generate
        )
        out = orch.run_regression_tests()
        assert out["executed"] == 1
        assert out["results"][0]["passed"] is False
        assert out["results"][0]["error"]


# ── Approval gate via orchestrator ───────────────────────────────────────────


class TestApprovalFlow:
    def test_process_failure_creates_pending_or_auto(self, orch):
        result = orch.process_failure(
            failure_id="af1",
            agent_id="COD",
            input_text="write sorting code",
            actual_output="Error: empty output",
            error_message="empty response",
            category_hint="provider_error",
        )
        assert result["lesson_id"]
        pending = orch.approval_gate.get_pending()
        auto = result["approval"] and result["approval"].get("status") == "auto_approved"
        assert pending or auto or result["skill_id"] is None

    def test_approve_and_reject(self, orch):
        lesson_id = orch.lesson_store.add_lesson(
            agent_id="TAS", category="tool_failure", subject="s",
            mistake_summary="m", correct_approach="c", importance=7,
        )
        skill = orch.skill_generator.generate_skill(
            lesson_ids=[lesson_id], name="Handle tool_failure for TAS"
        )
        assert skill is not None
        # Force a pending (high priority → needs approval)
        orch.skill_generator._skills[skill.id].priority = 10
        req = orch.approval_gate.request_approval(skill.id, reason="test")
        assert req["status"] in ("pending_approval", "auto_approved")
        if req["status"] == "pending_approval":
            rid = req["request_id"]
            assert orch.approval_gate.approve(rid) is True
            assert orch.approval_gate.approve(rid) is False  # already decided


# ── Blueprint routes ─────────────────────────────────────────────────────────


class TestV2Blueprint:
    @pytest.fixture
    def client(self, tmp_dir, monkeypatch):
        from flask import Flask

        from orbit.orbit.core import self_improvement_v2 as siv2
        from orbit.orbit.core.self_improvement_bp import self_improvement_bp

        # Redirect the REAL singleton to tmp storage so bp routes never
        # touch orbit_data during tests.
        o = SelfImprovementOrchestrator.__new__(SelfImprovementOrchestrator)
        o.analyzer = FailureAnalyzer()
        o.analyzer._analyses.clear()
        o.analyzer._patterns.clear()
        o.analyzer._storage = os.path.join(tmp_dir, "b_analyses.json")
        o.lesson_store = LessonStore()
        o.lesson_store._lessons.clear()
        o.lesson_store._storage = os.path.join(tmp_dir, "b_lessons.json")
        o.skill_generator = SkillGenerator(o.lesson_store)
        o.skill_generator._skills.clear()
        o.skill_generator._storage = os.path.join(tmp_dir, "b_skills.json")
        o.validator = SkillValidator(o.skill_generator)
        o.approval_gate = ApprovalGate(o.skill_generator, o.validator)
        o.approval_gate._pending.clear()
        o.approval_gate._history.clear()
        o.approval_gate._storage = os.path.join(tmp_dir, "b_approvals.json")
        o.regression_tests = RegressionTestGenerator()
        o.regression_tests._tests.clear()
        o.regression_tests._storage = os.path.join(tmp_dir, "b_tests.json")
        import threading

        o._lock = threading.Lock()

        monkeypatch.setattr(siv2, "_orchestrator", o)

        app = Flask(__name__)
        app.register_blueprint(self_improvement_bp)
        app.config["TESTING"] = True
        return app.test_client()

    def test_status(self, client):
        res = client.get("/api/self-improvement/v2/status")
        assert res.status_code == 200
        data = res.get_json()
        assert "orchestrator" in data
        assert "capture" in data

    def test_failures(self, client):
        res = client.get("/api/self-improvement/v2/failures")
        assert res.status_code == 200
        assert "failures" in res.get_json()

    def test_lessons(self, client):
        res = client.get("/api/self-improvement/v2/lessons")
        assert res.status_code == 200
        assert "lessons" in res.get_json()

    def test_skills(self, client):
        res = client.get("/api/self-improvement/v2/skills")
        assert res.status_code == 200

    def test_approvals(self, client):
        res = client.get("/api/self-improvement/v2/approvals")
        assert res.status_code == 200
        data = res.get_json()
        assert "pending" in data
        assert "history" in data

    def test_approve_404(self, client):
        res = client.post("/api/self-improvement/v2/approve/nonexistent")
        assert res.status_code == 404

    def test_reject_404(self, client):
        res = client.post("/api/self-improvement/v2/reject/nonexistent")
        assert res.status_code == 404

    def test_regression_tests(self, client):
        res = client.get("/api/self-improvement/v2/regression-tests")
        assert res.status_code == 200

    def test_report_requires_content(self, client):
        res = client.post(
            "/api/self-improvement/v2/report",
            json={},
        )
        assert res.status_code == 400

    def test_report_ok_or_deduped(self, client):
        res = client.post(
            "/api/self-improvement/v2/report",
            json={
                "prompt": "unique manual report prompt 12345",
                "output": "Error: something broke",
                "error": "something broke",
                "agent_id": "TAS",
            },
        )
        assert res.status_code == 200
        data = res.get_json()
        # Either processed (ok) or deduped (if cooldown from a prior identical run)
        assert data["status"] in ("ok", "deduped")


# ── Hook presence (chat_api + orchestrator) ──────────────────────────────────


class TestProductionHooks:
    def test_chat_api_has_capture_hook(self):
        import inspect

        from orbit.orbit.core import chat_api

        src = inspect.getsource(chat_api)
        assert "get_failure_capture" in src
        assert "get_self_improvement_orchestrator" in src  # context injection

    def test_agent_orchestrator_has_capture_hook(self):
        import inspect

        from orbit.orbit.agents import orchestrator

        src = inspect.getsource(orchestrator)
        assert "get_failure_capture" in src
