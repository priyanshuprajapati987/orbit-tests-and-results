"""Deep tests for orbit/orbit/core/reasoning_engine.py (Loop 19/4)."""

import json
import random
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import reasoning_engine as re_mod


class ReasoningStepTests(unittest.TestCase):
    def test_defaults(self):
        s = re_mod.ReasoningStep("thought")
        self.assertEqual(s.thought, "thought")
        self.assertEqual(s.confidence, 0.0)
        self.assertEqual(s.action, "")
        self.assertEqual(s.observation, "")
        self.assertTrue(s.id)
        self.assertTrue(s.timestamp)

    def test_confidence_clamped(self):
        s = re_mod.ReasoningStep("t", confidence=150.0)
        self.assertEqual(s.confidence, 100.0)
        s2 = re_mod.ReasoningStep("t", confidence=-5.0)
        self.assertEqual(s2.confidence, 0.0)

    def test_to_dict(self):
        s = re_mod.ReasoningStep("t", confidence=50.0, action="a", observation="o")
        d = s.to_dict()
        self.assertEqual(d["thought"], "t")
        self.assertEqual(d["confidence"], 50.0)
        self.assertEqual(d["action"], "a")
        self.assertEqual(d["observation"], "o")
        self.assertEqual(d["id"], s.id)
        self.assertEqual(d["timestamp"], s.timestamp)


class ReasoningTraceTests(unittest.TestCase):
    def test_defaults(self):
        t = re_mod.ReasoningTrace("task", "direct")
        self.assertEqual(t.task, "task")
        self.assertEqual(t.strategy, "direct")
        self.assertEqual(t.steps, [])
        self.assertEqual(t.answer, "")
        self.assertEqual(t.final_confidence, 0.0)
        self.assertEqual(t.completed_at, "")
        self.assertEqual(t.elapsed_ms, 0.0)
        self.assertTrue(t.id)
        self.assertTrue(t.started_at)

    def test_add_step(self):
        t = re_mod.ReasoningTrace("task", "direct")
        s = re_mod.ReasoningStep("thought")
        t.add_step(s)
        self.assertEqual(len(t.steps), 1)
        self.assertIs(t.steps[0], s)

    def test_to_dict(self):
        t = re_mod.ReasoningTrace("task", "direct")
        t.add_step(re_mod.ReasoningStep("s1"))
        t.answer = "ans"
        t.final_confidence = 80.0
        t.completed_at = "2026-01-01"
        t.elapsed_ms = 12.5
        d = t.to_dict()
        self.assertEqual(d["task"], "task")
        self.assertEqual(d["strategy"], "direct")
        self.assertEqual(len(d["steps"]), 1)
        self.assertEqual(d["answer"], "ans")
        self.assertEqual(d["final_confidence"], 80.0)
        self.assertEqual(d["completed_at"], "2026-01-01")
        self.assertEqual(d["elapsed_ms"], 12.5)


class InitLoadSaveTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self._path = self._d / "traces.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", self._d):
            e = re_mod.ReasoningEngine()
        return e

    def test_init_creates_data_dir(self):
        with mock.patch("pathlib.Path.mkdir") as mk:
            with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", Path("/tmp/x")):
                e = re_mod.ReasoningEngine()
        mk.assert_called_once_with(parents=True, exist_ok=True)

    def test_load_existing(self):
        self._path.write_text('[{"id":"t1","strategy":"direct"}]', encoding="utf-8")
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", self._d):
            e = re_mod.ReasoningEngine()
        self.assertEqual(len(e._traces), 1)
        self.assertEqual(e._traces[0]["id"], "t1")

    def test_load_corrupt(self):
        self._path.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", self._d):
            e = re_mod.ReasoningEngine()
        self.assertEqual(e._traces, [])

    def test_load_missing(self):
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", self._d):
            e = re_mod.ReasoningEngine()
        self.assertEqual(e._traces, [])

    def test_save_success(self):
        e = re_mod.ReasoningEngine.__new__(re_mod.ReasoningEngine)
        e._lock = threading.Lock()
        e._traces = [{"id": "t1"}]
        with mock.patch.object(e, "_path", lambda: self._path):
            ok = e._save()
        self.assertIsNone(ok)
        self.assertTrue(self._path.exists())
        self.assertEqual(json.loads(self._path.read_text("utf-8")), [{"id": "t1"}])

    def test_save_failure(self):
        e = re_mod.ReasoningEngine.__new__(re_mod.ReasoningEngine)
        e._lock = threading.Lock()
        e._traces = [{"id": "t1"}]
        with mock.patch.object(e, "_path", lambda: self._path), \
                mock.patch.object(Path, "with_name", side_effect=OSError("boom")), \
                mock.patch.object(re_mod, "logger") as lg:
            ok = e._save()
        self.assertFalse(ok)
        lg.error.assert_called_once()

    def test_save_caps_1000(self):
        e = re_mod.ReasoningEngine.__new__(re_mod.ReasoningEngine)
        e._lock = threading.Lock()
        e._traces = [{"id": f"t{i}"} for i in range(1005)]
        with mock.patch.object(e, "_path", lambda: self._path):
            e._save()
        data = json.loads(self._path.read_text("utf-8"))
        self.assertEqual(len(data), 1000)

    def test_path(self):
        e = re_mod.ReasoningEngine.__new__(re_mod.ReasoningEngine)
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", self._d):
            p = e._path()
        self.assertTrue(str(p).endswith("traces.json"))


class DetectComplexityTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", d):
            return re_mod.ReasoningEngine()

    def test_simple(self):
        e = self._make()
        self.assertEqual(e.detect_complexity("what is python"), "simple")
        self.assertEqual(e.detect_complexity("define X"), "simple")
        self.assertEqual(e.detect_complexity("true or false"), "simple")

    def test_medium(self):
        e = self._make()
        self.assertEqual(e.detect_complexity("explain how this works"), "medium")
        self.assertEqual(e.detect_complexity("why does X happen"), "medium")
        self.assertEqual(e.detect_complexity("compare A and B"), "medium")

    def test_complex(self):
        e = self._make()
        self.assertEqual(e.detect_complexity("analyze and optimize the system"), "complex")
        # need >= 2 complex keywords
        self.assertEqual(e.detect_complexity("analyze X"), "simple")  # only 1 -> not complex

    def test_critical(self):
        e = self._make()
        self.assertEqual(e.detect_complexity("should I decide and evaluate the risk"), "critical")
        # need >= 2 critical keywords
        self.assertEqual(e.detect_complexity("should I do it"), "simple")

    def test_no_keywords_simple(self):
        e = self._make()
        self.assertEqual(e.detect_complexity("xyz abc"), "simple")


class SelectStrategyTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", d):
            return re_mod.ReasoningEngine()

    def test_mapping(self):
        e = self._make()
        self.assertEqual(e.select_strategy("simple"), "direct")
        self.assertEqual(e.select_strategy("medium"), "chain_of_thought")
        self.assertEqual(e.select_strategy("complex"), "tree_of_thoughts")
        self.assertEqual(e.select_strategy("critical"), "self_consistency")

    def test_unknown_defaults_cot(self):
        e = self._make()
        self.assertEqual(e.select_strategy("nope"), "chain_of_thought")


class SolveTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", d):
            return re_mod.ReasoningEngine()

    def test_solve_direct(self):
        e = self._make()
        with mock.patch("time.time", side_effect=[1000.0, 1000.5]):
            r = e.solve("what is 2+2", strategy="direct")
        self.assertEqual(r["strategy"], "direct")
        self.assertIn("Direct analysis", r["answer"])
        self.assertEqual(r["final_confidence"], 75.0)
        self.assertEqual(len(r["steps"]), 1)
        self.assertTrue(r["completed_at"])
        self.assertEqual(r["elapsed_ms"], 500.0)
        # persisted
        self.assertEqual(len(e._traces), 1)

    def test_solve_cot(self):
        e = self._make()
        with mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("explain X", strategy="chain_of_thought")
        self.assertEqual(r["strategy"], "chain_of_thought")
        self.assertEqual(len(r["steps"]), 4)
        self.assertEqual(r["final_confidence"], 80.0)

    def test_solve_tot(self):
        e = self._make()
        with mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("analyze Y", strategy="tree_of_thoughts")
        self.assertEqual(r["strategy"], "tree_of_thoughts")
        # 3 paths + 1 final = 4 steps
        self.assertEqual(len(r["steps"]), 4)
        self.assertEqual(r["final_confidence"], 72.0)

    def test_solve_self_consistency(self):
        e = self._make()
        with mock.patch("random.uniform", return_value=70.0), \
                mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("decide Z", strategy="self_consistency")
        self.assertEqual(r["strategy"], "self_consistency")
        # 3 solve steps + 1 final = 4
        self.assertEqual(len(r["steps"]), 4)
        self.assertAlmostEqual(r["final_confidence"], 70.0, places=1)

    def test_solve_react(self):
        e = self._make()
        with mock.patch("random.uniform", return_value=75.0), \
                mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("task", strategy="react")
        self.assertEqual(r["strategy"], "react")
        self.assertEqual(len(r["steps"]), 4)
        self.assertEqual(r["final_confidence"], 82.0)

    def test_solve_auto_strategy(self):
        e = self._make()
        with mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("what is X")  # simple -> direct
        self.assertEqual(r["strategy"], "direct")

    def test_solve_unknown_strategy_falls_to_cot(self):
        e = self._make()
        with mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("task", strategy="nope")
        self.assertEqual(r["strategy"], "nope")
        # falls to cot branch (4 steps)
        self.assertEqual(len(r["steps"]), 4)

    def test_solve_caps_traces_1000(self):
        e = self._make()
        e._traces = [{"id": f"t{i}"} for i in range(1000)]
        with mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            e.solve("task", strategy="direct")
        self.assertEqual(len(e._traces), 1000)

    def test_solve_direct_step_confidence(self):
        e = self._make()
        with mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("task", strategy="direct")
        self.assertEqual(r["steps"][0]["confidence"], 75.0)
        self.assertIn("Direct answer", r["steps"][0]["thought"])

    def test_solve_cot_steps(self):
        e = self._make()
        with mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("task", strategy="chain_of_thought")
        thoughts = [s["thought"] for s in r["steps"]]
        self.assertIn("Understanding the problem: task", thoughts[0])
        self.assertEqual(r["steps"][0]["confidence"], 60.0)

    def test_solve_tot_best_path(self):
        e = self._make()
        with mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("task", strategy="tree_of_thoughts")
        # best path is C (72.0)
        self.assertIn("Approach C", r["steps"][-1]["thought"])
        self.assertEqual(r["final_confidence"], 72.0)

    def test_solve_react_steps_have_actions(self):
        e = self._make()
        with mock.patch("random.uniform", return_value=70.0), \
                mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("task", strategy="react")
        for s in r["steps"]:
            self.assertIn("action", s)
            self.assertIn("observation", s)
            self.assertEqual(s["observation"], f"{s['action']} completed successfully")

    def test_solve_self_consistency_majority(self):
        e = self._make()
        with mock.patch("random.uniform", return_value=80.0), \
                mock.patch("time.time", side_effect=[1000.0, 1000.1]):
            r = e.solve("task", strategy="self_consistency")
        self.assertIn("3 independent solutions", r["answer"])
        self.assertIn("Average confidence: 80%", r["answer"])


class GetTracesTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", d):
            return re_mod.ReasoningEngine()

    def test_get_traces_empty(self):
        e = self._make()
        self.assertEqual(e.get_traces(), [])

    def test_get_traces_limit(self):
        e = self._make()
        e._traces = [{"id": f"t{i}"} for i in range(10)]
        r = e.get_traces(limit=3)
        self.assertEqual(len(r), 3)
        # reversed: last 3 reversed
        self.assertEqual(r[0]["id"], "t9")
        self.assertEqual(r[2]["id"], "t7")

    def test_get_traces_default_limit_50(self):
        e = self._make()
        e._traces = [{"id": f"t{i}"} for i in range(60)]
        r = e.get_traces()
        self.assertEqual(len(r), 50)

    def test_get_trace_found(self):
        e = self._make()
        e._traces = [{"id": "t1", "x": 1}, {"id": "t2", "x": 2}]
        self.assertEqual(e.get_trace("t2"), {"id": "t2", "x": 2})

    def test_get_trace_not_found(self):
        e = self._make()
        e._traces = [{"id": "t1"}]
        self.assertIsNone(e.get_trace("nope"))

    def test_get_stats_empty(self):
        e = self._make()
        self.assertEqual(e.get_stats(), {"total": 0, "avg_confidence": 0,
                                        "strategies": {}})

    def test_get_stats_populated(self):
        e = self._make()
        e._traces = [
            {"id": "t1", "strategy": "direct", "final_confidence": 75.0,
             "steps": [{"a": 1}, {"b": 2}]},
            {"id": "t2", "strategy": "direct", "final_confidence": 80.0,
             "steps": [{"a": 1}]},
            {"id": "t3", "strategy": "cot", "final_confidence": 90.0,
             "steps": []},
        ]
        s = e.get_stats()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["avg_confidence"], 81.7)
        self.assertEqual(s["strategies"], {"direct": 2, "cot": 1})
        self.assertEqual(s["avg_steps"], 1.0)


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = re_mod._instance
        re_mod._instance = None
        self.addCleanup(setattr, re_mod, "_instance", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", d):
            a = re_mod.get_reasoning_engine()
        self.assertIsInstance(a, re_mod.ReasoningEngine)
        self.assertIs(re_mod._instance, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.reasoning_engine.DATA_DIR", d):
            a = re_mod.get_reasoning_engine()
            b = re_mod.get_reasoning_engine()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
