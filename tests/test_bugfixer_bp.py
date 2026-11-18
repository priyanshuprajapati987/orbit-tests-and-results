"""Unit tests for orbit/orbit/core/bugfixer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.bugfixer_bp import bugfixer_bp


def _finding(fid="f1", auto_fixable=True, fixed=False):
    f = MagicMock()
    f.id = fid
    f.severity = "warning"
    f.category = "bug"
    f.file_path = "a.py"
    f.line_number = 10
    f.code_line = "x = 1"
    f.description = "desc"
    f.auto_fixable = auto_fixable
    f.fixed = fixed
    return f


def _report(findings=None, **kw):
    r = MagicMock()
    r.scan_id = "scan-1"
    r.timestamp = "2026-01-01T00:00:00"
    r.files_scanned = 5
    r.findings = findings if findings is not None else [_finding()]
    r.scan_duration_ms = 12.5
    r.fixes_applied = 2
    r.fixes_failed = 1
    r.tests_passed = True
    r.tests_output = "ok" * 400  # 800 chars -> capped to 500
    r.summary.return_value = {"total": 1}
    return r


class BugfixerBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bugfixer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(bugfixer_bp.name, "bugfixer_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/bugfixer/status", "/api/bugfixer/scan",
                  "/api/bugfixer/fix", "/api/bugfixer/full-cycle",
                  "/api/bugfixer/history"]:
            self.assertIn(p, rules)


class TestStatus(BugfixerBpBase):
    def test_status(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.get_status.return_value = {"scans": 3}
            r = self.client.get("/api/bugfixer/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["scans"], 3)


class TestScan(BugfixerBpBase):
    def test_scan_no_path(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.scan.return_value = _report()
            r = self.client.post("/api/bugfixer/scan", json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["scan_id"], "scan-1")
        self.assertEqual(body["files_scanned"], 5)
        self.assertEqual(body["findings_count"], 1)
        self.assertEqual(body["scan_duration_ms"], 12.5)
        self.assertEqual(len(body["findings"]), 1)
        f = body["findings"][0]
        self.assertEqual(f["id"], "f1")
        self.assertEqual(f["severity"], "warning")
        self.assertTrue(f["auto_fixable"])
        gb.return_value.scan.assert_called_once_with(None)

    def test_scan_with_allowed_path(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.scan.return_value = _report(findings=[])
            r = self.client.post("/api/bugfixer/scan", json={"path": "."})
        self.assertEqual(r.status_code, 200)
        gb.return_value.scan.assert_called_once_with(".")

    def test_scan_blocked_path_403(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            r = self.client.post("/api/bugfixer/scan",
                                 json={"path": "C:/Windows/System32"})
        self.assertEqual(r.status_code, 403)
        body = r.get_json()
        self.assertEqual(body["error"], "path not allowed")
        self.assertEqual(body["reason"], "blocked_system_directory")
        gb.return_value.scan.assert_not_called()

    def test_scan_findings_capped_at_200(self):
        findings = [_finding(str(i)) for i in range(250)]
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.scan.return_value = _report(findings=findings)
            r = self.client.post("/api/bugfixer/scan", json={})
        body = r.get_json()
        self.assertEqual(len(body["findings"]), 200)
        self.assertEqual(body["findings_count"], 250)  # count is full length

    def test_scan_no_body(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.scan.return_value = _report(findings=[])
            r = self.client.post("/api/bugfixer/scan")
        self.assertEqual(r.status_code, 200)


class TestFix(BugfixerBpBase):
    def test_fix_defaults(self):
        rep = _report()
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.scan.return_value = rep
            gb.return_value.auto_fix.return_value = rep
            r = self.client.post("/api/bugfixer/fix", json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["fixes_applied"], 2)
        self.assertEqual(body["fixes_failed"], 1)
        gb.return_value.auto_fix.assert_called_once_with(rep, 50)
        # only auto_fixable findings included
        self.assertEqual(len(body["findings"]), 1)
        self.assertFalse(body["findings"][0]["fixed"])

    def test_fix_custom_max(self):
        rep = _report()
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.scan.return_value = rep
            gb.return_value.auto_fix.return_value = rep
            r = self.client.post("/api/bugfixer/fix",
                                 json={"path": ".", "max_fixes": 10})
        gb.return_value.auto_fix.assert_called_once_with(rep, 10)
        gb.return_value.scan.assert_called_once_with(".")

    def test_fix_excludes_non_autofixable(self):
        findings = [_finding("a", auto_fixable=True),
                    _finding("b", auto_fixable=False)]
        rep = _report(findings=findings)
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.scan.return_value = rep
            gb.return_value.auto_fix.return_value = rep
            r = self.client.post("/api/bugfixer/fix", json={})
        body = r.get_json()
        self.assertEqual(len(body["findings"]), 1)
        self.assertEqual(body["findings"][0]["id"], "a")

    def test_fix_blocked_path_403(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            r = self.client.post("/api/bugfixer/fix",
                                 json={"path": "C:/Windows/System32"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("mutation", r.get_json()["error"])
        gb.return_value.scan.assert_not_called()


class TestFullCycle(BugfixerBpBase):
    def test_full_cycle(self):
        rep = _report()
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.full_cycle.return_value = rep
            r = self.client.post("/api/bugfixer/full-cycle", json={"path": "."})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["scan_id"], "scan-1")
        self.assertEqual(body["tests_passed"], True)
        self.assertEqual(body["fixes_applied"], 2)
        self.assertEqual(body["findings_count"], 1)
        # tests_output capped at 500
        self.assertEqual(len(body["tests_output"]), 500)
        gb.return_value.full_cycle.assert_called_once_with(".", 50)

    def test_full_cycle_no_path_default_max(self):
        rep = _report()
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.full_cycle.return_value = rep
            r = self.client.post("/api/bugfixer/full-cycle", json={})
        gb.return_value.full_cycle.assert_called_once_with(None, 50)

    def test_full_cycle_custom_max(self):
        rep = _report()
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.full_cycle.return_value = rep
            r = self.client.post("/api/bugfixer/full-cycle",
                                 json={"max_fixes": 7})
        gb.return_value.full_cycle.assert_called_once_with(None, 7)

    def test_full_cycle_blocked_path_403(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            r = self.client.post("/api/bugfixer/full-cycle",
                                 json={"path": "C:/Windows/System32"})
        self.assertEqual(r.status_code, 403)
        gb.return_value.full_cycle.assert_not_called()

    def test_full_cycle_tests_output_short(self):
        rep = _report()
        rep.tests_output = "short"
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.full_cycle.return_value = rep
            r = self.client.post("/api/bugfixer/full-cycle", json={})
        self.assertEqual(r.get_json()["tests_output"], "short")


class TestHistory(BugfixerBpBase):
    def test_history_default(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.get_history.return_value = [{"scan_id": "s1"}]
            r = self.client.get("/api/bugfixer/history")
        self.assertEqual(r.status_code, 200)
        gb.return_value.get_history.assert_called_once_with(10)

    def test_history_custom_limit(self):
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.get_history.return_value = []
            r = self.client.get("/api/bugfixer/history?limit=25")
        gb.return_value.get_history.assert_called_once_with(25)

    def test_history_bad_limit_fallback(self):
        # Flask type=int falls back to default 10 on parse failure
        with patch("orbit.core.bugfixer_bp.get_bugfixer") as gb:
            gb.return_value.get_history.return_value = []
            r = self.client.get("/api/bugfixer/history?limit=abc")
        gb.return_value.get_history.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
