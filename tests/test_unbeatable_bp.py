"""Unit tests for orbit/orbit/core/unbeatable_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.unbeatable_bp import unbeatable_bp


class UnbeatableBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(unbeatable_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(unbeatable_bp.name, "unbeatable")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/unbeatable/status", "/api/unbeatable/wake-eval",
                  "/api/unbeatable/wake-eval/apply", "/api/unbeatable/creative",
                  "/api/unbeatable/proactive-screen/start",
                  "/api/unbeatable/proactive-screen/stop",
                  "/api/unbeatable/proactive-screen/suggestions"]:
            self.assertIn(p, rules)


class TestStatus(UnbeatableBase):
    def test_status_defaults(self):
        tts = MagicMock()
        tts.get_stats.return_value = {"buffered": 2}
        ps = MagicMock()
        ps.get_status.return_value = {"running": True}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORBIT_STREAMING_TTS", None)
            os.environ["ORBIT_MULTI_CANDIDATE"] = "1"
            with patch("orbit.core.streaming_tts.get_streaming_tts",
                       return_value=tts), \
                 patch("orbit.core.proactive_screen.get_proactive_screen",
                       return_value=ps):
                r = self.client.get("/api/unbeatable/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertFalse(body["streaming_tts"]["enabled"])
        self.assertEqual(body["streaming_tts"]["buffered"], 2)
        self.assertTrue(body["multi_candidate"]["enabled"])
        self.assertEqual(body["proactive_screen"], {"running": True})

    def test_status_streaming_tts_enabled(self):
        with patch.dict(os.environ, {"ORBIT_STREAMING_TTS": "on"}):
            with patch("orbit.core.streaming_tts.get_streaming_tts",
                       side_effect=ImportError), \
                 patch("orbit.core.proactive_screen.get_proactive_screen",
                       side_effect=ImportError):
                r = self.client.get("/api/unbeatable/status")
        body = r.get_json()
        self.assertTrue(body["streaming_tts"]["enabled"])
        # import failures swallowed -> empty dicts
        self.assertEqual(body["proactive_screen"], {})

    def test_status_multi_candidate_off(self):
        with patch.dict(os.environ, {"ORBIT_MULTI_CANDIDATE": "0"}):
            with patch("orbit.core.streaming_tts.get_streaming_tts",
                       side_effect=RuntimeError), \
                 patch("orbit.core.proactive_screen.get_proactive_screen",
                       side_effect=RuntimeError):
                r = self.client.get("/api/unbeatable/status")
        self.assertFalse(r.get_json()["multi_candidate"]["enabled"])


class TestWakeEval(UnbeatableBase):
    def test_success(self):
        report = {"summary": {"far": 0.01}, "best_operating_point": None}
        with patch("orbit.core.wake_eval.run_far_frr_eval",
                   return_value=report) as run, \
             patch("orbit.core.wake_eval.get_current_config",
                   return_value={"energy": 100}):
            r = self.client.post("/api/unbeatable/wake-eval", json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["live_config"], {"energy": 100})
        run.assert_called_once_with(energy_thresholds=None,
                                    confidence_thresholds=None)

    def test_with_thresholds(self):
        report = {"summary": {}}
        with patch("orbit.core.wake_eval.run_far_frr_eval",
                   return_value=report) as run, \
             patch("orbit.core.wake_eval.get_current_config",
                   return_value={}):
            r = self.client.post("/api/unbeatable/wake-eval", json={
                "energy_thresholds": [10, 20],
                "confidence_thresholds": [0.5, 0.6]})
        run.assert_called_once_with(energy_thresholds=[10, 20],
                                    confidence_thresholds=[0.5, 0.6])

    def test_no_body(self):
        report = {"summary": {}}
        with patch("orbit.core.wake_eval.run_far_frr_eval",
                   return_value=report), \
             patch("orbit.core.wake_eval.get_current_config",
                   return_value={}):
            r = self.client.post("/api/unbeatable/wake-eval")
        self.assertEqual(r.status_code, 200)

    def test_exception_500(self):
        with patch("orbit.core.wake_eval.run_far_frr_eval",
                   side_effect=RuntimeError("boom")):
            r = self.client.post("/api/unbeatable/wake-eval", json={})
        self.assertEqual(r.status_code, 500)
        self.assertIn("boom", r.get_json()["error"])


class TestWakeEvalApply(UnbeatableBase):
    def _report(self, best=True):
        rep = {"summary": {"far": 0.02}}
        if best:
            rep["best_operating_point"] = {
                "energy_threshold": 150, "confidence_threshold": 0.7}
        return rep

    def test_apply_success(self):
        with patch("orbit.core.wake_eval.run_far_frr_eval",
                   return_value=self._report()), \
             patch("orbit.core.wake_eval.get_current_config",
                   return_value={"energy": 150}), \
             patch("orbit.wake_word.apply_tuning",
                   return_value={"energy_threshold": 150}) as apply:
            r = self.client.post("/api/unbeatable/wake-eval/apply", json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["applied"])
        self.assertEqual(body["operating_point"]["energy_threshold"], 150)
        self.assertEqual(body["applied_values"], {"energy_threshold": 150})
        apply.assert_called_once_with(energy_threshold=150,
                                      confidence_threshold=0.7)

    def test_dry_run(self):
        with patch("orbit.core.wake_eval.run_far_frr_eval",
                   return_value=self._report()), \
             patch("orbit.core.wake_eval.get_current_config",
                   return_value={}), \
             patch("orbit.wake_word.apply_tuning") as apply:
            r = self.client.post("/api/unbeatable/wake-eval/apply",
                                 json={"dry_run": True})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertFalse(body["applied"])
        self.assertEqual(body["would_apply"]["energy_threshold"], 150)
        apply.assert_not_called()

    def test_no_operating_point_500(self):
        with patch("orbit.core.wake_eval.run_far_frr_eval",
                   return_value=self._report(best=False)), \
             patch("orbit.core.wake_eval.get_current_config",
                   return_value={}):
            r = self.client.post("/api/unbeatable/wake-eval/apply", json={})
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertEqual(body["error"], "no operating point found")
        self.assertIn("report", body)

    def test_exception_500(self):
        with patch("orbit.core.wake_eval.run_far_frr_eval",
                   side_effect=RuntimeError("x")):
            r = self.client.post("/api/unbeatable/wake-eval/apply", json={})
        self.assertEqual(r.status_code, 500)
        self.assertIn("x", r.get_json()["error"])


class TestCreative(UnbeatableBase):
    def test_success(self):
        with patch("orbit.core.multi_candidate.generate_best_creative",
                   return_value=("best text", {"n": 3})) as gen:
            r = self.client.post("/api/unbeatable/creative",
                                 json={"prompt": "write a poem"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["best"], "best text")
        self.assertEqual(body["meta"], {"n": 3})
        gen.assert_called_once_with("write a poem", n=3)

    def test_n_capped_at_5(self):
        with patch("orbit.core.multi_candidate.generate_best_creative",
                   return_value=("b", {})) as gen:
            r = self.client.post("/api/unbeatable/creative",
                                 json={"prompt": "p", "n": 50})
        gen.assert_called_once_with("p", n=5)

    def test_n_string_number(self):
        with patch("orbit.core.multi_candidate.generate_best_creative",
                   return_value=("b", {})) as gen:
            r = self.client.post("/api/unbeatable/creative",
                                 json={"prompt": "p", "n": "2"})
        gen.assert_called_once_with("p", n=2)

    def test_missing_prompt_400(self):
        with patch("orbit.core.multi_candidate.generate_best_creative") as gen:
            r = self.client.post("/api/unbeatable/creative", json={"n": 2})
        self.assertEqual(r.status_code, 400)
        self.assertIn("prompt required", r.get_json()["error"])
        gen.assert_not_called()

    def test_blank_prompt_400(self):
        r = self.client.post("/api/unbeatable/creative", json={"prompt": "   "})
        self.assertEqual(r.status_code, 400)

    def test_no_body_400(self):
        r = self.client.post("/api/unbeatable/creative")
        self.assertEqual(r.status_code, 400)

    def test_exception_500(self):
        with patch("orbit.core.multi_candidate.generate_best_creative",
                   side_effect=RuntimeError("gen fail")):
            r = self.client.post("/api/unbeatable/creative",
                                 json={"prompt": "p"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("gen fail", r.get_json()["error"])


class TestProactiveScreen(UnbeatableBase):
    def test_start_default(self):
        ps = MagicMock()
        with patch("orbit.core.proactive_screen.get_proactive_screen",
                   return_value=ps):
            r = self.client.post("/api/unbeatable/proactive-screen/start",
                                 json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "started")
        self.assertEqual(body["interval"], 30)
        ps.start.assert_called_once_with(interval_sec=30.0)

    def test_start_custom_interval(self):
        ps = MagicMock()
        with patch("orbit.core.proactive_screen.get_proactive_screen",
                   return_value=ps):
            r = self.client.post("/api/unbeatable/proactive-screen/start",
                                 json={"interval_sec": 45})
        ps.start.assert_called_once_with(interval_sec=45.0)

    def test_start_no_body(self):
        ps = MagicMock()
        with patch("orbit.core.proactive_screen.get_proactive_screen",
                   return_value=ps):
            r = self.client.post("/api/unbeatable/proactive-screen/start")
        self.assertEqual(r.status_code, 200)

    def test_start_exception_500(self):
        with patch("orbit.core.proactive_screen.get_proactive_screen",
                   side_effect=RuntimeError("start fail")):
            r = self.client.post("/api/unbeatable/proactive-screen/start",
                                 json={})
        self.assertEqual(r.status_code, 500)
        self.assertIn("start fail", r.get_json()["error"])

    def test_stop(self):
        ps = MagicMock()
        with patch("orbit.core.proactive_screen.get_proactive_screen",
                   return_value=ps):
            r = self.client.post("/api/unbeatable/proactive-screen/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "stopped")
        ps.stop.assert_called_once()

    def test_stop_exception_500(self):
        with patch("orbit.core.proactive_screen.get_proactive_screen",
                   side_effect=RuntimeError("stop fail")):
            r = self.client.post("/api/unbeatable/proactive-screen/stop")
        self.assertEqual(r.status_code, 500)

    def test_suggestions(self):
        ps = MagicMock()
        ps.get_suggestions.return_value = ["take a break"]
        with patch("orbit.core.proactive_screen.get_proactive_screen",
                   return_value=ps):
            r = self.client.get("/api/unbeatable/proactive-screen/suggestions")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["suggestions"], ["take a break"])

    def test_suggestions_exception_500(self):
        with patch("orbit.core.proactive_screen.get_proactive_screen",
                   side_effect=RuntimeError("x")):
            r = self.client.get("/api/unbeatable/proactive-screen/suggestions")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
