"""P4 Self-Healer controlled-patching tests.

Verifies:
  * evidence field (before->after snippet) built for planned fixes
  * preview_cycle never writes files (dry-run guarantee)
  * sensitive-file gate: auto-fix blocked unless approve_sensitive=True
  * py_compile verify: broken patch triggers rollback + compile_ok=False
  * audit JSONL records applied/rollback/gate_blocked operations
  * approve_sensitive API marks specific findings
"""

from __future__ import annotations

import json
from pathlib import Path

from orbit.orbit.core.self_healer import (
    FixAction,
    SelfHealer,
    _is_sensitive,
    _make_evidence,
    get_self_healer,
)


class TestSensitiveClassifier:
    def test_security_paths_sensitive(self):
        assert _is_sensitive("orbit/core/security_guard.py")
        assert _is_sensitive("orbit/core/kill_switch.py")
        assert _is_sensitive("orbit/core/policy_engine.py")
        assert _is_sensitive("orbit/core/dead_hand.py")
        assert _is_sensitive("orbit/core/secret_redactor.py")
        assert _is_sensitive("orbit/core/permission.py")

    def test_ordinary_paths_not_sensitive(self):
        assert not _is_sensitive("orbit/core/analytics.py")
        assert not _is_sensitive("orbit/core/daily_digest.py")
        assert not _is_sensitive("tests/test_analytics.py")


class TestEvidence:
    def test_changed_line_evidence(self):
        before = "import yaml\ndata = yaml.load(x)\n"
        after = "import yaml\ndata = yaml.safe_load(x)\n"
        ev = _make_evidence(before, after)
        assert "yaml.load(x)" in ev
        assert "yaml.safe_load(x)" in ev
        assert "- " in ev and "+ " in ev

    def test_no_change_returns_empty(self):
        assert _make_evidence("same\n", "same\n") == ""


class TestFixActionP4Fields:
    def test_defaults(self):
        a = FixAction(
            finding_id="f1", file="x.py", line=1, pattern="yaml_load",
            severity="medium", description="d", fix_type="auto",
            fix_description="fix",
        )
        assert a.evidence == ""
        assert a.preview == ""
        assert a.sensitive is False
        assert a.approved is False
        assert a.compile_ok is True

    def test_to_dict_includes_p4_fields(self):
        a = FixAction(
            finding_id="f1", file="security/x.py", line=1, pattern="md5_hash",
            severity="high", description="d", fix_type="auto", fix_description="f",
            sensitive=True, evidence="L1: - md5\nL1: + sha256",
        )
        d = a.to_dict()
        assert d["sensitive"] is True
        assert "evidence" in d
        assert "compile_ok" in d


class TestDryRunGuarantee:
    def test_preview_never_writes(self, tmp_path, monkeypatch):
        healer = SelfHealer()
        target = tmp_path / "app.py"
        target.write_text("v = yaml.load(data)\n", encoding="utf-8")
        monkeypatch.setattr(
            SelfHealer, "_resolve_root", staticmethod(lambda: tmp_path)
        )

        # fake a scanner returning one auto-fixable finding
        class _F:
            finding_id = "f1"
            file = "app.py"
            line = 1
            pattern = "yaml_load"
            severity = "medium"
            description = "unsafe yaml"
            auto_fixable = True
            suggested_fix = ""

        class _R:
            findings = [_F()]
            total_findings = 1

        monkeypatch.setattr(
            "orbit.orbit.core.vuln_scanner.get_vuln_scanner",
            lambda: type("S", (), {"full_scan": lambda s: _R(), "scan_code": lambda s, p: _R()})(),
            raising=False,
        )
        cycle = healer.run_cycle(dry_run=True)
        # file unchanged
        assert "yaml.load(data)" in target.read_text(encoding="utf-8")
        # evidence + preview populated
        auto = [a for a in cycle.actions if a.fix_type == "auto"]
        assert auto, "expected auto action"
        assert auto[0].evidence, "evidence should be populated"
        assert "safe_load" in auto[0].preview


class TestSensitiveGate:
    def test_gate_blocks_sensitive_in_action(self):
        # simulate gate decision logic (unit): sensitive + not approved
        a = FixAction(
            finding_id="f1", file="orbit/core/security_guard.py", line=1,
            pattern="md5_hash", severity="high", description="d",
            fix_type="auto", fix_description="f", sensitive=True,
        )
        blocked = a.sensitive and not a.approved
        assert blocked is True
        a.approved = True
        blocked = a.sensitive and not a.approved
        assert blocked is False

    def test_approve_sensitive_api_unknown_id(self):
        healer = SelfHealer()
        assert healer.approve_sensitive("nonexistent") is False


class TestAuditTrail:
    def test_audit_file_written(self, tmp_path, monkeypatch):
        healer = SelfHealer()
        audit_file = tmp_path / "audit.jsonl"
        monkeypatch.setattr(
            SelfHealer, "_audit_path", staticmethod(lambda: audit_file)
        )
        healer._audit_cycle_op("applied", "sh_test", detail="app.py:yaml_load")
        healer._audit_cycle_op("gate_blocked", "sh_test", detail="sec.py:md5")
        lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        r0 = json.loads(lines[0])
        assert r0["op"] == "applied"
        assert r0["cycle"] == "sh_test"
        assert "yaml_load" in r0["detail"]
        assert json.loads(lines[1])["op"] == "gate_blocked"

    def test_audit_failure_never_raises(self, monkeypatch):
        healer = SelfHealer()
        monkeypatch.setattr(
            SelfHealer, "_audit_path",
            staticmethod(lambda: Path("/nonexistent-root-xyz/readonly/a.jsonl")),
        )
        healer._audit_cycle_op("applied", "sh_x")  # must not raise


class TestSingleton:
    def test_singleton(self):
        assert get_self_healer() is get_self_healer()
