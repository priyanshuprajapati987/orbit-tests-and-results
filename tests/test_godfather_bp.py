"""Unit tests for orbit/orbit/core/godfather_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.godfather_bp import godfather_bp

SWARM = "orbit.core.swarm_council."
EVOLVE = "orbit.core.self_evolution."
PREDICT = "orbit.core.predictive_engine."


def _council_result():
    r = MagicMock()
    r.to_dict.return_value = {"council_id": "c1", "advisors": 4}
    return r


class GodfatherBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(godfather_bp)
        self.client = self.app.test_client()
        self.council = MagicMock()
        self.engine = MagicMock()
        self.pred = MagicMock()

    def _setup_defaults(self):
        """Start the three getters returning local mocks."""
        self._stack = []
        for target, mock in (
            (SWARM + "get_council", self.council),
            (EVOLVE + "get_evolution_engine", self.engine),
            (PREDICT + "get_predictive_engine", self.pred),
        ):
            p = patch(target, return_value=mock)
            p.start()
            self.addCleanup(p.stop)
            self._stack.append(p)

    def test_blueprint_name(self):
        self.assertEqual(godfather_bp.name, "godfather")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/godfather/council", "/api/godfather/council/stats",
                  "/api/godfather/evolve", "/api/godfather/evolve/stats",
                  "/api/godfather/evolve/history",
                  "/api/godfather/evolve/prompts",
                  "/api/godfather/evolve/rollback",
                  "/api/godfather/predict",
                  "/api/godfather/predict/record",
                  "/api/godfather/predict/stats",
                  "/api/godfather/status"]:
            self.assertIn(p, rules)


class TestCouncil(GodfatherBase):
    def _convene(self):
        return patch(SWARM + "convene_council", return_value=_council_result())

    def test_success_defaults(self):
        with self._convene() as conv:
            r = self.client.post("/api/godfather/council",
                                 json={"query": "  plan it  "})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"council_id": "c1", "advisors": 4})
        conv.assert_called_once_with(
            "plan it", category=None, max_advisors=6,
            with_critic=True, with_synthesis=True)

    def test_custom_options(self):
        with self._convene() as conv:
            self.client.post("/api/godfather/council", json={
                "query": "q", "category": "tech", "max_advisors": 4,
                "with_critic": False, "with_synthesis": False})
        conv.assert_called_once_with(
            "q", category="tech", max_advisors=4,
            with_critic=False, with_synthesis=False)

    def test_max_advisors_clamped_to_8(self):
        with self._convene() as conv:
            self.client.post("/api/godfather/council",
                             json={"query": "q", "max_advisors": 99})
        kwargs = conv.call_args.kwargs
        self.assertEqual(kwargs["max_advisors"], 8)

    def test_max_advisors_string_number(self):
        with self._convene() as conv:
            self.client.post("/api/godfather/council",
                             json={"query": "q", "max_advisors": "3"})
        kwargs = conv.call_args.kwargs
        self.assertEqual(kwargs["max_advisors"], 3)

    def test_max_advisors_bad_500(self):
        # int() raises before the try block
        with self._convene():
            r = self.client.post("/api/godfather/council",
                                 json={"query": "q", "max_advisors": "abc"})
        self.assertEqual(r.status_code, 500)

    def test_blank_category_none(self):
        with self._convene() as conv:
            self.client.post("/api/godfather/council",
                             json={"query": "q", "category": "   "})
        kwargs = conv.call_args.kwargs
        self.assertIsNone(kwargs["category"])

    def test_missing_query_400(self):
        with self._convene() as conv:
            r = self.client.post("/api/godfather/council", json={"x": 1})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "query required")
        conv.assert_not_called()

    def test_blank_query_400(self):
        r = self.client.post("/api/godfather/council",
                             json={"query": " "})
        self.assertEqual(r.status_code, 400)

    def test_no_body_400(self):
        r = self.client.post("/api/godfather/council")
        self.assertEqual(r.status_code, 400)

    def test_exception_500(self):
        with patch(SWARM + "convene_council",
                   side_effect=RuntimeError("council down")):
            r = self.client.post("/api/godfather/council",
                                 json={"query": "q"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("council down", r.get_json()["error"])

    def test_stats(self):
        self._setup_defaults()
        self.council.get_stats.return_value = {"sessions": 5}
        r = self.client.get("/api/godfather/council/stats")
        self.assertEqual(r.get_json(), {"sessions": 5})

    def test_stats_exception_500(self):
        with patch(SWARM + "get_council", side_effect=RuntimeError("st")):
            r = self.client.get("/api/godfather/council/stats")
        self.assertEqual(r.status_code, 500)


class TestEvolve(GodfatherBase):
    def test_run_default(self):
        self._setup_defaults()
        self.engine.run_cycle.return_value = {"fixed": 2}
        r = self.client.post("/api/godfather/evolve")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"fixed": 2})
        self.engine.run_cycle.assert_called_once_with(dry_run=False)

    def test_run_dry_run_true(self):
        self._setup_defaults()
        self.engine.run_cycle.return_value = {}
        self.client.post("/api/godfather/evolve", json={"dry_run": True})
        self.engine.run_cycle.assert_called_once_with(dry_run=True)

    def test_run_dry_run_false_explicit(self):
        self._setup_defaults()
        self.engine.run_cycle.return_value = {}
        self.client.post("/api/godfather/evolve", json={"dry_run": False})
        self.engine.run_cycle.assert_called_once_with(dry_run=False)

    def test_run_exception_500(self):
        self._setup_defaults()
        self.engine.run_cycle.side_effect = RuntimeError("cycle fail")
        r = self.client.post("/api/godfather/evolve")
        self.assertEqual(r.status_code, 500)
        self.assertIn("cycle fail", r.get_json()["error"])

    def test_stats(self):
        self._setup_defaults()
        self.engine.get_stats.return_value = {"cycles": 8}
        r = self.client.get("/api/godfather/evolve/stats")
        self.assertEqual(r.get_json(), {"cycles": 8})

    def test_stats_exception_500(self):
        with patch(EVOLVE + "get_evolution_engine",
                   side_effect=RuntimeError("es")):
            r = self.client.get("/api/godfather/evolve/stats")
        self.assertEqual(r.status_code, 500)

    def test_history_default_limit(self):
        self._setup_defaults()
        self.engine.get_history.return_value = [{"step": 1}]
        r = self.client.get("/api/godfather/evolve/history")
        self.engine.get_history.assert_called_once_with(limit=20)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["entries"], [{"step": 1}])

    def test_history_custom_limit(self):
        self._setup_defaults()
        self.engine.get_history.return_value = []
        self.client.get("/api/godfather/evolve/history?limit=5")
        self.engine.get_history.assert_called_once_with(limit=5)

    def test_history_limit_clamped_100(self):
        self._setup_defaults()
        self.engine.get_history.return_value = []
        self.client.get("/api/godfather/evolve/history?limit=999")
        self.engine.get_history.assert_called_once_with(limit=100)

    def test_history_bad_limit_500(self):
        # int() raises before try
        self._setup_defaults()
        r = self.client.get("/api/godfather/evolve/history?limit=abc")
        self.assertEqual(r.status_code, 500)

    def test_history_exception_500(self):
        self._setup_defaults()
        self.engine.get_history.side_effect = RuntimeError("h")
        r = self.client.get("/api/godfather/evolve/history")
        self.assertEqual(r.status_code, 500)

    def test_prompts(self):
        self._setup_defaults()
        self.engine._prompt_store.all_prompts.return_value = {"coding": "p1"}
        r = self.client.get("/api/godfather/evolve/prompts")
        body = r.get_json()
        self.assertEqual(body["prompts"], {"coding": "p1"})
        self.assertEqual(body["count"], 1)

    def test_prompts_exception_500(self):
        with patch(EVOLVE + "get_evolution_engine",
                   side_effect=RuntimeError("pp")):
            r = self.client.get("/api/godfather/evolve/prompts")
        self.assertEqual(r.status_code, 500)

    def test_rollback_success(self):
        self._setup_defaults()
        self.engine.rollback_category.return_value = True
        r = self.client.post("/api/godfather/evolve/rollback",
                             json={"category": "coding"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"rolled_back": True, "category": "coding"})
        self.engine.rollback_category.assert_called_once_with("coding")

    def test_rollback_not_found_404(self):
        self._setup_defaults()
        self.engine.rollback_category.return_value = False
        r = self.client.post("/api/godfather/evolve/rollback",
                             json={"category": "coding"})
        self.assertEqual(r.status_code, 404)
        body = r.get_json()
        self.assertFalse(body["rolled_back"])
        self.assertEqual(body["reason"], "no previous prompt")

    def test_rollback_missing_category_400(self):
        self._setup_defaults()
        r = self.client.post("/api/godfather/evolve/rollback", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "category required")
        self.engine.rollback_category.assert_not_called()

    def test_rollback_blank_category_400(self):
        self._setup_defaults()
        r = self.client.post("/api/godfather/evolve/rollback",
                             json={"category": "  "})
        self.assertEqual(r.status_code, 400)

    def test_rollback_no_body_400(self):
        r = self.client.post("/api/godfather/evolve/rollback")
        self.assertEqual(r.status_code, 400)

    def test_rollback_category_coerced(self):
        self._setup_defaults()
        self.engine.rollback_category.return_value = True
        r = self.client.post("/api/godfather/evolve/rollback",
                             json={"category": 123})
        self.engine.rollback_category.assert_called_once_with("123")

    def test_rollback_exception_500(self):
        self._setup_defaults()
        self.engine.rollback_category.side_effect = RuntimeError("rb")
        r = self.client.post("/api/godfather/evolve/rollback",
                             json={"category": "x"})
        self.assertEqual(r.status_code, 500)


class TestPredict(GodfatherBase):
    def test_defaults(self):
        self._setup_defaults()
        self.pred.get_predictions.return_value = [{"kind": "habit"}]
        r = self.client.get("/api/godfather/predict")
        self.pred.get_predictions.assert_called_once_with(
            ptype=None, min_confidence=0.0, limit=10)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["predictions"], [{"kind": "habit"}])

    def test_with_params(self):
        self._setup_defaults()
        self.pred.get_predictions.return_value = []
        self.client.get(
            "/api/godfather/predict?type=habit&min_confidence=0.5&limit=5")
        self.pred.get_predictions.assert_called_once_with(
            ptype="habit", min_confidence=0.5, limit=5)

    def test_blank_type_none(self):
        self._setup_defaults()
        self.pred.get_predictions.return_value = []
        self.client.get("/api/godfather/predict?type=")
        kwargs = self.pred.get_predictions.call_args.kwargs
        self.assertIsNone(kwargs["ptype"])

    def test_limit_clamped_50(self):
        self._setup_defaults()
        self.pred.get_predictions.return_value = []
        self.client.get("/api/godfather/predict?limit=999")
        kwargs = self.pred.get_predictions.call_args.kwargs
        self.assertEqual(kwargs["limit"], 50)

    def test_bad_min_confidence_500(self):
        # float() raises before try
        self._setup_defaults()
        r = self.client.get("/api/godfather/predict?min_confidence=abc")
        self.assertEqual(r.status_code, 500)

    def test_bad_limit_500(self):
        self._setup_defaults()
        r = self.client.get("/api/godfather/predict?limit=abc")
        self.assertEqual(r.status_code, 500)

    def test_exception_500(self):
        self._setup_defaults()
        self.pred.get_predictions.side_effect = RuntimeError("pr")
        r = self.client.get("/api/godfather/predict")
        self.assertEqual(r.status_code, 500)

    def test_record_success(self):
        self._setup_defaults()
        r = self.client.post("/api/godfather/predict/record",
                             json={"action": "  open editor  ",
                                   "context": {"app": "vscode"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"recorded": True, "action": "open editor"})
        self.pred.record_action.assert_called_once_with(
            "open editor", {"app": "vscode"})

    def test_record_no_context(self):
        self._setup_defaults()
        self.client.post("/api/godfather/predict/record",
                         json={"action": "click"})
        self.pred.record_action.assert_called_once_with("click", None)

    def test_record_non_dict_context_none(self):
        self._setup_defaults()
        self.client.post("/api/godfather/predict/record",
                         json={"action": "click", "context": "not-a-dict"})
        self.pred.record_action.assert_called_once_with("click", None)

    def test_record_action_truncated_100(self):
        self._setup_defaults()
        long_action = "x" * 250
        r = self.client.post("/api/godfather/predict/record",
                             json={"action": long_action})
        body = r.get_json()
        self.assertEqual(body["action"], "x" * 100)
        # full action passed to engine
        self.pred.record_action.assert_called_once_with(long_action, None)

    def test_record_missing_action_400(self):
        self._setup_defaults()
        r = self.client.post("/api/godfather/predict/record", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "action required")
        self.pred.record_action.assert_not_called()

    def test_record_blank_action_400(self):
        self._setup_defaults()
        r = self.client.post("/api/godfather/predict/record",
                             json={"action": "   "})
        self.assertEqual(r.status_code, 400)

    def test_record_no_body_400(self):
        r = self.client.post("/api/godfather/predict/record")
        self.assertEqual(r.status_code, 400)

    def test_record_action_coerced_str(self):
        self._setup_defaults()
        self.client.post("/api/godfather/predict/record",
                         json={"action": 42})
        self.pred.record_action.assert_called_once_with("42", None)

    def test_record_exception_500(self):
        self._setup_defaults()
        self.pred.record_action.side_effect = RuntimeError("rec")
        r = self.client.post("/api/godfather/predict/record",
                             json={"action": "a"})
        self.assertEqual(r.status_code, 500)

    def test_predict_stats(self):
        self._setup_defaults()
        self.pred.get_stats.return_value = {"learned": 14}
        r = self.client.get("/api/godfather/predict/stats")
        self.assertEqual(r.get_json(), {"learned": 14})

    def test_predict_stats_exception_500(self):
        with patch(PREDICT + "get_predictive_engine",
                   side_effect=RuntimeError("ps")):
            r = self.client.get("/api/godfather/predict/stats")
        self.assertEqual(r.status_code, 500)


class TestStatus(GodfatherBase):
    def test_all_ok(self):
        self._setup_defaults()
        self.council.get_stats.return_value = {"sessions": 1}
        self.engine.get_stats.return_value = {"cycles": 2}
        self.pred.get_stats.return_value = {"learned": 3}
        r = self.client.get("/api/godfather/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {
            "swarm_council": {"sessions": 1},
            "self_evolution": {"cycles": 2},
            "predictive_engine": {"learned": 3},
        })

    def test_swarm_fails_others_ok(self):
        with patch(SWARM + "get_council", side_effect=RuntimeError("s down")), \
             patch(EVOLVE + "get_evolution_engine") as ge, \
             patch(PREDICT + "get_predictive_engine") as gp:
            ge.return_value.get_stats.return_value = {}
            gp.return_value.get_stats.return_value = {}
            body = self.client.get("/api/godfather/status").get_json()
        self.assertIn("s down", body["swarm_council"]["error"])
        self.assertEqual(body["self_evolution"], {})
        self.assertEqual(body["predictive_engine"], {})

    def test_evolve_fails_others_ok(self):
        self._setup_defaults()
        self.engine.get_stats.side_effect = RuntimeError("e down")
        self.council.get_stats.return_value = {}
        self.pred.get_stats.return_value = {}
        body = self.client.get("/api/godfather/status").get_json()
        self.assertIn("e down", body["self_evolution"]["error"])

    def test_predict_fails_others_ok(self):
        self._setup_defaults()
        self.pred.get_stats.side_effect = RuntimeError("p down")
        self.council.get_stats.return_value = {}
        self.engine.get_stats.return_value = {}
        body = self.client.get("/api/godfather/status").get_json()
        self.assertIn("p down", body["predictive_engine"]["error"])

    def test_all_fail(self):
        with patch(SWARM + "get_council", side_effect=RuntimeError("s")), \
             patch(EVOLVE + "get_evolution_engine",
                   side_effect=RuntimeError("e")), \
             patch(PREDICT + "get_predictive_engine",
                   side_effect=RuntimeError("p")):
            r = self.client.get("/api/godfather/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        for key in ("swarm_council", "self_evolution", "predictive_engine"):
            self.assertIn("error", body[key])


if __name__ == "__main__":
    unittest.main()
