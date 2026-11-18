"""Unit tests for orbit/orbit/core/dead_hand_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.dead_hand_bp import (
    dead_hand_bp, _require_local, _require_local_post, _rate_limit, _reason,
)

ENGINE = "orbit.core.dead_hand.get_dead_hand"
LIMITER = "orbit.core.rate_limiter.get_limiter"
REMOTE = {"REMOTE_ADDR": "10.9.8.7"}


class DeadHandBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(dead_hand_bp)
        self.client = self.app.test_client()
        self.dh = MagicMock()
        self.dh.armed = False
        self.dh.get_status.return_value = {
            "armed": False, "attempts": 3, "code_root": "/x",
            "identities_recorded": 2, "warnings": ["w1"]}
        self.dh.get_flagged.return_value = {"flagged": ["id1"]}
        self.dh.disarm.return_value = {"sealed": True}
        self.dh.reseal.return_value = {"sealed_files": 4}
        self.dh.unflag.return_value = 2
        self.dh.reset.return_value = {"armed": False}
        # engine
        ep = patch(ENGINE, return_value=self.dh)
        ep.start()
        self.addCleanup(ep.stop)
        # rate limiter: always allow
        self.limiter = MagicMock()
        self.limiter.scoped_check.return_value = True
        lp = patch(LIMITER, return_value=self.limiter)
        lp.start()
        self.addCleanup(lp.stop)

    def test_blueprint_name(self):
        self.assertEqual(dead_hand_bp.name, "dead_hand_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/deadhand/status", "/api/deadhand/attempts",
                  "/api/deadhand/flagged", "/api/deadhand/arm",
                  "/api/deadhand/disarm", "/api/deadhand/reset",
                  "/api/deadhand/reseal", "/api/deadhand/unflag"]:
            self.assertIn(p, rules)


class TestLocalGuard(DeadHandBase):
    def test_local_ipv4(self):
        with self.app.test_request_context(
                "/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            self.assertIsNone(_require_local())

    def test_local_ipv6(self):
        with self.app.test_request_context(
                "/", environ_base={"REMOTE_ADDR": "::1"}):
            self.assertIsNone(_require_local())

    def test_local_hostname(self):
        with self.app.test_request_context(
                "/", environ_base={"REMOTE_ADDR": "localhost"}):
            self.assertIsNone(_require_local())

    def test_remote_denied(self):
        with self.app.test_request_context(
                "/", environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            denied = _require_local()
        self.assertIsNotNone(denied)
        resp, code = denied
        self.assertEqual(code, 403)
        self.assertEqual(resp.get_json()["error"], "local_only")

    def test_missing_remote_addr_denied(self):
        with self.app.test_request_context("/"):
            # werkzeug default sets 127.0.0.1; force empty
            from flask import request
            request.environ["REMOTE_ADDR"] = ""
            denied = _require_local()
        self.assertIsNotNone(denied)


class TestStatus(DeadHandBase):
    def test_local_keeps_sensitive_fields(self):
        r = self.client.get("/api/deadhand/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        dh = body["dead_hand"]
        self.assertEqual(dh["attempts"], 3)
        self.assertEqual(dh["code_root"], "/x")
        self.assertEqual(dh["identities_recorded"], 2)

    def test_remote_sanitized(self):
        r = self.client.get("/api/deadhand/status",
                            environ_base=REMOTE)
        self.assertEqual(r.status_code, 200)
        dh = r.get_json()["dead_hand"]
        self.assertNotIn("attempts", dh)
        self.assertNotIn("code_root", dh)
        self.assertNotIn("identities_recorded", dh)
        self.assertIn("armed", dh)  # non-sensitive kept

    def test_exception_500(self):
        self.dh.get_status.side_effect = RuntimeError("boom")
        r = self.client.get("/api/deadhand/status")
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertFalse(body["ok"])
        self.assertIn("boom", body["error"])


class TestAttemptsFlagged(DeadHandBase):
    def test_attempts_local(self):
        r = self.client.get("/api/deadhand/attempts")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["attempts"], 3)
        self.assertEqual(body["warnings"], ["w1"])

    def test_attempts_remote_403(self):
        r = self.client.get("/api/deadhand/attempts",
                            environ_base=REMOTE)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "local_only")

    def test_attempts_exception_500(self):
        self.dh.get_status.side_effect = RuntimeError("a fail")
        r = self.client.get("/api/deadhand/attempts")
        self.assertEqual(r.status_code, 500)

    def test_flagged_local(self):
        r = self.client.get("/api/deadhand/flagged")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["flagged"], ["id1"])

    def test_flagged_remote_403(self):
        r = self.client.get("/api/deadhand/flagged",
                            environ_base=REMOTE)
        self.assertEqual(r.status_code, 403)

    def test_flagged_exception_500(self):
        self.dh.get_flagged.side_effect = RuntimeError("f fail")
        r = self.client.get("/api/deadhand/flagged")
        self.assertEqual(r.status_code, 500)


class TestCSRF(DeadHandBase):
    def test_origin_evil_blocked(self):
        r = self.client.post("/api/deadhand/arm",
                             json={"confirm": "ARM"},
                             headers={"Origin": "http://evil.example"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "csrf_origin")

    def test_origin_local_ip_allowed(self):
        self.dh.arm_manual.return_value = None
        r = self.client.post("/api/deadhand/arm",
                             json={"confirm": "ARM"},
                             headers={"Origin": "http://127.0.0.1:5000"})
        self.assertEqual(r.status_code, 200)

    def test_origin_localhost_allowed(self):
        self.dh.arm_manual.return_value = None
        r = self.client.post("/api/deadhand/arm",
                             json={"confirm": "ARM"},
                             headers={"Origin": "http://localhost:8080"})
        self.assertEqual(r.status_code, 200)

    def test_referer_evil_blocked_without_origin(self):
        r = self.client.post("/api/deadhand/arm",
                             json={"confirm": "ARM"},
                             headers={"Referer": "http://evil.example/x"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "csrf_origin")

    def test_referer_local_allowed(self):
        self.dh.arm_manual.return_value = None
        r = self.client.post("/api/deadhand/arm",
                             json={"confirm": "ARM"},
                             headers={"Referer": "http://127.0.0.1:5000/y"})
        self.assertEqual(r.status_code, 200)

    def test_no_origin_referer_allowed(self):
        self.dh.arm_manual.return_value = None
        r = self.client.post("/api/deadhand/arm", json={"confirm": "ARM"})
        self.assertEqual(r.status_code, 200)

    def test_remote_csrf_denied_before_body(self):
        # remote_addr check runs before origin check
        r = self.client.post("/api/deadhand/arm", json={"confirm": "ARM"},
                             environ_base=REMOTE)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"], "local_only")


class TestRateLimit(DeadHandBase):
    def test_limited_returns_429(self):
        self.limiter.scoped_check.return_value = False
        r = self.client.post("/api/deadhand/arm", json={"confirm": "ARM"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.get_json()["error"], "rate_limited")
        self.dh.arm_manual.assert_not_called()

    def test_limiter_register_called_scoped(self):
        self.client.post("/api/deadhand/arm", json={"confirm": "ARM"})
        self.limiter.register.assert_called_with(
            "system:deadhand", rate=2.0, burst=10)
        self.limiter.scoped_check.assert_called_with(
            "system:deadhand", "127.0.0.1")

    def test_register_failure_fail_open(self):
        self.limiter.register.side_effect = KeyError("exists")
        self.dh.arm_manual.return_value = None
        r = self.client.post("/api/deadhand/arm", json={"confirm": "ARM"})
        self.assertEqual(r.status_code, 200)  # inner except: pass

    def test_limiter_import_failure_fail_open(self):
        with patch(LIMITER, side_effect=ImportError("no limiter")):
            self.dh.arm_manual.return_value = None
            r = self.client.post("/api/deadhand/arm",
                                 json={"confirm": "ARM"})
        self.assertEqual(r.status_code, 200)  # outer except: pass


class TestArm(DeadHandBase):
    def test_success(self):
        self.dh.arm_manual.return_value = None
        self.dh.armed = True
        r = self.client.post("/api/deadhand/arm", json={"confirm": "ARM"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["armed"])
        self.dh.arm_manual.assert_called_once()
        self.dh._audit_op.assert_any_call(
            "arm", actor="api", result="armed", detail="")

    def test_confirm_case_insensitive(self):
        self.dh.arm_manual.return_value = None
        r = self.client.post("/api/deadhand/arm", json={"confirm": "  arm  "})
        self.assertEqual(r.status_code, 200)

    def test_missing_confirm_400(self):
        r = self.client.post("/api/deadhand/arm", json={})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertEqual(body["error"], "confirm_required")
        self.dh.arm_manual.assert_not_called()

    def test_wrong_confirm_400(self):
        r = self.client.post("/api/deadhand/arm", json={"confirm": "disarm"})
        self.assertEqual(r.status_code, 400)
        self.dh.arm_manual.assert_not_called()

    def test_no_body_400(self):
        r = self.client.post("/api/deadhand/arm")
        self.assertEqual(r.status_code, 400)

    def test_exception_500(self):
        self.dh.arm_manual.side_effect = RuntimeError("arm fail")
        r = self.client.post("/api/deadhand/arm", json={"confirm": "ARM"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("arm fail", r.get_json()["error"])


class TestDisarm(DeadHandBase):
    def test_success(self):
        r = self.client.post("/api/deadhand/disarm",
                             json={"reason": "maintenance window"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["sealed"])
        self.dh.disarm.assert_called_once()
        self.dh._audit_op.assert_any_call(
            "disarm", actor="api", result="disarmed",
            detail="reason=maintenance window")

    def test_missing_reason_400(self):
        r = self.client.post("/api/deadhand/disarm", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "reason_required")
        self.dh.disarm.assert_not_called()

    def test_short_reason_400(self):
        r = self.client.post("/api/deadhand/disarm", json={"reason": "ab"})
        self.assertEqual(r.status_code, 400)

    def test_blank_reason_400(self):
        r = self.client.post("/api/deadhand/disarm",
                             json={"reason": "   "})
        self.assertEqual(r.status_code, 400)

    def test_no_body_400(self):
        r = self.client.post("/api/deadhand/disarm")
        self.assertEqual(r.status_code, 400)

    def test_reason_truncated_120_in_audit(self):
        long_reason = "r" * 300
        self.client.post("/api/deadhand/disarm",
                         json={"reason": long_reason})
        kwargs = self.dh._audit_op.call_args.kwargs
        self.assertEqual(kwargs["detail"], "reason=" + "r" * 120)

    def test_remote_403(self):
        r = self.client.post("/api/deadhand/disarm",
                             json={"reason": "valid"}, environ_base=REMOTE)
        self.assertEqual(r.status_code, 403)
        self.dh.disarm.assert_not_called()

    def test_exception_500(self):
        self.dh.disarm.side_effect = RuntimeError("d fail")
        r = self.client.post("/api/deadhand/disarm",
                             json={"reason": "valid"})
        self.assertEqual(r.status_code, 500)


class TestReset(DeadHandBase):
    def test_success(self):
        r = self.client.post("/api/deadhand/reset",
                             json={"reason": "clean slate"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["dead_hand"], {"armed": False})
        self.dh.reset.assert_called_once_with(reason="clean slate")

    def test_missing_reason_400(self):
        r = self.client.post("/api/deadhand/reset", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "reason_required")
        self.dh.reset.assert_not_called()

    def test_short_reason_400(self):
        r = self.client.post("/api/deadhand/reset", json={"reason": "x"})
        self.assertEqual(r.status_code, 400)

    def test_remote_403(self):
        r = self.client.post("/api/deadhand/reset",
                             json={"reason": "valid"}, environ_base=REMOTE)
        self.assertEqual(r.status_code, 403)

    def test_exception_500(self):
        self.dh.reset.side_effect = RuntimeError("r fail")
        r = self.client.post("/api/deadhand/reset",
                             json={"reason": "valid"})
        self.assertEqual(r.status_code, 500)


class TestReseal(DeadHandBase):
    def test_success(self):
        r = self.client.post("/api/deadhand/reseal",
                             json={"reason": "after update"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["sealed_files"], 4)
        self.dh._audit_op.assert_any_call(
            "reseal", actor="api", result="sealed=4",
            detail="reason=after update")

    def test_missing_reason_400(self):
        r = self.client.post("/api/deadhand/reseal", json={})
        self.assertEqual(r.status_code, 400)
        self.dh.reseal.assert_not_called()

    def test_short_reason_400(self):
        r = self.client.post("/api/deadhand/reseal", json={"reason": "no"})
        self.assertEqual(r.status_code, 400)

    def test_remote_403(self):
        r = self.client.post("/api/deadhand/reseal",
                             json={"reason": "valid"}, environ_base=REMOTE)
        self.assertEqual(r.status_code, 403)

    def test_exception_500(self):
        self.dh.reseal.side_effect = RuntimeError("rs fail")
        r = self.client.post("/api/deadhand/reseal",
                             json={"reason": "valid"})
        self.assertEqual(r.status_code, 500)


class TestUnflag(DeadHandBase):
    def test_success_identity(self):
        r = self.client.post("/api/deadhand/unflag", json={
            "identity": "agent-x", "reason": "false positive"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["removed"], 2)
        self.dh.unflag.assert_called_once_with(
            identity="agent-x", clear_all=False,
            reason="false positive")

    def test_success_clear_all(self):
        r = self.client.post("/api/deadhand/unflag", json={
            "all": True, "reason": "mass pardon"})
        self.assertEqual(r.status_code, 200)
        self.dh.unflag.assert_called_once_with(
            identity="", clear_all=True, reason="mass pardon")

    def test_missing_identity_and_all_400(self):
        r = self.client.post("/api/deadhand/unflag",
                             json={"reason": "valid"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"],
                         "identity or {all:true} required")
        self.dh.unflag.assert_not_called()

    def test_missing_reason_400(self):
        # reason checked BEFORE identity
        r = self.client.post("/api/deadhand/unflag",
                             json={"identity": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "reason_required")

    def test_short_reason_400(self):
        r = self.client.post("/api/deadhand/unflag",
                             json={"identity": "x", "reason": "ab"})
        self.assertEqual(r.status_code, 400)

    def test_remote_403(self):
        r = self.client.post("/api/deadhand/unflag", json={
            "identity": "x", "reason": "valid"}, environ_base=REMOTE)
        self.assertEqual(r.status_code, 403)

    def test_exception_500(self):
        self.dh.unflag.side_effect = RuntimeError("u fail")
        r = self.client.post("/api/deadhand/unflag", json={
            "identity": "x", "reason": "valid"})
        self.assertEqual(r.status_code, 500)


class TestHelpers(DeadHandBase):
    def test_reason_strips(self):
        with self.app.test_request_context(
                "/", json={"reason": "  padded  "}):
            self.assertEqual(_reason(), "padded")

    def test_reason_missing_empty(self):
        with self.app.test_request_context("/", json={}):
            self.assertEqual(_reason(), "")

    def test_reason_non_string_coerced(self):
        with self.app.test_request_context("/", json={"reason": 123}):
            self.assertEqual(_reason(), "123")

    def test_rate_limit_returns_none_when_ok(self):
        with self.app.test_request_context("/"):
            self.assertIsNone(_rate_limit())

    def test_audit_swallows_exceptions(self):
        from orbit.core.dead_hand_bp import _audit
        with patch(ENGINE, side_effect=RuntimeError("eng")):
            _audit("op")  # must not raise


if __name__ == "__main__":
    unittest.main()
