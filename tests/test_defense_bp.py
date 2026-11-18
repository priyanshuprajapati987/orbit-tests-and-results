"""Unit tests for orbit/orbit/core/defense_bp.py."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.defense_bp import defense_bp

IMMORTALITY = "orbit.core.immortality.get_immortality_engine"
GRID = "orbit.core.defense_grid.get_defense_grid"
VULN = "orbit.core.vuln_scanner.get_vuln_scanner"
ROLLBACK = "orbit.core.rollback.get_rollback_manager"
GUARDRAILS = "orbit.core.guardrails.get_guardrails"
HEALER = "orbit.core.self_healer.get_self_healer"

ALL_TARGETS = (IMMORTALITY, GRID, VULN, ROLLBACK, GUARDRAILS, HEALER)


def _probe(component="db", healthy=True, latency=1.25, detail="ok"):
    return SimpleNamespace(component=component, healthy=healthy,
                           latency_ms=latency, detail=detail)


def _threat(blocked=False, layer="input"):
    t = MagicMock()
    t.blocked = blocked
    t.to_dict.return_value = {"blocked": blocked, "layer": layer}
    return t


def _finding(name="CVE-0"):
    f = MagicMock()
    f.to_dict.return_value = {"finding": name}
    return f


def _point(pid="p1", category="custom"):
    p = MagicMock()
    p.to_dict.return_value = {"id": pid, "category": category}
    p.category = category
    return p


class DefenseBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(defense_bp)
        self.client = self.app.test_client()

        self.immortality = MagicMock()
        self.grid = MagicMock()
        self.vuln = MagicMock()
        self.rollback = MagicMock()
        self.guardrails = MagicMock()
        self.healer = MagicMock()

        self.rollback.store = MagicMock()
        self.rollback.store.get_stats.return_value = {"points": 5}
        self.rollback.store.list_points.return_value = ["p1"]
        self.rollback.store.create_point.return_value = _point()
        self.rollback.store.get_point.return_value = None
        self.rollback.store.delete_point.return_value = True

        self.guardrails.check_input.return_value = (True, None)
        self.guardrails.get_stats.return_value = {"enabled": True}

        for target, mock in (
            (IMMORTALITY, self.immortality),
            (GRID, self.grid),
            (VULN, self.vuln),
            (ROLLBACK, self.rollback),
            (GUARDRAILS, self.guardrails),
            (HEALER, self.healer),
        ):
            p = patch(target, return_value=mock)
            p.start()
            self.addCleanup(p.stop)

    def test_blueprint_name(self):
        self.assertEqual(defense_bp.name, "defense_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/defense/status",
                  "/api/defense/immortality",
                  "/api/defense/immortality/start",
                  "/api/defense/immortality/stop",
                  "/api/defense/immortality/probe",
                  "/api/defense/immortality/snapshot",
                  "/api/defense/immortality/restore",
                  "/api/defense/immortality/history",
                  "/api/defense/grid",
                  "/api/defense/grid/scan",
                  "/api/defense/grid/check",
                  "/api/defense/grid/threats",
                  "/api/defense/vulns",
                  "/api/defense/vulns/scan",
                  "/api/defense/vulns/scan/code",
                  "/api/defense/vulns/scan/config",
                  "/api/defense/vulns/scan/deps",
                  "/api/defense/rollback",
                  "/api/defense/rollback/points",
                  "/api/defense/rollback/snapshot",
                  "/api/defense/rollback/restore",
                  "/api/defense/rollback/points/<point_id>",
                  "/api/defense/guardrails",
                  "/api/defense/guardrails/check",
                  "/api/defense/guardrails/violations",
                  "/api/defense/guardrails/enable",
                  "/api/defense/guardrails/disable",
                  "/api/defense/heal",
                  "/api/defense/heal/run",
                  "/api/defense/heal/history"]:
            self.assertIn(p, rules)


class TestStatus(DefenseBase):
    def test_all_ok(self):
        self.immortality.get_status.return_value = {"running": True}
        self.grid.get_status.return_value = {"level": "green"}
        self.vuln.get_stats.return_value = {"scans": 2}
        r = self.client.get("/api/defense/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["immortality"], {"running": True})
        self.assertEqual(body["defense_grid"], {"level": "green"})
        self.assertEqual(body["vuln_scanner"], {"scans": 2})
        self.assertEqual(body["rollback"], {"points": 5})

    def test_engine_failure_500(self):
        self.grid.get_status.side_effect = RuntimeError("grid down")
        r = self.client.get("/api/defense/status")
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertFalse(body["ok"])
        self.assertIn("grid down", body["error"])


class TestImmortality(DefenseBase):
    def test_status(self):
        self.immortality.get_status.return_value = {"daemon": "idle"}
        r = self.client.get("/api/defense/immortality")
        self.assertEqual(r.get_json(), {"ok": True, "daemon": "idle"})

    def test_status_exception_500(self):
        self.immortality.get_status.side_effect = RuntimeError("im fail")
        r = self.client.get("/api/defense/immortality")
        self.assertEqual(r.status_code, 500)

    def test_start_default_interval(self):
        r = self.client.post("/api/defense/immortality/start", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"ok": True, "running": True, "interval": 30.0})
        self.immortality.start.assert_called_once_with(interval=30.0)

    def test_start_custom_interval(self):
        self.client.post("/api/defense/immortality/start",
                         json={"interval": 5})
        self.immortality.start.assert_called_once_with(interval=5.0)

    def test_start_bad_interval_500(self):
        # float() parse inside try -> caught as 500
        r = self.client.post("/api/defense/immortality/start",
                             json={"interval": "abc"})
        self.assertEqual(r.status_code, 500)
        self.immortality.start.assert_not_called()

    def test_start_no_body(self):
        r = self.client.post("/api/defense/immortality/start")
        self.assertEqual(r.status_code, 200)

    def test_start_exception_500(self):
        self.immortality.start.side_effect = RuntimeError("start fail")
        r = self.client.post("/api/defense/immortality/start", json={})
        self.assertEqual(r.status_code, 500)

    def test_stop(self):
        r = self.client.post("/api/defense/immortality/stop")
        self.assertEqual(r.get_json(), {"ok": True, "running": False})
        self.immortality.stop.assert_called_once()

    def test_stop_exception_500(self):
        self.immortality.stop.side_effect = RuntimeError("stop fail")
        r = self.client.post("/api/defense/immortality/stop")
        self.assertEqual(r.status_code, 500)

    def test_probe_success(self):
        self.immortality.probe_all.return_value = [
            _probe("db", True, 1.234, "up"),
            _probe("fs", False, 9.876, "slow")]
        r = self.client.post("/api/defense/immortality/probe")
        self.assertEqual(r.status_code, 200)
        probes = r.get_json()["probes"]
        self.assertEqual(len(probes), 2)
        self.assertEqual(probes[0], {"component": "db", "healthy": True,
                                     "latency_ms": 1.2, "detail": "up"})
        self.assertEqual(probes[1]["latency_ms"], 9.9)  # rounded 1dp

    def test_probe_empty(self):
        self.immortality.probe_all.return_value = []
        r = self.client.post("/api/defense/immortality/probe")
        self.assertEqual(r.get_json()["probes"], [])

    def test_probe_exception_500(self):
        self.immortality.probe_all.side_effect = RuntimeError("probe fail")
        r = self.client.post("/api/defense/immortality/probe")
        self.assertEqual(r.status_code, 500)

    def test_snapshot_success(self):
        snap = MagicMock()
        snap.to_dict.return_value = {"id": "s1"}
        self.immortality.save_snapshot.return_value = snap
        r = self.client.post("/api/defense/immortality/snapshot")
        self.assertEqual(r.get_json(), {"ok": True, "snapshot": {"id": "s1"}})

    def test_snapshot_none_500(self):
        self.immortality.save_snapshot.return_value = None
        r = self.client.post("/api/defense/immortality/snapshot")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "Snapshot failed")

    def test_snapshot_exception_500(self):
        self.immortality.save_snapshot.side_effect = RuntimeError("snap fail")
        r = self.client.post("/api/defense/immortality/snapshot")
        self.assertEqual(r.status_code, 500)

    def test_restore_success(self):
        self.immortality.restore_latest.return_value = {"id": "s1"}
        r = self.client.post("/api/defense/immortality/restore")
        self.assertEqual(r.get_json(),
                         {"ok": True, "snapshot": {"id": "s1"}})

    def test_restore_none_404(self):
        self.immortality.restore_latest.return_value = None
        r = self.client.post("/api/defense/immortality/restore")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "No snapshots available")

    def test_restore_exception_500(self):
        self.immortality.restore_latest.side_effect = RuntimeError("r fail")
        r = self.client.post("/api/defense/immortality/restore")
        self.assertEqual(r.status_code, 500)

    def test_history_default_limit(self):
        self.immortality.get_health_history.return_value = ["h1"]
        r = self.client.get("/api/defense/immortality/history")
        self.assertEqual(r.get_json(), {"ok": True, "history": ["h1"]})
        self.immortality.get_health_history.assert_called_once_with(50)

    def test_history_custom_limit(self):
        self.immortality.get_health_history.return_value = []
        self.client.get("/api/defense/immortality/history?limit=5")
        self.immortality.get_health_history.assert_called_once_with(5)

    def test_history_bad_limit_defaults_50(self):
        self.immortality.get_health_history.return_value = []
        self.client.get("/api/defense/immortality/history?limit=abc")
        self.immortality.get_health_history.assert_called_once_with(50)

    def test_history_exception_500(self):
        self.immortality.get_health_history.side_effect = RuntimeError("h")
        r = self.client.get("/api/defense/immortality/history")
        self.assertEqual(r.status_code, 500)


class TestGrid(DefenseBase):
    def test_status(self):
        self.grid.get_status.return_value = {"armed": True}
        r = self.client.get("/api/defense/grid")
        self.assertEqual(r.get_json(), {"ok": True, "armed": True})

    def test_status_exception_500(self):
        self.grid.get_status.side_effect = RuntimeError("g fail")
        r = self.client.get("/api/defense/grid")
        self.assertEqual(r.status_code, 500)

    def test_scan_blocked(self):
        self.grid.scan_input.return_value = [
            _threat(True, "injection"), _threat(False)]
        r = self.client.post("/api/defense/grid/scan",
                             json={"text": "DROP TABLE",
                                   "source": "chat"})
        body = r.get_json()
        self.assertTrue(body["blocked"])
        self.assertEqual(body["threat_count"], 2)
        self.assertEqual(body["threats"][0], {"blocked": True,
                                              "layer": "injection"})
        self.grid.scan_input.assert_called_once_with(
            "DROP TABLE", source="chat")

    def test_scan_clean_defaults(self):
        self.grid.scan_input.return_value = []
        r = self.client.post("/api/defense/grid/scan", json={"text": "hi"})
        body = r.get_json()
        self.assertFalse(body["blocked"])
        self.assertEqual(body["threat_count"], 0)
        self.grid.scan_input.assert_called_once_with("hi", source="api")

    def test_scan_no_body(self):
        self.grid.scan_input.return_value = []
        r = self.client.post("/api/defense/grid/scan")
        self.assertEqual(r.status_code, 200)

    def test_scan_exception_500(self):
        self.grid.scan_input.side_effect = RuntimeError("scan fail")
        r = self.client.post("/api/defense/grid/scan", json={})
        self.assertEqual(r.status_code, 500)

    def test_check(self):
        self.grid.periodic_check.return_value = [_threat(True)]
        r = self.client.post("/api/defense/grid/check")
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["threat_count"], 1)
        self.grid.periodic_check.assert_called_once()

    def test_check_empty(self):
        self.grid.periodic_check.return_value = []
        r = self.client.post("/api/defense/grid/check")
        self.assertEqual(r.get_json()["threat_count"], 0)

    def test_check_exception_500(self):
        self.grid.periodic_check.side_effect = RuntimeError("chk")
        r = self.client.post("/api/defense/grid/check")
        self.assertEqual(r.status_code, 500)

    def test_threats_default(self):
        self.grid.get_threats.return_value = ["t1", "t2"]
        r = self.client.get("/api/defense/grid/threats")
        self.assertEqual(r.get_json(),
                         {"ok": True, "threats": ["t1", "t2"]})
        self.grid.get_threats.assert_called_once_with(50, None)

    def test_threats_filter_args(self):
        self.grid.get_threats.return_value = []
        self.client.get("/api/defense/grid/threats?limit=3&layer=output")
        self.grid.get_threats.assert_called_once_with(3, "output")

    def test_threats_exception_500(self):
        self.grid.get_threats.side_effect = RuntimeError("th")
        r = self.client.get("/api/defense/grid/threats")
        self.assertEqual(r.status_code, 500)


class TestVulns(DefenseBase):
    def test_last_report_exists(self):
        self.vuln.get_last_report.return_value = {"score": 91}
        r = self.client.get("/api/defense/vulns")
        self.assertEqual(r.get_json(),
                         {"ok": True, "report": {"score": 91}})

    def test_last_report_none(self):
        self.vuln.get_last_report.return_value = None
        r = self.client.get("/api/defense/vulns")
        self.assertEqual(r.get_json(),
                         {"ok": True, "report": None,
                          "detail": "No scan yet"})

    def test_last_report_exception_500(self):
        self.vuln.get_last_report.side_effect = RuntimeError("lr")
        r = self.client.get("/api/defense/vulns")
        self.assertEqual(r.status_code, 500)

    def test_full_scan(self):
        rep = MagicMock()
        rep.to_dict.return_value = {"findings": 4}
        self.vuln.full_scan.return_value = rep
        r = self.client.post("/api/defense/vulns/scan")
        self.assertEqual(r.get_json(),
                         {"ok": True, "report": {"findings": 4}})
        self.vuln.full_scan.assert_called_once()

    def test_full_scan_exception_500(self):
        self.vuln.full_scan.side_effect = RuntimeError("fs")
        r = self.client.post("/api/defense/vulns/scan")
        self.assertEqual(r.status_code, 500)

    def test_code_scan(self):
        rep = MagicMock()
        rep.to_dict.return_value = {"code": 1}
        self.vuln.scan_code.return_value = rep
        r = self.client.post("/api/defense/vulns/scan/code")
        self.assertEqual(r.get_json(), {"ok": True, "report": {"code": 1}})

    def test_code_scan_exception_500(self):
        self.vuln.scan_code.side_effect = RuntimeError("sc")
        r = self.client.post("/api/defense/vulns/scan/code")
        self.assertEqual(r.status_code, 500)

    def test_config_scan(self):
        self.vuln.scan_config.return_value = [_finding("cfg1")]
        r = self.client.post("/api/defense/vulns/scan/config")
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["findings"], [{"finding": "cfg1"}])

    def test_config_scan_empty(self):
        self.vuln.scan_config.return_value = []
        r = self.client.post("/api/defense/vulns/scan/config")
        self.assertEqual(r.get_json()["count"], 0)

    def test_config_scan_exception_500(self):
        self.vuln.scan_config.side_effect = RuntimeError("cfg")
        r = self.client.post("/api/defense/vulns/scan/config")
        self.assertEqual(r.status_code, 500)

    def test_deps_scan(self):
        self.vuln.scan_dependencies.return_value = [
            _finding("dep1"), _finding("dep2")]
        r = self.client.post("/api/defense/vulns/scan/deps")
        body = r.get_json()
        self.assertEqual(body["count"], 2)

    def test_deps_scan_exception_500(self):
        self.vuln.scan_dependencies.side_effect = RuntimeError("dep")
        r = self.client.post("/api/defense/vulns/scan/deps")
        self.assertEqual(r.status_code, 500)


class TestRollback(DefenseBase):
    def test_status(self):
        r = self.client.get("/api/defense/rollback")
        self.assertEqual(r.get_json(), {"ok": True, "points": 5})
        self.rollback.store.get_stats.assert_called_once()

    def test_status_exception_500(self):
        self.rollback.store.get_stats.side_effect = RuntimeError("st")
        r = self.client.get("/api/defense/rollback")
        self.assertEqual(r.status_code, 500)

    def test_points_default(self):
        r = self.client.get("/api/defense/rollback/points")
        self.assertEqual(r.get_json(),
                         {"ok": True, "points": ["p1"], "count": 1})
        self.rollback.store.list_points.assert_called_once_with(None, 50)

    def test_points_filter_args(self):
        self.rollback.store.list_points.return_value = []
        self.client.get(
            "/api/defense/rollback/points?category=file&limit=2")
        self.rollback.store.list_points.assert_called_once_with("file", 2)

    def test_points_exception_500(self):
        self.rollback.store.list_points.side_effect = RuntimeError("lp")
        r = self.client.get("/api/defense/rollback/points")
        self.assertEqual(r.status_code, 500)

    def test_snapshot_defaults(self):
        r = self.client.post("/api/defense/rollback/snapshot", json={})
        self.assertEqual(r.get_json(),
                         {"ok": True, "point": {"id": "p1",
                                                "category": "custom"}})
        self.rollback.store.create_point.assert_called_once_with(
            label="manual", category="custom", data=None,
            source_path=None)

    def test_snapshot_full_fields(self):
        self.client.post("/api/defense/rollback/snapshot", json={
            "label": "pre-update", "category": "config",
            "data": {"a": 1}, "source_path": "C:/cfg.yml"})
        self.rollback.store.create_point.assert_called_once_with(
            label="pre-update", category="config", data={"a": 1},
            source_path="C:/cfg.yml")

    def test_snapshot_exception_500(self):
        self.rollback.store.create_point.side_effect = RuntimeError("cp")
        r = self.client.post("/api/defense/rollback/snapshot", json={})
        self.assertEqual(r.status_code, 500)

    def test_restore_missing_point_id_400(self):
        r = self.client.post("/api/defense/rollback/restore", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "point_id required")
        self.rollback.store.get_point.assert_not_called()

    def test_restore_not_found_404(self):
        self.rollback.store.get_point.return_value = None
        r = self.client.post("/api/defense/rollback/restore",
                             json={"point_id": "nope"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Point not found")

    def test_restore_file_category(self):
        self.rollback.store.get_point.return_value = _point("p1", "file")
        result = MagicMock()
        result.success = True
        result.detail = "restored ok"
        self.rollback.restore_file.return_value = result
        r = self.client.post("/api/defense/rollback/restore",
                             json={"point_id": "p1"})
        self.assertEqual(r.get_json(),
                         {"ok": True, "restored": True,
                          "detail": "restored ok"})
        self.rollback.restore_file.assert_called_once_with("p1")

    def test_restore_file_failure(self):
        self.rollback.store.get_point.return_value = _point("p1", "file")
        result = MagicMock()
        result.success = False
        result.detail = "missing"
        self.rollback.restore_file.return_value = result
        r = self.client.post("/api/defense/rollback/restore",
                             json={"point_id": "p1"})
        self.assertEqual(r.get_json()["ok"], False)

    def test_restore_data_category_with_data(self):
        self.rollback.store.get_point.return_value = _point(
            "p2", "custom")
        self.rollback.store.read_snapshot.return_value = {"x": 1}
        r = self.client.post("/api/defense/rollback/restore",
                             json={"point_id": "p2"})
        self.assertEqual(r.get_json(),
                         {"ok": True, "restored": True, "data": {"x": 1}})
        self.rollback.restore_file.assert_not_called()

    def test_restore_data_category_none_data(self):
        self.rollback.store.get_point.return_value = _point(
            "p2", "custom")
        self.rollback.store.read_snapshot.return_value = None
        r = self.client.post("/api/defense/rollback/restore",
                             json={"point_id": "p2"})
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertNotIn("data", body)

    def test_restore_exception_500(self):
        self.rollback.store.get_point.side_effect = RuntimeError("gp")
        r = self.client.post("/api/defense/rollback/restore",
                             json={"point_id": "p"})
        self.assertEqual(r.status_code, 500)

    def test_delete_success(self):
        r = self.client.delete("/api/defense/rollback/points/p1")
        self.assertEqual(r.get_json(), {"ok": True, "deleted": True})
        self.rollback.store.delete_point.assert_called_once_with("p1")

    def test_delete_not_found_404(self):
        self.rollback.store.delete_point.return_value = False
        r = self.client.delete("/api/defense/rollback/points/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Point not found")

    def test_delete_exception_500(self):
        self.rollback.store.delete_point.side_effect = RuntimeError("dp")
        r = self.client.delete("/api/defense/rollback/points/p1")
        self.assertEqual(r.status_code, 500)


class TestGuardrails(DefenseBase):
    def test_status(self):
        r = self.client.get("/api/defense/guardrails")
        self.assertEqual(r.get_json(), {"ok": True, "enabled": True})

    def test_status_exception_500(self):
        self.guardrails.get_stats.side_effect = RuntimeError("gs")
        r = self.client.get("/api/defense/guardrails")
        self.assertEqual(r.status_code, 500)

    def test_check_allowed(self):
        self.guardrails.check_input.return_value = (True, None)
        r = self.client.post("/api/defense/guardrails/check",
                             json={"text": "hello"})
        body = r.get_json()
        self.assertTrue(body["allowed"])
        self.assertIsNone(body["violation"])
        self.assertNotIn("response", body)
        self.guardrails.check_input.assert_called_once_with("hello")

    def test_check_violation(self):
        viol = MagicMock()
        viol.to_dict.return_value = {"principle": "honesty"}
        viol.principle = "honesty"
        self.guardrails.check_input.return_value = (False, viol)
        self.guardrails.get_response.return_value = "I can't do that."
        r = self.client.post("/api/defense/guardrails/check",
                             json={"text": "lie now"})
        body = r.get_json()
        self.assertFalse(body["allowed"])
        self.assertEqual(body["violation"], {"principle": "honesty"})
        self.assertEqual(body["response"], "I can't do that.")
        self.guardrails.get_response.assert_called_once_with("honesty")

    def test_check_no_body_defaults_empty(self):
        r = self.client.post("/api/defense/guardrails/check")
        self.assertEqual(r.status_code, 200)
        self.guardrails.check_input.assert_called_once_with("")

    def test_check_exception_500(self):
        self.guardrails.check_input.side_effect = RuntimeError("ck")
        r = self.client.post("/api/defense/guardrails/check", json={})
        self.assertEqual(r.status_code, 500)

    def test_violations_default(self):
        self.guardrails.get_violations.return_value = ["v1"]
        r = self.client.get("/api/defense/guardrails/violations")
        self.assertEqual(r.get_json(),
                         {"ok": True, "violations": ["v1"]})
        self.guardrails.get_violations.assert_called_once_with(20)

    def test_violations_custom_limit(self):
        self.guardrails.get_violations.return_value = []
        self.client.get("/api/defense/guardrails/violations?limit=4")
        self.guardrails.get_violations.assert_called_once_with(4)

    def test_violations_exception_500(self):
        self.guardrails.get_violations.side_effect = RuntimeError("vv")
        r = self.client.get("/api/defense/guardrails/violations")
        self.assertEqual(r.status_code, 500)

    def test_enable(self):
        r = self.client.post("/api/defense/guardrails/enable")
        self.assertEqual(r.get_json(), {"ok": True, "enabled": True})
        self.guardrails.enable.assert_called_once()

    def test_enable_exception_500(self):
        self.guardrails.enable.side_effect = RuntimeError("en")
        r = self.client.post("/api/defense/guardrails/enable")
        self.assertEqual(r.status_code, 500)

    def test_disable(self):
        r = self.client.post("/api/defense/guardrails/disable")
        body = r.get_json()
        self.assertEqual(body, {"ok": True, "enabled": False,
                                "warning": "Test mode only!"})
        self.guardrails.disable.assert_called_once()

    def test_disable_exception_500(self):
        self.guardrails.disable.side_effect = RuntimeError("dis")
        r = self.client.post("/api/defense/guardrails/disable")
        self.assertEqual(r.status_code, 500)


class TestHealer(DefenseBase):
    def test_status(self):
        self.healer.get_stats.return_value = {"cycles": 7}
        r = self.client.get("/api/defense/heal")
        self.assertEqual(r.get_json(), {"ok": True, "cycles": 7})

    def test_status_exception_500(self):
        self.healer.get_stats.side_effect = RuntimeError("hs")
        r = self.client.get("/api/defense/heal")
        self.assertEqual(r.status_code, 500)

    def test_run_default_dry_run_true(self):
        cycle = MagicMock()
        cycle.to_dict.return_value = {"fixed": 0}
        self.healer.run_cycle.return_value = cycle
        r = self.client.post("/api/defense/heal/run", json={})
        self.assertEqual(r.get_json(),
                         {"ok": True, "cycle": {"fixed": 0}})
        self.healer.run_cycle.assert_called_once_with(dry_run=True)

    def test_run_real(self):
        cycle = MagicMock()
        cycle.to_dict.return_value = {"fixed": 2}
        self.healer.run_cycle.return_value = cycle
        self.client.post("/api/defense/heal/run",
                         json={"dry_run": False})
        self.healer.run_cycle.assert_called_once_with(dry_run=False)

    def test_run_no_body(self):
        cycle = MagicMock()
        cycle.to_dict.return_value = {}
        self.healer.run_cycle.return_value = cycle
        r = self.client.post("/api/defense/heal/run")
        self.assertEqual(r.status_code, 200)

    def test_run_exception_500(self):
        self.healer.run_cycle.side_effect = RuntimeError("run fail")
        r = self.client.post("/api/defense/heal/run", json={})
        self.assertEqual(r.status_code, 500)

    def test_history_default_limit(self):
        self.healer.get_history.return_value = ["c1"]
        r = self.client.get("/api/defense/heal/history")
        self.assertEqual(r.get_json(), {"ok": True, "cycles": ["c1"]})
        self.healer.get_history.assert_called_once_with(10)

    def test_history_custom_limit(self):
        self.healer.get_history.return_value = []
        self.client.get("/api/defense/heal/history?limit=2")
        self.healer.get_history.assert_called_once_with(2)

    def test_history_exception_500(self):
        self.healer.get_history.side_effect = RuntimeError("gh")
        r = self.client.get("/api/defense/heal/history")
        self.assertEqual(r.status_code, 500)


class TestLazyImportFailure(DefenseBase):
    """Engine getter raising at import/get time -> endpoint 500."""

    def test_status_getter_raises(self):
        with patch(IMMORTALITY, side_effect=ImportError("no engine")):
            r = self.client.get("/api/defense/status")
        self.assertEqual(r.status_code, 500)
        self.assertIn("no engine", r.get_json()["error"])

    def test_immortality_getter_raises(self):
        with patch(IMMORTALITY, side_effect=ImportError("no im")):
            r = self.client.get("/api/defense/immortality")
        self.assertEqual(r.status_code, 500)

    def test_grid_getter_raises(self):
        with patch(GRID, side_effect=ImportError("no grid")):
            r = self.client.post("/api/defense/grid/scan", json={})
        self.assertEqual(r.status_code, 500)

    def test_vuln_getter_raises(self):
        with patch(VULN, side_effect=ImportError("no vuln")):
            r = self.client.post("/api/defense/vulns/scan")
        self.assertEqual(r.status_code, 500)

    def test_rollback_getter_raises(self):
        with patch(ROLLBACK, side_effect=ImportError("no rb")):
            r = self.client.get("/api/defense/rollback/points")
        self.assertEqual(r.status_code, 500)

    def test_guardrails_getter_raises(self):
        with patch(GUARDRAILS, side_effect=ImportError("no gr")):
            r = self.client.post("/api/defense/guardrails/check", json={})
        self.assertEqual(r.status_code, 500)

    def test_healer_getter_raises(self):
        with patch(HEALER, side_effect=ImportError("no heal")):
            r = self.client.get("/api/defense/heal")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
