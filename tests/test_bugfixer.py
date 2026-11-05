"""Tests for BugFixerAgent — scanner + auto-fixer + API."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.core.bugfixer import (
    BugAutoFixer,
    BugFinding,
    BugFixerAgent,
    BugScanner,
    ScanReport,
    get_bugfixer,
)


def _write_temp(code: str) -> str:
    """Write code to a temp file and return the path (file closed)."""
    fd, path = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w") as f:
        f.write(code)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
#  SCANNER TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestBugScanner:
    def setup_method(self):
        self.scanner = BugScanner()

    def test_detects_shell_true(self):
        path = _write_temp("subprocess.run(['ls'], shell=True)\n")
        try:
            findings = self.scanner.scan_file(path)
            security = [f for f in findings if f.category == "security"]
            assert len(security) >= 1
            assert security[0].severity == "CRITICAL"
        finally:
            os.unlink(path)

    def test_detects_eval(self):
        path = _write_temp("result = eval(user_input)\n")
        try:
            findings = self.scanner.scan_file(path)
            security = [f for f in findings if "eval" in f.description.lower()]
            assert len(security) >= 1
        finally:
            os.unlink(path)

    def test_detects_os_system(self):
        path = _write_temp("os.system('rm -rf /')\n")
        try:
            findings = self.scanner.scan_file(path)
            security = [f for f in findings if "os.system" in f.description]
            assert len(security) >= 1
        finally:
            os.unlink(path)

    def test_detects_bare_except(self):
        path = _write_temp("try:\n    pass\nexcept:\n    pass\n")
        try:
            findings = self.scanner.scan_file(path)
            logic = [f for f in findings if "bare except" in f.description.lower()]
            assert len(logic) >= 1
            assert logic[0].auto_fixable is True
        finally:
            os.unlink(path)

    def test_detects_equals_true(self):
        path = _write_temp("if x == True:\n    pass\n")
        try:
            findings = self.scanner.scan_file(path)
            logic = [f for f in findings if "== True" in f.description]
            assert len(logic) >= 1
            assert logic[0].auto_fixable is True
        finally:
            os.unlink(path)

    def test_detects_equals_none(self):
        path = _write_temp("if x == None:\n    pass\n")
        try:
            findings = self.scanner.scan_file(path)
            logic = [f for f in findings if "== None" in f.description]
            assert len(logic) >= 1
        finally:
            os.unlink(path)

    def test_skips_comments(self):
        path = _write_temp("# subprocess.run(['ls'], shell=True)\n")
        try:
            findings = self.scanner.scan_file(path)
            security = [f for f in findings if "shell=True" in f.description]
            assert len(security) == 0
        finally:
            os.unlink(path)

    def test_no_findings_on_clean_code(self):
        path = _write_temp("x = 1\ny = 2\nprint(x + y)\n")
        try:
            findings = self.scanner.scan_file(path)
            assert len(findings) == 0
        finally:
            os.unlink(path)

    def test_scan_report_structure(self):
        path = _write_temp("subprocess.run(['ls'], shell=True)\n")
        try:
            findings = self.scanner.scan_file(path)
            assert len(findings) >= 1
            assert findings[0].file_path == path
            assert findings[0].line_number == 1
            assert findings[0].id != ""
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTO-FIXER TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestBugAutoFixer:
    def setup_method(self):
        self.fixer = BugAutoFixer()

    def test_fix_shell_true(self):
        path = _write_temp("subprocess.run(['ls'], shell=True)\n")
        finding = BugFinding(
            auto_fixable=True, fix_pattern="shell_true", file_path=path, line_number=1
        )
        try:
            result = self.fixer.apply_fix(finding)
            assert result is True
            assert finding.fixed is True
            with open(path) as r:
                content = r.read()
            assert "shell=False" in content
            assert "shell=True" not in content
        finally:
            os.unlink(path)

    def test_fix_equals_none(self):
        path = _write_temp("if x == None:\n    pass\n")
        finding = BugFinding(
            auto_fixable=True, fix_pattern="equals_none", file_path=path, line_number=1
        )
        try:
            result = self.fixer.apply_fix(finding)
            assert result is True
            with open(path) as r:
                content = r.read()
            assert "is None" in content
        finally:
            os.unlink(path)

    def test_fix_not_equals_none(self):
        path = _write_temp("if x != None:\n    pass\n")
        finding = BugFinding(
            auto_fixable=True,
            fix_pattern="not_equals_none",
            file_path=path,
            line_number=1,
        )
        try:
            result = self.fixer.apply_fix(finding)
            assert result is True
            with open(path) as r:
                content = r.read()
            assert "is not None" in content
        finally:
            os.unlink(path)

    def test_no_fix_when_not_auto_fixable(self):
        finding = BugFinding(auto_fixable=False, fix_pattern="")
        result = self.fixer.apply_fix(finding)
        assert result is False

    def test_fix_preserves_syntax(self):
        path = _write_temp("subprocess.run(['ls'], shell=True)\n")
        finding = BugFinding(
            auto_fixable=True, fix_pattern="shell_true", file_path=path, line_number=1
        )
        try:
            result = self.fixer.apply_fix(finding)
            assert result is True
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
#  FULL AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestBugFixerAgent:
    def setup_method(self):
        self.agent = BugFixerAgent()

    def test_scan_returns_report(self):
        report = self.agent.scan("orbit/orbit/calculator.py")
        assert isinstance(report, ScanReport)
        assert report.files_scanned >= 1
        assert report.scan_duration_ms >= 0
        assert isinstance(report.findings, list)

    def test_auto_fix_returns_report(self):
        report = self.agent.scan("orbit/orbit/calculator.py")
        report = self.agent.auto_fix(report, max_fixes=5)
        assert isinstance(report.fixes_applied, int)
        assert report.fixes_applied >= 0

    def test_get_status(self):
        status = self.agent.get_status()
        assert "total_scans" in status
        assert "capabilities" in status
        assert len(status["capabilities"]) > 0

    def test_get_history_empty(self):
        history = self.agent.get_history()
        assert isinstance(history, list)

    def test_full_cycle(self):
        report = self.agent.full_cycle("orbit/orbit/calculator.py", max_fixes=5)
        assert isinstance(report, ScanReport)
        assert isinstance(report.tests_passed, bool)


# ═══════════════════════════════════════════════════════════════════════════════
#  SINGLETON TEST
# ═══════════════════════════════════════════════════════════════════════════════


class TestSingleton:
    def test_get_bugfixer_returns_same_instance(self):
        a = get_bugfixer()
        b = get_bugfixer()
        assert a is b

    def test_instance_has_all_methods(self):
        agent = get_bugfixer()
        assert hasattr(agent, "scan")
        assert hasattr(agent, "auto_fix")
        assert hasattr(agent, "run_tests")
        assert hasattr(agent, "full_cycle")
        assert hasattr(agent, "get_status")
        assert hasattr(agent, "get_history")
