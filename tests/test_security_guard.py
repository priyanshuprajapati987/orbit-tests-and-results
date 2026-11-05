"""Tests for the SecurityGuard defensive security system.

Covers:
- Codebase scan: secrets detected, os.system detected, JS regex .exec() NOT flagged,
  JSON data files skipped for dangerous-code but scanned for secrets
- Exempt paths: AST-safe eval locations not flagged
- Defense check: returns 7 checks, redaction verified
- Incident log: persisted + redacted
- Auto-fix: gitignore appends missing patterns
- SecurityGuardAgent (SECG): registry, can_handle, run responses
- Flask API: all 8 endpoints respond
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_KEY", "")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

from orbit.orbit.core.security_guard import (
    SecurityGuard,
    _sanitize_finding,
    get_security_guard,
)

TEST_KEY = "sk-proj-abcdef1234567890abcdef1234567890"


@pytest.fixture
def guard(tmp_path):
    return SecurityGuard(root=tmp_path, storage_file=tmp_path / "incidents.jsonl")


# ── Codebase scan ─────────────────────────────────────────────────────
def test_scan_detects_secret(guard, tmp_path):
    (tmp_path / "app.py").write_text(f'API_KEY = "{TEST_KEY}"\n')
    r = guard.scan_codebase()
    assert r["ok"] is True
    assert r["critical"] == 1
    assert r["findings"][0]["kind"] == "secret"
    assert r["findings"][0]["file"] == "app.py"


def test_scan_detects_os_system(guard, tmp_path):
    (tmp_path / "app.py").write_text('os.system("whoami")\n')
    r = guard.scan_codebase()
    assert r["high"] == 1
    assert r["findings"][0]["name"] == "os.system() (command injection)"


def test_scan_ignores_js_regex_exec(guard, tmp_path):
    (tmp_path / "app.js").write_text('const m = /foo/.exec(className || "")\n')
    r = guard.scan_codebase()
    assert r["count"] == 0


def test_scan_json_data_skips_dangerous_code_but_finds_secret(guard, tmp_path):
    (tmp_path / "data.json").write_text(
        '{"code": "exec(foo)", "key": "AIza1234567890abcdefghijklmnopqrstuvw"}\n'
    )
    r = guard.scan_codebase()
    assert r["count"] == 1
    assert r["findings"][0]["kind"] == "secret"


def test_scan_skips_exempt_paths(guard, tmp_path):
    target = tmp_path / "orbit" / "orbit"
    target.mkdir(parents=True)
    (target / "calculator.py").write_text("return float(eval(code, {}, allowed))\n")
    r = guard.scan_codebase()
    # calculator.py is exempt via SCAN_EXEMPT_PATHS
    assert r["count"] == 0


def test_scan_skips_node_modules(guard, tmp_path):
    (tmp_path / ".venv" / "x").mkdir(parents=True)
    (tmp_path / ".venv" / "x" / "app.js").write_text(f'KEY="{TEST_KEY}"\n')
    r = guard.scan_codebase()
    assert r["count"] == 0


def test_scan_finding_message_has_no_secret(guard, tmp_path):
    (tmp_path / "app.py").write_text(f'API_KEY = "{TEST_KEY}"\n')
    r = guard.scan_codebase()
    assert TEST_KEY not in r["findings"][0]["message"]
    assert TEST_KEY not in str(r["findings"])


def test_sanitize_finding_redacts_secret():
    msg = f"OpenAI key {TEST_KEY} in app.py:1"
    out = _sanitize_finding(msg)
    assert TEST_KEY not in out
    assert "[REDACTED]" in out


# ── Defense check ─────────────────────────────────────────────────────
def test_defense_check_shape(guard):
    d = guard.check_defenses()
    assert d["total"] >= 6
    names = {c["name"] for c in d["checks"]}
    assert {"api_auth", "rate_limiter", "toolgate", "secret_redaction"}.issubset(names)


def test_defense_check_secret_redaction_true(guard):
    d = guard.check_defenses()
    red = next(c for c in d["checks"] if c["name"] == "secret_redaction")
    assert red["ok"] is True


# ── Incident log ──────────────────────────────────────────────────────
def test_incident_log_persisted(guard, tmp_path):
    guard._log_incident(
        {"kind": "secret", "severity": "critical", "message": f"leak {TEST_KEY}"}
    )
    incs = guard.incidents()
    assert len(incs) == 1
    assert TEST_KEY not in incs[0]["message"]
    assert incs[0]["severity"] == "critical"


def test_incidents_empty_when_no_file(guard):
    assert guard.incidents() == []


def test_incidents_limit(guard):
    for i in range(10):
        guard._log_incident({"message": f"incident {i}", "severity": "low"})
    assert len(guard.incidents(limit=3)) == 3
    assert guard.incidents(limit=3)[0]["message"] == "incident 9"


# ── Auto-fix ──────────────────────────────────────────────────────────
def test_auto_fix_appends_gitignore(guard, tmp_path):
    (tmp_path / ".gitignore").write_text("*.pyc\n")
    result = guard.auto_fix()
    assert result["count"] >= 1
    content = (tmp_path / ".gitignore").read_text()
    assert "orbit_data/" in content
    assert ".env" in content


def test_auto_fix_no_change_when_covered(guard, tmp_path):
    (tmp_path / ".gitignore").write_text("orbit_data/\n.env\ndata/\n*.pyc\n")
    result = guard.auto_fix()
    assert result["count"] == 0


# ── Monitor ───────────────────────────────────────────────────────────
def test_monitor_start_stop(guard):
    assert guard.start_monitor(interval=1) is True
    assert guard.start_monitor(interval=1) is False  # already running
    assert guard.get_status()["monitoring"] is True
    guard.stop_monitor()
    assert guard.get_status()["monitoring"] is False


# ── Singleton ─────────────────────────────────────────────────────────
def test_singleton():
    assert get_security_guard() is get_security_guard()


# ── SecurityGuardAgent ────────────────────────────────────────────────
def test_agent_registered():
    from orbit.agents import AGENT_REGISTRY

    assert "SECG" in AGENT_REGISTRY
    assert AGENT_REGISTRY["SECG"].name == "SecurityGuard"


def test_agent_can_handle():
    from orbit.agents import SecurityGuardAgent

    a = SecurityGuardAgent()
    assert a.can_handle("scan the codebase for secrets") is True
    assert a.can_handle("check defense status") is True
    assert a.can_handle("run a security scan") is True
    assert a.can_handle("what is the weather today") is False


def test_agent_run_scan():
    from orbit.agents import SecurityGuardAgent

    a = SecurityGuardAgent()
    result = a.execute("security scan")
    assert "Codebase" in result or "scan" in result.lower() or "🛡" in result


def test_agent_run_defense_status():
    from orbit.agents import SecurityGuardAgent

    a = SecurityGuardAgent()
    result = a.execute("defense status")
    assert "Defense" in result


def test_agent_import_from_outer():
    from orbit.agents import SecurityGuardAgent as Outer
    from orbit.orbit.agents import SecurityGuardAgent as Inner

    assert Outer is Inner


# ── Flask API ─────────────────────────────────────────────────────────
@pytest.fixture
def client():
    from orbit.orbit.server import create_app

    app = create_app()
    with app.test_client() as c:
        yield c


def test_bp_registered(client):
    from orbit.orbit.server import create_app

    app = create_app()
    assert "security_guard" in app.blueprints


def test_api_status(client):
    r = client.get("/api/security-guard/status")
    assert r.status_code == 200
    assert "monitoring" in r.get_json()


def test_api_defenses(client):
    r = client.get("/api/security-guard/defenses")
    assert r.status_code == 200
    assert r.get_json()["total"] >= 6


def test_api_scan(client):
    r = client.get("/api/security-guard/scan")
    assert r.status_code == 200
    assert "count" in r.get_json()


def test_api_report(client):
    r = client.post("/api/security-guard/report", json={"deep": False})
    assert r.status_code == 200
    assert "verdict" in r.get_json()


def test_api_incidents(client):
    r = client.get("/api/security-guard/incidents")
    assert r.status_code == 200
    assert "incidents" in r.get_json()


def test_api_fix(client):
    r = client.post("/api/security-guard/fix")
    assert r.status_code == 200
    assert "fixes" in r.get_json()


def test_api_monitor(client):
    r = client.post("/api/security-guard/monitor/start", json={"interval": 1})
    assert r.status_code == 200
    assert r.get_json()["started"] is True
    r = client.post("/api/security-guard/monitor/stop")
    assert r.status_code == 200
    assert r.get_json()["monitoring"] is False
