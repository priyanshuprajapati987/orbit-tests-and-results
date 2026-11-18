"""Unit tests for orbit/orbit/core/future_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.future_bp import future_bp


def _quant_result():
    r = MagicMock()
    r.to_dict.return_value = {"answer": 42, "code": "print(42)"}
    return r


def _ident(code="Q1"):
    ident = MagicMock()
    ident.to_dict.return_value = {"code": code, "name": "Queen"}
    ident.verify.return_value = True
    return ident


class FutureBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(future_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(future_bp.name, "future")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/future/quant/solve", "/api/future/quant/check",
                  "/api/future/quant/stats", "/api/future/identity",
                  "/api/future/identity/<code>", "/api/future/identity/audit",
                  "/api/future/identity/stats", "/api/future/world",
                  "/api/future/world/brief", "/api/future/status"]:
            self.assertIn(p, rules)


class TestQuantSolve(FutureBpBase):
    def test_success(self):
        with patch("orbit.core.quant_router.get_quant_router") as gr:
            gr.return_value.solve.return_value = _quant_result()
            r = self.client.post("/api/future/quant/solve",
                                 json={"query": "what is 6*7"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"answer": 42, "code": "print(42)"})
        gr.return_value.solve.assert_called_once_with("what is 6*7")

    def test_query_stripped(self):
        with patch("orbit.core.quant_router.get_quant_router") as gr:
            gr.return_value.solve.return_value = _quant_result()
            self.client.post("/api/future/quant/solve",
                             json={"query": "  1+1  "})
        gr.return_value.solve.assert_called_once_with("1+1")

    def test_query_coerced_to_string(self):
        with patch("orbit.core.quant_router.get_quant_router") as gr:
            gr.return_value.solve.return_value = _quant_result()
            self.client.post("/api/future/quant/solve", json={"query": 123})
        gr.return_value.solve.assert_called_once_with("123")

    def test_missing_query_400(self):
        with patch("orbit.core.quant_router.get_quant_router") as gr:
            r = self.client.post("/api/future/quant/solve", json={"x": 1})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "query required")
        gr.return_value.solve.assert_not_called()

    def test_blank_query_400(self):
        r = self.client.post("/api/future/quant/solve",
                             json={"query": "   "})
        self.assertEqual(r.status_code, 400)

    def test_no_body_400(self):
        r = self.client.post("/api/future/quant/solve")
        self.assertEqual(r.status_code, 400)

    def test_exception_500(self):
        with patch("orbit.core.quant_router.get_quant_router",
                   side_effect=RuntimeError("boom")):
            r = self.client.post("/api/future/quant/solve",
                                 json={"query": "1+1"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("boom", r.get_json()["error"])


class TestQuantCheck(FutureBpBase):
    def test_quant_true_with_code(self):
        with patch("orbit.core.quant_router.is_quant_query",
                   return_value=True) as iq, \
             patch("orbit.core.quant_router._generate_code",
                   return_value="print(1)") as gen:
            r = self.client.post("/api/future/quant/check",
                                 json={"query": "2+2"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["query"], "2+2")
        self.assertTrue(body["is_quant"])
        self.assertEqual(body["generated_code"], "print(1)")
        iq.assert_called_once_with("2+2")
        gen.assert_called_once_with("2+2")

    def test_quant_false_no_code(self):
        with patch("orbit.core.quant_router.is_quant_query",
                   return_value=False) as iq, \
             patch("orbit.core.quant_router._generate_code") as gen:
            r = self.client.post("/api/future/quant/check",
                                 json={"query": "hello"})
        body = r.get_json()
        self.assertFalse(body["is_quant"])
        self.assertIsNone(body["generated_code"])
        gen.assert_not_called()

    def test_missing_query_400(self):
        r = self.client.post("/api/future/quant/check", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "query required")

    def test_no_body_400(self):
        r = self.client.post("/api/future/quant/check")
        self.assertEqual(r.status_code, 400)

    def test_exception_500(self):
        with patch("orbit.core.quant_router.is_quant_query",
                   side_effect=RuntimeError("detect fail")):
            r = self.client.post("/api/future/quant/check",
                                 json={"query": "1"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("detect fail", r.get_json()["error"])


class TestQuantStats(FutureBpBase):
    def test_success(self):
        with patch("orbit.core.quant_router.get_quant_router") as gr:
            gr.return_value.get_stats.return_value = {"solved": 9}
            r = self.client.get("/api/future/quant/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"solved": 9})

    def test_exception_500(self):
        with patch("orbit.core.quant_router.get_quant_router",
                   side_effect=RuntimeError("stats fail")):
            r = self.client.get("/api/future/quant/stats")
        self.assertEqual(r.status_code, 500)
        self.assertIn("stats fail", r.get_json()["error"])


class TestIdentity(FutureBpBase):
    def test_registry(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.export_registry.return_value = {"Q1": {"name": "Queen"}}
            r = self.client.get("/api/future/identity")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"Q1": {"name": "Queen"}})

    def test_registry_exception_500(self):
        with patch("orbit.core.agent_identity.get_identity_manager",
                   side_effect=RuntimeError("reg fail")):
            r = self.client.get("/api/future/identity")
        self.assertEqual(r.status_code, 500)

    def test_card_found(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get.return_value = _ident("Q1")
            r = self.client.get("/api/future/identity/q1")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["code"], "Q1")
        self.assertTrue(body["signature_valid"])
        gm.return_value.get.assert_called_once_with("Q1")  # upper-cased

    def test_card_signature_invalid(self):
        ident = _ident()
        ident.verify.return_value = False
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get.return_value = ident
            r = self.client.get("/api/future/identity/Q1")
        self.assertFalse(r.get_json()["signature_valid"])

    def test_card_not_found_404(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get.return_value = None
            r = self.client.get("/api/future/identity/nope")
        self.assertEqual(r.status_code, 404)
        self.assertIn("unknown agent: nope", r.get_json()["error"])

    def test_card_exception_500(self):
        with patch("orbit.core.agent_identity.get_identity_manager",
                   side_effect=RuntimeError("card fail")):
            r = self.client.get("/api/future/identity/Q1")
        self.assertEqual(r.status_code, 500)

    def test_audit_default(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get_audit_trail.return_value = [{"a": 1}]
            r = self.client.get("/api/future/identity/audit")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["entries"], [{"a": 1}])
        self.assertEqual(body["count"], 1)
        gm.return_value.get_audit_trail.assert_called_once_with(
            code=None, limit=50)

    def test_audit_with_code_uppercased(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get_audit_trail.return_value = []
            self.client.get("/api/future/identity/audit?code=q1")
        gm.return_value.get_audit_trail.assert_called_once_with(
            code="Q1", limit=50)

    def test_audit_blank_code_none(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get_audit_trail.return_value = []
            self.client.get("/api/future/identity/audit?code=")
        gm.return_value.get_audit_trail.assert_called_once_with(
            code=None, limit=50)

    def test_audit_limit_clamped_to_500(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get_audit_trail.return_value = []
            self.client.get("/api/future/identity/audit?limit=9999")
        gm.return_value.get_audit_trail.assert_called_once_with(
            code=None, limit=500)

    def test_audit_custom_limit(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get_audit_trail.return_value = []
            self.client.get("/api/future/identity/audit?limit=10")
        gm.return_value.get_audit_trail.assert_called_once_with(
            code=None, limit=10)

    def test_audit_bad_limit_500(self):
        # int() raises before the try block -> 500
        r = self.client.get("/api/future/identity/audit?limit=abc")
        self.assertEqual(r.status_code, 500)

    def test_audit_exception_500(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get_audit_trail.side_effect = RuntimeError("au")
            r = self.client.get("/api/future/identity/audit")
        self.assertEqual(r.status_code, 500)
        self.assertIn("au", r.get_json()["error"])

    def test_stats(self):
        with patch("orbit.core.agent_identity.get_identity_manager") as gm:
            gm.return_value.get_stats.return_value = {"agents": 3}
            r = self.client.get("/api/future/identity/stats")
        self.assertEqual(r.get_json(), {"agents": 3})

    def test_stats_exception_500(self):
        with patch("orbit.core.agent_identity.get_identity_manager",
                   side_effect=RuntimeError("st")):
            r = self.client.get("/api/future/identity/stats")
        self.assertEqual(r.status_code, 500)


class TestWorld(FutureBpBase):
    def test_snapshot_default_no_force(self):
        snap = MagicMock()
        snap.to_dict.return_value = {"time": "now"}
        with patch("orbit.core.world_state.get_world_state_manager") as gm:
            gm.return_value.snapshot.return_value = snap
            r = self.client.get("/api/future/world")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"time": "now"})
        gm.return_value.snapshot.assert_called_once_with(force=False)

    def test_force_true_variants(self):
        for val in ("1", "true", "yes"):
            snap = MagicMock()
            snap.to_dict.return_value = {}
            with patch("orbit.core.world_state.get_world_state_manager") as gm:
                gm.return_value.snapshot.return_value = snap
                self.client.get(f"/api/future/world?force={val}")
            gm.return_value.snapshot.assert_called_once_with(force=True)

    def test_force_false_variants(self):
        for val in ("0", "TRUE", "no", ""):
            snap = MagicMock()
            snap.to_dict.return_value = {}
            with patch("orbit.core.world_state.get_world_state_manager") as gm:
                gm.return_value.snapshot.return_value = snap
                self.client.get(f"/api/future/world?force={val}")
            gm.return_value.snapshot.assert_called_once_with(force=False)

    def test_exception_500(self):
        with patch("orbit.core.world_state.get_world_state_manager",
                   side_effect=RuntimeError("world fail")):
            r = self.client.get("/api/future/world")
        self.assertEqual(r.status_code, 500)
        self.assertIn("world fail", r.get_json()["error"])

    def test_brief(self):
        with patch("orbit.core.world_state.get_world_state") as gw:
            gw.return_value.brief.return_value = "all calm"
            r = self.client.get("/api/future/world/brief")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"brief": "all calm"})

    def test_brief_exception_500(self):
        with patch("orbit.core.world_state.get_world_state",
                   side_effect=RuntimeError("brief fail")):
            r = self.client.get("/api/future/world/brief")
        self.assertEqual(r.status_code, 500)


class TestStatus(FutureBpBase):
    def test_all_ok(self):
        with patch("orbit.core.quant_router.get_quant_router") as gq, \
             patch("orbit.core.agent_identity.get_identity_manager") as gi, \
             patch("orbit.core.world_state.get_world_state_manager") as gw:
            gq.return_value.get_stats.return_value = {"solved": 1}
            gi.return_value.get_stats.return_value = {"agents": 2}
            gw.return_value.get_stats.return_value = {"ticks": 3}
            r = self.client.get("/api/future/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {
            "quant_router": {"solved": 1},
            "agent_identity": {"agents": 2},
            "world_state": {"ticks": 3},
        })

    def test_quant_fails_others_ok(self):
        with patch("orbit.core.quant_router.get_quant_router",
                   side_effect=RuntimeError("q down")), \
             patch("orbit.core.agent_identity.get_identity_manager") as gi, \
             patch("orbit.core.world_state.get_world_state_manager") as gw:
            gi.return_value.get_stats.return_value = {"agents": 2}
            gw.return_value.get_stats.return_value = {"ticks": 3}
            r = self.client.get("/api/future/status")
        body = r.get_json()
        self.assertEqual(r.status_code, 200)  # partial failure still 200
        self.assertIn("q down", body["quant_router"]["error"])
        self.assertEqual(body["agent_identity"], {"agents": 2})
        self.assertEqual(body["world_state"], {"ticks": 3})

    def test_identity_fails_others_ok(self):
        with patch("orbit.core.quant_router.get_quant_router") as gq, \
             patch("orbit.core.agent_identity.get_identity_manager",
                   side_effect=RuntimeError("i down")), \
             patch("orbit.core.world_state.get_world_state_manager") as gw:
            gq.return_value.get_stats.return_value = {}
            gw.return_value.get_stats.return_value = {}
            body = self.client.get("/api/future/status").get_json()
        self.assertIn("i down", body["agent_identity"]["error"])
        self.assertEqual(body["quant_router"], {})

    def test_world_fails_others_ok(self):
        with patch("orbit.core.quant_router.get_quant_router") as gq, \
             patch("orbit.core.agent_identity.get_identity_manager") as gi, \
             patch("orbit.core.world_state.get_world_state_manager",
                   side_effect=RuntimeError("w down")):
            gq.return_value.get_stats.return_value = {}
            gi.return_value.get_stats.return_value = {}
            body = self.client.get("/api/future/status").get_json()
        self.assertIn("w down", body["world_state"]["error"])

    def test_all_fail(self):
        with patch("orbit.core.quant_router.get_quant_router",
                   side_effect=RuntimeError("q")), \
             patch("orbit.core.agent_identity.get_identity_manager",
                   side_effect=RuntimeError("i")), \
             patch("orbit.core.world_state.get_world_state_manager",
                   side_effect=RuntimeError("w")):
            r = self.client.get("/api/future/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        for key in ("quant_router", "agent_identity", "world_state"):
            self.assertIn("error", body[key])


if __name__ == "__main__":
    unittest.main()
