"""Deep tests for orbit/orbit/core/agent_coordination.py (Loop 22/5)."""

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import agent_coordination as ac

import sys as _sys
import types as _types
from unittest import mock as _mock
_fake_reg_mod = _types.ModuleType("orbit.orbit.agents.registry")
_fake_reg_mod.get_agent_registry = _mock.MagicMock()
_sys.modules["orbit.orbit.agents.registry"] = _fake_reg_mod
import orbit.orbit.agents as _agents_mod
_agents_mod.registry = _fake_reg_mod


class EnumDataclassTests(unittest.TestCase):
    def test_stage_status(self):
        self.assertEqual(ac.StageStatus.PENDING.value, "pending")
        self.assertEqual(ac.StageStatus.RUNNING.value, "running")
        self.assertEqual(ac.StageStatus.COMPLETED.value, "completed")
        self.assertEqual(ac.StageStatus.FAILED.value, "failed")
        self.assertEqual(ac.StageStatus.SKIPPED.value, "skipped")

    def test_pipeline_status(self):
        self.assertEqual(ac.PipelineStatus.IDLE.value, "idle")
        self.assertEqual(ac.PipelineStatus.RUNNING.value, "running")
        self.assertEqual(ac.PipelineStatus.COMPLETED.value, "completed")
        self.assertEqual(ac.PipelineStatus.FAILED.value, "failed")

    def test_stage_result_defaults(self):
        r = ac.StageResult(stage_name="s", agent="a", status=ac.StageStatus.PENDING)
        self.assertIsNone(r.output)
        self.assertIsNone(r.error)
        self.assertEqual(r.latency_ms, 0)
        self.assertEqual(r.tokens_used, 0)
        self.assertTrue(r.timestamp)

    def test_pipeline_result_defaults(self):
        r = ac.PipelineResult(pipeline_id="p", goal="g", status=ac.PipelineStatus.IDLE)
        self.assertEqual(r.stages, [])
        self.assertIsNone(r.final_output)
        self.assertEqual(r.total_latency_ms, 0)
        self.assertTrue(r.started_at)
        self.assertIsNone(r.completed_at)

    def test_pipeline_stage_defaults(self):
        s = ac.PipelineStage(name="n", agent="a", description="d")
        self.assertEqual(s.depends_on, [])
        self.assertFalse(s.parallel)
        self.assertEqual(s.timeout_seconds, 60)
        self.assertEqual(s.retry_count, 1)
        self.assertTrue(s.required)

    def test_pipeline_templates_exist(self):
        self.assertIn("full_stack_feature", ac.PIPELINE_TEMPLATES)
        self.assertIn("research_report", ac.PIPELINE_TEMPLATES)
        self.assertIn("code_review_fix", ac.PIPELINE_TEMPLATES)
        self.assertIn("security_audit", ac.PIPELINE_TEMPLATES)
        # each template is list of PipelineStage
        for name, stages in ac.PIPELINE_TEMPLATES.items():
            self.assertIsInstance(stages, list)
            for s in stages:
                self.assertIsInstance(s, ac.PipelineStage)


class RehydrateTests(unittest.TestCase):
    def test_rehydrate_full(self):
        p = {"pipeline_id": "p1", "goal": "g", "status": "completed",
             "stages": [{"stage_name": "s1", "agent": "a", "status": "completed",
                         "latency_ms": 10.5, "error": None, "timestamp": "t"}],
             "total_latency_ms": 10.5, "started_at": "s", "completed_at": "c"}
        r = ac.AgentCoordinator._rehydrate(p)
        self.assertEqual(r.pipeline_id, "p1")
        self.assertEqual(r.goal, "g")
        self.assertEqual(r.status, ac.PipelineStatus.COMPLETED)
        self.assertEqual(len(r.stages), 1)
        self.assertEqual(r.stages[0].stage_name, "s1")
        self.assertEqual(r.stages[0].status, ac.StageStatus.COMPLETED)
        self.assertEqual(r.stages[0].latency_ms, 10.5)
        self.assertEqual(r.stages[0].error, None)
        self.assertEqual(r.stages[0].timestamp, "t")
        self.assertEqual(r.total_latency_ms, 10.5)
        self.assertEqual(r.started_at, "s")
        self.assertEqual(r.completed_at, "c")

    def test_rehydrate_unknown_status_fallback_failed(self):
        p = {"pipeline_id": "p1", "status": "bogus"}
        r = ac.AgentCoordinator._rehydrate(p)
        self.assertEqual(r.status, ac.PipelineStatus.FAILED)

    def test_rehydrate_unknown_stage_status_fallback_failed(self):
        p = {"pipeline_id": "p1", "status": "completed",
             "stages": [{"stage_name": "s1", "agent": "a", "status": "bogus"}]}
        r = ac.AgentCoordinator._rehydrate(p)
        self.assertEqual(r.stages[0].status, ac.StageStatus.FAILED)

    def test_rehydrate_empty(self):
        r = ac.AgentCoordinator._rehydrate({})
        self.assertEqual(r.pipeline_id, "")
        self.assertEqual(r.goal, "")
        self.assertEqual(r.status, ac.PipelineStatus.IDLE)
        self.assertEqual(r.stages, [])
        self.assertEqual(r.total_latency_ms, 0)
        self.assertEqual(r.started_at, "")
        self.assertIsNone(r.completed_at)


class InitLoadSaveTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._p = self._d / "pipelines.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self, path=None):
        p = path or self._p
        with mock.patch("orbit.orbit.core.agent_coordination.DATA_DIR" if False else "pathlib.Path.mkdir"):
            # DATA_DIR is computed at import: data_dir() / "agent_coordination"
            pass
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            pass
        # Patch data_dir to return our temp dir's parent
        with mock.patch("orbit.orbit.core.agent_coordination.data_dir" if hasattr(__import__("orbit.orbit.core.agent_coordination", fromlist=["data_dir"]), "data_dir") else "orbit.orbit.core.runtime_paths.data_dir",
                        return_value=self._d):
            m = ac.AgentCoordinator(data_dir=self._d)
        return m

    def test_init_creates_data_dir(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        with mock.patch("pathlib.Path.mkdir") as mk:
            m = ac.AgentCoordinator(data_dir=d)
        mk.assert_called_once_with(parents=True, exist_ok=True)

    def test_load_existing(self):
        self._p.parent.mkdir(parents=True, exist_ok=True)
        self._p.write_text(json.dumps({"pipelines": [
            {"pipeline_id": "p1", "goal": "g", "status": "completed",
             "stages": [], "total_latency_ms": 5, "started_at": "s",
             "completed_at": "c"}]}), encoding="utf-8")
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            m = ac.AgentCoordinator(data_dir=self._p.parent)
        self.assertEqual(len(m._pipelines), 1)
        self.assertEqual(m._pipelines[0].pipeline_id, "p1")

    def test_load_caps_50(self):
        self._p.parent.mkdir(parents=True, exist_ok=True)
        pipes = [{"pipeline_id": f"p{i}", "goal": "g", "status": "completed",
                  "stages": [], "total_latency_ms": 0, "started_at": "s",
                  "completed_at": "c"} for i in range(60)]
        self._p.write_text(json.dumps({"pipelines": pipes}), encoding="utf-8")
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            m = ac.AgentCoordinator(data_dir=self._p.parent)
        self.assertEqual(len(m._pipelines), 50)

    def test_load_corrupt(self):
        self._p.parent.mkdir(parents=True, exist_ok=True)
        self._p.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            m = ac.AgentCoordinator(data_dir=self._p.parent)
        self.assertEqual(m._pipelines, [])

    def test_load_missing(self):
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            m = ac.AgentCoordinator(data_dir=self._p.parent)
        self.assertEqual(m._pipelines, [])

    def test_save_success(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        m = ac.AgentCoordinator(data_dir=d)
        m._pipelines.append(ac.PipelineResult(pipeline_id="p1", goal="g",
                                              status=ac.PipelineStatus.COMPLETED))
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text") as awt:
            m._save()
        awt.assert_called_once()
        # verify JSON content
        call_args = awt.call_args
        content = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("content", "")
        # atomic_write_text signature: atomic_write_text(path, content, encoding=...)
        # call: atomic_write_text(results_file, json.dumps(...), encoding="utf-8")
        content = call_args.args[1]
        data = json.loads(content)
        self.assertEqual(len(data["pipelines"]), 1)
        self.assertEqual(data["pipelines"][0]["pipeline_id"], "p1")

    def test_save_failure_logged(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text",
                        side_effect=OSError("boom")), \
                mock.patch.object(ac, "logger") as lg:
            m = ac.AgentCoordinator(data_dir=d)
            m._save()
        lg.warning.assert_called_once()


class GetTemplatesTests(unittest.TestCase):
    def test_get_templates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            m = ac.AgentCoordinator(data_dir=d)
        t = m.get_templates()
        self.assertIn("full_stack_feature", t)
        self.assertIn("research_report", t)
        self.assertIn("code_review_fix", t)
        self.assertIn("security_audit", t)
        # each template is list of dicts with keys
        for name, stages in t.items():
            self.assertIsInstance(stages, list)
            for s in stages:
                self.assertIn("name", s)
                self.assertIn("agent", s)
                self.assertIn("description", s)
                self.assertIn("depends_on", s)
                self.assertIn("parallel", s)


class ExecuteStageTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            return ac.AgentCoordinator(data_dir=d)

    def test_agent_not_found(self):
        m = self._make()
        registry = mock.MagicMock()
        registry.get.return_value = None
        stage = ac.PipelineStage(name="s1", agent="NOPE", description="d")
        ctx = {"goal": "g", "results": {}}
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry):
            r = m._execute_stage(stage, ctx)
        self.assertEqual(r.stage_name, "s1")
        self.assertEqual(r.agent, "NOPE")
        self.assertEqual(r.status, ac.StageStatus.FAILED)
        self.assertIn("Agent NOPE not found", r.error)
        self.assertGreaterEqual(r.latency_ms, 0)

    def test_success(self):
        m = self._make()
        registry = mock.MagicMock()
        agent = mock.MagicMock()
        registry.get.return_value = agent
        stage = ac.PipelineStage(name="s1", agent="COD", description="d")
        ctx = {"goal": "g", "results": {}}
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value="response text"):
            r = m._execute_stage(stage, ctx)
        self.assertEqual(r.status, ac.StageStatus.COMPLETED)
        self.assertEqual(r.output, "response text")
        self.assertGreaterEqual(r.latency_ms, 0)

    def test_success_non_str_response(self):
        m = self._make()
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        stage = ac.PipelineStage(name="s1", agent="COD", description="d")
        ctx = {"goal": "g", "results": {}}
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value=123):
            r = m._execute_stage(stage, ctx)
        self.assertEqual(r.output, "123")

    def test_prompt_includes_previous_results(self):
        m = self._make()
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        stage = ac.PipelineStage(name="s2", agent="COD", description="d")
        prev_result = ac.StageResult(stage_name="s1", agent="a",
                                     status=ac.StageStatus.COMPLETED,
                                     output="prev output")
        ctx = {"goal": "g", "results": {"s1": prev_result}}
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value="r") as gen:
            m._execute_stage(stage, ctx)
        prompt = gen.call_args.kwargs["prompt"]
        self.assertIn("Goal: g", prompt)
        self.assertIn("Previous stage 's1' output: prev output", prompt)

    def test_prompt_skips_none_output(self):
        m = self._make()
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        stage = ac.PipelineStage(name="s2", agent="COD", description="d")
        prev_result = ac.StageResult(stage_name="s1", agent="a",
                                     status=ac.StageStatus.COMPLETED,
                                     output=None)
        ctx = {"goal": "g", "results": {"s1": prev_result}}
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value="r") as gen:
            m._execute_stage(stage, ctx)
        prompt = gen.call_args.kwargs["prompt"]
        self.assertNotIn("Previous stage", prompt)

    def test_exception(self):
        m = self._make()
        registry = mock.MagicMock()
        registry.get.side_effect = RuntimeError("boom")
        stage = ac.PipelineStage(name="s1", agent="COD", description="d")
        ctx = {"goal": "g", "results": {}}
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry):
            r = m._execute_stage(stage, ctx)
        self.assertEqual(r.status, ac.StageStatus.FAILED)
        self.assertEqual(r.error, "boom")
        self.assertGreaterEqual(r.latency_ms, 0)


class RunPipelineTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            return ac.AgentCoordinator(data_dir=d)

    def test_unknown_template(self):
        m = self._make()
        r = m.run_pipeline("nope", "goal")
        self.assertEqual(r.pipeline_id, "")
        self.assertEqual(r.goal, "goal")
        self.assertEqual(r.status, ac.PipelineStatus.FAILED)
        self.assertEqual(r.stages, [])

    def test_single_stage_success(self):
        m = self._make()
        # create a single-stage template
        ac.PIPELINE_TEMPLATES["single"] = [ac.PipelineStage("s1", "COD", "d")]
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value="output"), \
                mock.patch.object(m, "_save"):
            r = m.run_pipeline("single", "my goal")
        self.assertEqual(r.status, ac.PipelineStatus.COMPLETED)
        self.assertEqual(len(r.stages), 1)
        self.assertEqual(r.stages[0].status, ac.StageStatus.COMPLETED)
        self.assertEqual(r.final_output, "output")
        self.assertGreaterEqual(r.total_latency_ms, 0)
        self.assertTrue(r.completed_at)
        # active cleared
        self.assertIsNone(m.get_active())
        # persisted
        self.assertEqual(len(m._pipelines), 1)
        # cleanup
        del ac.PIPELINE_TEMPLATES["single"]

    def test_required_stage_failure_stops(self):
        m = self._make()
        ac.PIPELINE_TEMPLATES["single"] = [ac.PipelineStage("s1", "COD", "d", required=True)]
        registry = mock.MagicMock()
        registry.get.return_value = None  # agent not found -> failed
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch.object(m, "_save"):
            r = m.run_pipeline("single", "g")
        self.assertEqual(r.status, ac.PipelineStatus.FAILED)
        self.assertEqual(len(r.stages), 1)
        self.assertEqual(r.stages[0].status, ac.StageStatus.FAILED)
        del ac.PIPELINE_TEMPLATES["single"]

    def test_non_required_stage_failure_continues(self):
        m = self._make()
        ac.PIPELINE_TEMPLATES["two"] = [
            ac.PipelineStage("s1", "COD", "d", required=False),
            ac.PipelineStage("s2", "COD", "d2", depends_on=["s1"], required=True),
        ]
        registry = mock.MagicMock()
        # first stage: agent not found -> failed (non-required, continue)
        # second stage: agent found -> success
        registry.get.side_effect = [None, mock.MagicMock()]
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value="out"), \
                mock.patch.object(m, "_save"):
            r = m.run_pipeline("two", "g")
        self.assertEqual(r.status, ac.PipelineStatus.COMPLETED)
        self.assertEqual(len(r.stages), 2)
        del ac.PIPELINE_TEMPLATES["two"]

    def test_deadlock(self):
        m = self._make()
        # stage depends on non-existent stage -> never ready
        ac.PIPELINE_TEMPLATES["dead"] = [
            ac.PipelineStage("s1", "COD", "d", depends_on=["ghost"]),
        ]
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch.object(m, "_save"):
            r = m.run_pipeline("dead", "g")
        self.assertEqual(r.status, ac.PipelineStatus.FAILED)
        del ac.PIPELINE_TEMPLATES["dead"]

    def test_parallel_stages(self):
        m = self._make()
        ac.PIPELINE_TEMPLATES["par"] = [
            ac.PipelineStage("s1", "COD", "d", parallel=True),
            ac.PipelineStage("s2", "COD", "d2", parallel=True),
        ]
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value="out"), \
                mock.patch.object(m, "_save"):
            r = m.run_pipeline("par", "g")
        self.assertEqual(r.status, ac.PipelineStatus.COMPLETED)
        self.assertEqual(len(r.stages), 2)
        del ac.PIPELINE_TEMPLATES["par"]

    def test_exception_in_run(self):
        m = self._make()
        ac.PIPELINE_TEMPLATES["single"] = [ac.PipelineStage("s1", "COD", "d")]
        # make get_agent_registry raise
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(m, "_save"):
            r = m.run_pipeline("single", "g")
        self.assertEqual(r.status, ac.PipelineStatus.FAILED)
        del ac.PIPELINE_TEMPLATES["single"]

    def test_cap_pipelines_100(self):
        m = self._make()
        m._pipelines = [ac.PipelineResult(pipeline_id=f"p{i}", goal="g",
                                          status=ac.PipelineStatus.COMPLETED)
                        for i in range(100)]
        ac.PIPELINE_TEMPLATES["single"] = [ac.PipelineStage("s1", "COD", "d")]
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value="out"), \
                mock.patch.object(m, "_save"):
            m.run_pipeline("single", "g")
        self.assertEqual(len(m._pipelines), 100)
        del ac.PIPELINE_TEMPLATES["single"]

    def test_context_passed(self):
        m = self._make()
        ac.PIPELINE_TEMPLATES["single"] = [ac.PipelineStage("s1", "COD", "d")]
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value="out") as gen, \
                mock.patch.object(m, "_save"):
            r = m.run_pipeline("single", "g", context={"extra": "val"})
        self.assertEqual(r.status, ac.PipelineStatus.COMPLETED)
        # context merged into ctx (goal + results + extra)
        del ac.PIPELINE_TEMPLATES["single"]

    def test_no_stages_final_output_none(self):
        # a template with one stage whose output is None
        m = self._make()
        ac.PIPELINE_TEMPLATES["single"] = [ac.PipelineStage("s1", "COD", "d")]
        registry = mock.MagicMock()
        registry.get.return_value = mock.MagicMock()
        with mock.patch("orbit.orbit.agents.registry.get_agent_registry",
                        return_value=registry), \
                mock.patch("orbit.orbit.core.llm.legacy_adapter.generate",
                           return_value=None), \
                mock.patch.object(m, "_save"):
            r = m.run_pipeline("single", "g")
        self.assertEqual(r.final_output, "None")


class GetActiveHistoryStatsTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            return ac.AgentCoordinator(data_dir=d)

    def test_get_active_none(self):
        m = self._make()
        self.assertIsNone(m.get_active())

    def test_get_active_with_pipeline(self):
        m = self._make()
        r = ac.PipelineResult(pipeline_id="p1", goal="g",
                              status=ac.PipelineStatus.RUNNING)
        r.stages = [ac.StageResult("s1", "a", ac.StageStatus.COMPLETED)]
        m._active_pipeline = r
        a = m.get_active()
        self.assertEqual(a["pipeline_id"], "p1")
        self.assertEqual(a["goal"], "g")
        self.assertEqual(a["status"], "running")
        self.assertEqual(a["stages_completed"], 1)
        self.assertEqual(a["stages_total"], 1)

    def test_get_history_empty(self):
        m = self._make()
        self.assertEqual(m.get_history(), [])

    def test_get_history(self):
        m = self._make()
        r = ac.PipelineResult(pipeline_id="p1", goal="g", status=ac.PipelineStatus.COMPLETED,
                              stages=[ac.StageResult("s1", "a", ac.StageStatus.COMPLETED)],
                              total_latency_ms=10.5, started_at="s")
        m._pipelines.append(r)
        h = m.get_history(limit=10)
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["pipeline_id"], "p1")
        self.assertEqual(h[0]["goal"], "g")
        self.assertEqual(h[0]["status"], "completed")
        self.assertEqual(h[0]["stages"], 1)
        self.assertEqual(h[0]["total_latency_ms"], 10.5)
        self.assertEqual(h[0]["started_at"], "s")

    def test_get_history_limit(self):
        m = self._make()
        for i in range(5):
            m._pipelines.append(ac.PipelineResult(pipeline_id=f"p{i}", goal="g",
                                                  status=ac.PipelineStatus.COMPLETED))
        h = m.get_history(limit=2)
        self.assertEqual(len(h), 2)

    def test_get_stats_empty(self):
        m = self._make()
        self.assertEqual(m.get_stats(), {"total_pipelines": 0})

    def test_get_stats_populated(self):
        m = self._make()
        m._pipelines = [
            ac.PipelineResult("p1", "g", ac.PipelineStatus.COMPLETED, total_latency_ms=100),
            ac.PipelineResult("p2", "g", ac.PipelineStatus.FAILED, total_latency_ms=50),
        ]
        s = m.get_stats()
        self.assertEqual(s["total_pipelines"], 2)
        self.assertEqual(s["completed"], 1)
        self.assertEqual(s["failed"], 1)
        self.assertEqual(s["success_rate"], 50.0)
        self.assertEqual(s["avg_latency_ms"], 75.0)
        self.assertIn("full_stack_feature", s["templates"])


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = ac._coordinator
        ac._coordinator = None
        self.addCleanup(setattr, ac, "_coordinator", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            a = ac.get_coordinator()
        self.assertIsInstance(a, ac.AgentCoordinator)
        self.assertIs(ac._coordinator, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.agent_coordination.atomic_write_text"):
            a = ac.get_coordinator()
            b = ac.get_coordinator()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
