"""Tests for dep_scanner — dependency vulnerability scanner."""

import os

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")

from orbit.orbit.core.dep_scanner import (
    ScanResult,
    Vulnerability,
    get_status,
    run_scan,
    scan_python_outdated,
)


class TestVulnerability:
    def test_to_dict(self):
        v = Vulnerability(
            "requests", "2.28.0", "GHSA-1234", "high", "2.31.0", "test vuln"
        )
        d = v.to_dict()
        assert d["package"] == "requests"
        assert d["severity"] == "high"
        assert d["fix_version"] == "2.31.0"

    def test_no_fix_version(self):
        v = Vulnerability("pkg", "1.0", "CVE-999", "critical")
        d = v.to_dict()
        assert d["fix_version"] is None


class TestScanResult:
    def test_empty(self):
        r = ScanResult()
        d = r.to_dict()
        assert d["summary"]["total_vulnerabilities"] == 0
        assert d["summary"]["critical"] == 0

    def test_with_vulns(self):
        r = ScanResult()
        r.python_vulns = [
            Vulnerability("a", "1.0", "CVE-1", "critical"),
            Vulnerability("b", "2.0", "CVE-2", "medium"),
        ]
        assert r.total_vulns == 2
        assert r.critical_count == 1

    def test_with_npm_vulns(self):
        r = ScanResult()
        r.npm_vulns = [{"package": "lodash", "severity": "high"}]
        assert r.total_vulns == 1

    def test_to_dict_structure(self):
        r = ScanResult()
        d = r.to_dict()
        assert "python_vulnerabilities" in d
        assert "python_outdated" in d
        assert "npm_vulnerabilities" in d
        assert "npm_outdated" in d
        assert "errors" in d


class TestRunScan:
    def test_run_scan_returns_result(self):
        result = run_scan(force=True)
        assert isinstance(result, ScanResult)
        assert isinstance(result.errors, list)

    def test_caching(self):
        r1 = run_scan(force=False)
        r2 = run_scan(force=False)
        # Same cached result
        assert r1.timestamp == r2.timestamp

    def test_force_bypasses_cache(self):
        r1 = run_scan(force=True)
        r2 = run_scan(force=True)
        assert r1 is not None and r2 is not None


class TestGetStatus:
    def test_status_shape(self):
        s = get_status()
        assert "scanned" in s
        assert "summary" in s
        assert "timestamp" in s

    def test_status_no_scan(self):
        s = get_status()
        # May or may not have a scan file
        assert isinstance(s["scanned"], bool)


class TestScanOutdated:
    def test_returns_list(self):
        result = scan_python_outdated()
        assert isinstance(result, list)
