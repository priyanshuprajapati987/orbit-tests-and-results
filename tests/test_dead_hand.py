"""Dead Hand — anti-tamper engine tests (P0 hardened, non-destructive).

Hermetic: every engine is built with store_dir/code_root under tmp_path and
exit_on_trigger disabled. Trigger is NON-DESTRUCTIVE: no code file is ever
deleted by these tests, and the engine itself never deletes on trigger.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orbit.orbit.core import dead_hand as dh_mod
from orbit.orbit.core.dead_hand import DeadHand, get_dead_hand, reset_dead_hand_for_tests
from orbit.orbit.core import dead_hand_policy as policy
from orbit.orbit.core import dead_hand_destroy as destroy


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_deadhand_env(monkeypatch):
    monkeypatch.delenv("ORBIT_DEADHAND", raising=False)
    monkeypatch.delenv("ORBIT_DEADHAND_RESPONSE", raising=False)
    monkeypatch.delenv("ORBIT_ALLOW_DESTROY", raising=False)
    monkeypatch.setattr(dh_mod, "is_frozen", lambda: False, raising=False)


@pytest.fixture
def code_tree(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    (root / "orbit" / "core").mkdir(parents=True)
    (root / "ui" / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "orbit_data" / "security").mkdir(parents=True)
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / ".venv" / "Lib").mkdir(parents=True)
    (root / "orbit" / "core" / "engine.py").write_text("print('v1')\n", encoding="utf-8")
    (root / "orbit" / "core" / "util.py").write_text("X = 1\n", encoding="utf-8")
    (root / "ui" / "src" / "App.jsx").write_text("export default 1\n", encoding="utf-8")
    (root / "main.py").write_text("run()\n", encoding="utf-8")
    (root / "README.md").write_text("# keep me\n", encoding="utf-8")
    (root / ".git" / "hook.py").write_text("git-internal\n", encoding="utf-8")
    (root / "orbit_data" / "security" / "store.py").write_text("runtime\n", encoding="utf-8")
    (root / "node_modules" / "pkg" / "index.js").write_text("vendor\n", encoding="utf-8")
    (root / ".venv" / "Lib" / "site.py").write_text("stdlib\n", encoding="utf-8")
    return root


@pytest.fixture
def dh(tmp_path: Path, code_tree: Path) -> DeadHand:
    engine = DeadHand(
        store_dir=tmp_path / "sec",
        code_root=code_tree,
        armed=True,
        exit_on_trigger=False,
        profile="lockout",
    )
    yield engine
    engine.stop_monitor()


# ── Arming ───────────────────────────────────────────────────────────────

class TestArming:
    def test_default_not_armed(self, tmp_path, code_tree):
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree, armed=None)
        assert engine.armed is False

    def test_env_arms(self, tmp_path, code_tree, monkeypatch):
        monkeypatch.setenv("ORBIT_DEADHAND", "1")
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree, armed=None)
        assert engine.armed is True
        assert engine.env_armed is True

    def test_frozen_arms(self, tmp_path, code_tree, monkeypatch):
        monkeypatch.setattr(dh_mod, "is_frozen", lambda: True, raising=False)
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree, armed=None)
        assert engine.armed is True

    def test_manual_arm_persists_across_restart(self, tmp_path, code_tree):
        store = tmp_path / "s"
        first = DeadHand(store_dir=store, code_root=code_tree, armed=None)
        assert first.armed is False
        first.arm_manual()
        second = DeadHand(store_dir=store, code_root=code_tree, armed=None)
        assert second.armed is True

    def test_disarm_clears_manual(self, tmp_path, code_tree):
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree, armed=None)
        engine.arm_manual()
        result = engine.disarm()
        assert engine.armed is False
        assert result["env_armed"] is False

    def test_disarm_cannot_beat_env(self, tmp_path, code_tree, monkeypatch):
        monkeypatch.setenv("ORBIT_DEADHAND", "1")
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree, armed=None)
        result = engine.disarm()
        assert result["armed"] is True
        assert result["env_armed"] is True

    def test_override_beats_env(self, tmp_path, code_tree, monkeypatch):
        monkeypatch.setenv("ORBIT_DEADHAND", "1")
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree, armed=False)
        assert engine.armed is False


# ── Risk scoring + response ladder (POLICY layer) ────────────────────────

class TestPolicy:
    def test_severity_map(self):
        assert policy.severity("debugger") == 1
        assert policy.severity("re_tool") == 1
        assert policy.severity("integrity") == 3
        assert policy.severity("integrity_new") == 2
        assert policy.severity("state_tamper") == 3
        assert policy.severity("unknown") == 1  # fallback

    def test_risk_from_attempts_in_window(self):
        now = time.time()
        attempts = [
            {"kind": "debugger", "ts": now - 10, "severity": 1},
            {"kind": "integrity", "ts": now - 30, "severity": 3},
            {"kind": "re_tool", "ts": now - 100, "severity": 1},
        ]
        assert policy.risk_from_attempts(attempts, window_sec=600, now=now) == 5

    def test_risk_excludes_expired_window(self):
        now = time.time()
        attempts = [
            {"kind": "debugger", "ts": now - 700, "severity": 1},  # outside 600s
            {"kind": "re_tool", "ts": now - 10, "severity": 1},
        ]
        assert policy.risk_from_attempts(attempts, window_sec=600, now=now) == 1

    def test_risk_skips_no_ts(self):
        assert policy.risk_from_attempts([{"kind": "debugger"}]) == 0

    def test_response_ladder_audit_profile(self):
        assert policy.response_for(0, "audit") == "none"
        assert policy.response_for(1, "audit") == "audit"     # 1 < 3
        assert policy.response_for(3, "audit") == "audit"     # ceiling caps at audit
        assert policy.response_for(6, "audit") == "audit"     # never lockout under audit

    def test_response_ladder_restricted_profile(self):
        assert policy.response_for(3, "restricted") == "restricted"
        assert policy.response_for(6, "restricted") == "restricted"  # ceiling caps lockout

    def test_response_ladder_lockout_profile(self):
        assert policy.response_for(3, "lockout") == "restricted"
        assert policy.response_for(6, "lockout") == "lockout"

    def test_response_ladder_shutdown_profile(self):
        assert policy.response_for(6, "shutdown") == "shutdown"
        assert policy.response_for(3, "shutdown") == "restricted"

    def test_load_profile_from_env(self, monkeypatch):
        monkeypatch.setenv("ORBIT_DEADHAND_RESPONSE", "restricted")
        assert policy.load_profile() == "restricted"
        monkeypatch.setenv("ORBIT_DEADHAND_RESPONSE", "bogus")
        assert policy.load_profile() == "audit"  # invalid falls back
        monkeypatch.delenv("ORBIT_DEADHAND_RESPONSE")
        assert policy.load_profile() == "audit"

    def test_summarize_shape(self):
        s = policy.summarize(5, "lockout")
        assert s["risk"] == 5
        assert s["profile"] == "lockout"
        assert s["response"] == "restricted"
        assert s["restricted_at"] == 3
        assert s["lockout_at"] == 6


# ── Engine risk integration ──────────────────────────────────────────────

class TestEngineRisk:
    def test_low_risk_audit_profile_stays_audit(self, tmp_path, code_tree):
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree,
                          armed=True, exit_on_trigger=False, profile="audit")
        engine.record_attempt("debugger", "probe")
        engine.record_attempt("re_tool", "ida64")
        assert engine.current_risk() == 2
        assert engine.current_response() == "audit"  # ceiling caps
        assert engine.get_status()["triggered"] is False

    def test_integrity_triggers_restricted(self, tmp_path, code_tree):
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree,
                          armed=True, exit_on_trigger=False, profile="restricted")
        engine.record_attempt("integrity", "engine.py modified")
        assert engine.current_risk() == 3
        assert engine.current_response() == "restricted"
        assert engine.get_status()["triggered"] is False  # restricted is not lockout

    def test_high_risk_lockout_profile_triggers_quarantine(self, dh, code_tree):
        # profile=lockout, risk 3+3=6 -> lockout -> quarantine, NO deletion
        dh.record_attempt("integrity", "one")
        dh.record_attempt("state_tamper", "two")
        status = dh.get_status()
        assert status["triggered"] is True
        assert status["risk"] >= 6
        # code files survive
        assert (code_tree / "orbit" / "core" / "engine.py").exists()
        assert (code_tree / "main.py").exists()
        # excluded paths survive
        assert (code_tree / "README.md").exists()
        assert (code_tree / ".git" / "hook.py").exists()

    def test_trigger_never_deletes_files(self, dh, code_tree):
        for kind in ("integrity", "state_tamper", "integrity", "state_tamper"):
            dh.record_attempt(kind, "signal")
        assert dh.get_status()["triggered"] is True
        # every code file still present
        assert (code_tree / "orbit" / "core" / "engine.py").exists()
        assert (code_tree / "orbit" / "core" / "util.py").exists()
        assert (code_tree / "ui" / "src" / "App.jsx").exists()
        assert (code_tree / "main.py").exists()

    def test_disarmed_never_triggers(self, tmp_path, code_tree):
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree,
                          armed=False, exit_on_trigger=False, profile="lockout")
        for _ in range(8):
            engine.record_attempt("integrity", "x")
        assert engine.get_status()["warnings"] == 8
        assert engine.get_status()["triggered"] is False
        assert (code_tree / "main.py").exists()

    def test_trigger_is_idempotent(self, dh, code_tree):
        for _ in range(4):
            dh.record_attempt("integrity", "x")
        first = dh.get_status()
        again = dh.trigger(reason="should-not-double")
        assert again["warnings"] == first["warnings"]
        assert again["triggered"] is True

    def test_attempt_fields_have_ts_and_severity(self, dh):
        dh.record_attempt("debugger", "attached")
        attempt = dh.get_status()["attempts"][-1]
        assert "ts" in attempt
        assert attempt["severity"] == 1
        assert attempt["kind"] == "debugger"

    def test_reset_clears_counter_but_not_flags(self, dh):
        for _ in range(4):
            dh.record_attempt("integrity", "x")
        assert dh.get_status()["triggered"] is True
        status = dh.reset(reason="test")
        assert status["warnings"] == 0
        assert status["triggered"] is False
        assert status["attempts"] == []
        assert dh.has_flagged() is True  # quarantine survives reset

    def test_status_keys(self, dh):
        s = dh.get_status()
        assert "risk" in s
        assert "profile" in s
        assert "response" in s
        assert "wipe_deleted" not in s
        assert "wipe_failed" not in s


# ── Quarantine (flagging with expiry) ────────────────────────────────────

class TestQuarantine:
    def test_trigger_flags_recorded_and_machine_identities(self, dh):
        dh._state["identities"] = ["ip:203.0.113.9", "key:deadbeefdeadbeef"]
        for _ in range(4):
            dh.record_attempt("integrity", "x")
        entries = dh.get_flagged()["entries"]
        assert "ip:203.0.113.9" in entries
        assert "key:deadbeefdeadbeef" in entries
        assert "ip:127.0.0.1" in entries
        assert any(k.startswith("machine:") for k in entries)
        assert entries["ip:203.0.113.9"]["reason"]
        assert entries["ip:203.0.113.9"]["expires_at"]

    def test_quarantine_expiry_sweep(self, dh, tmp_path):
        dh._flag(["ip:1.2.3.4"], reason="old")
        # Manually set expiry to the past
        flag_file = Path(dh._store_dir) / "deadhand_flagged.json"
        data = json.loads(flag_file.read_text(encoding="utf-8"))
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat() + "Z"
        data["entries"]["ip:1.2.3.4"]["expires_at"] = past
        flag_file.write_text(json.dumps(data), encoding="utf-8")
        dh._flag_cache = None  # force reload
        assert dh._active_entries() == {}  # expired
        assert dh.has_flagged() is False
        # sweep drops it from disk
        removed = dh.sweep_expired()
        assert removed == 1
        assert "ip:1.2.3.4" not in dh.get_flagged()["entries"]

    def test_flag_file_survives_trigger(self, dh, tmp_path):
        for _ in range(4):
            dh.record_attempt("integrity", "x")
        flag_file = Path(dh._store_dir) / "deadhand_flagged.json"
        assert flag_file.exists()
        assert json.loads(flag_file.read_text(encoding="utf-8"))["entries"]

    def test_is_flagged_and_has_flagged(self, dh):
        assert dh.has_flagged() is False
        assert dh.is_flagged(["ip:1.2.3.4"]) is False
        dh._flag(["ip:1.2.3.4"], reason="test")
        assert dh.has_flagged() is True
        assert dh.is_flagged(["ip:9.9.9.9", "ip:1.2.3.4"]) is True
        assert dh.is_flagged(["ip:9.9.9.9"]) is False

    def test_unflag_single_and_all(self, dh):
        dh._flag(["ip:1.1.1.1", "ip:2.2.2.2"], reason="t")
        assert dh.unflag(identity="ip:1.1.1.1") == 1
        assert "ip:1.1.1.1" not in dh.get_flagged()["entries"]
        assert dh.unflag(clear_all=True) == 1
        assert dh.has_flagged() is False

    def test_flag_state_shared_across_instances(self, tmp_path, code_tree):
        store = tmp_path / "s"
        a = DeadHand(store_dir=store, code_root=code_tree, armed=True)
        a._flag(["ip:5.5.5.5"], reason="first")
        b = DeadHand(store_dir=store, code_root=code_tree, armed=False)
        assert b.is_flagged(["ip:5.5.5.5"]) is True


# ── Detections (scan_once) ───────────────────────────────────────────────

class TestDetections:
    def test_debugger_signal_records_warning(self, dh, monkeypatch):
        dh.seal()
        monkeypatch.setattr(dh, "_debugger_present", lambda: True)
        assert dh.scan_once() >= 1
        assert dh.get_status()["attempts"][-1]["kind"] == "debugger"

    def test_no_debugger_no_warning(self, dh, monkeypatch):
        dh.seal()
        monkeypatch.setattr(dh, "_debugger_present", lambda: False)
        monkeypatch.setattr(dh, "_scan_re_tools", lambda: [])
        assert dh.scan_once() == 0
        assert dh.get_status()["warnings"] == 0

    def test_re_tool_signal(self, dh, monkeypatch):
        dh.seal()
        monkeypatch.setattr(dh, "_debugger_present", lambda: False)
        monkeypatch.setattr(dh, "_scan_re_tools", lambda: ["ida64.exe"])
        dh.scan_once()
        assert dh.get_status()["attempts"][-1]["kind"] == "re_tool"
        assert "ida64.exe" in dh.get_status()["attempts"][-1]["detail"]

    def test_integrity_detects_modified_file_once(self, dh, code_tree, monkeypatch):
        dh.seal()
        monkeypatch.setattr(dh, "_debugger_present", lambda: False)
        monkeypatch.setattr(dh, "_scan_re_tools", lambda: [])
        (code_tree / "orbit" / "core" / "engine.py").write_text("print('patched')\n", encoding="utf-8")
        dh.scan_once()
        attempt = dh.get_status()["attempts"][-1]
        assert attempt["kind"] == "integrity"
        assert "engine.py" in attempt["detail"]
        before = dh.get_status()["warnings"]
        dh.scan_once()
        assert dh.get_status()["warnings"] == before

    def test_integrity_new_detects_added_file(self, dh, code_tree, monkeypatch):
        dh.seal()
        monkeypatch.setattr(dh, "_debugger_present", lambda: False)
        monkeypatch.setattr(dh, "_scan_re_tools", lambda: [])
        (code_tree / "orbit" / "core" / "new_module.py").write_text("evil\n", encoding="utf-8")
        dh.scan_once()
        kinds = [a["kind"] for a in dh.get_status()["attempts"]]
        assert "integrity_new" in kinds

    def test_reseal_clears_integrity_reporting(self, dh, code_tree, monkeypatch):
        dh.seal()
        monkeypatch.setattr(dh, "_debugger_present", lambda: False)
        monkeypatch.setattr(dh, "_scan_re_tools", lambda: [])
        (code_tree / "orbit" / "core" / "engine.py").write_text("edited\n", encoding="utf-8")
        dh.scan_once()
        assert dh.get_status()["warnings"] >= 1
        dh.reseal()
        before = dh.get_status()["warnings"]
        dh.scan_once()
        assert dh.get_status()["warnings"] == before

    def test_state_tamper_detects_counter_decrease(self, dh, monkeypatch):
        dh.seal()
        monkeypatch.setattr(dh, "_debugger_present", lambda: False)
        monkeypatch.setattr(dh, "_scan_re_tools", lambda: [])
        dh.record_attempt("test", "real work")
        assert dh.get_status()["warnings"] == 1
        state_file = Path(dh._store_dir) / "dead_hand.json"
        external = json.loads(state_file.read_text(encoding="utf-8"))
        external["warnings"] = 0
        external["attempts"] = []
        state_file.write_text(json.dumps(external), encoding="utf-8")
        dh._last_state_raw = json.dumps(external) + "\x00stale"  # force mismatch detection
        dh.scan_once()
        kinds = [a["kind"] for a in dh.get_status()["attempts"]]
        assert "state_tamper" in kinds
        # high water mark restored
        assert dh.get_status()["warnings"] >= 2


# ── Audit ────────────────────────────────────────────────────────────────

class TestAudit:
    def test_audit_op_writes_jsonl(self, dh, tmp_path):
        dh._audit_op("arm", actor="api", result="armed")
        audit = Path(dh._store_dir) / "deadhand_audit.jsonl"
        assert audit.exists()
        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[-1])
        assert entry["op"] == "arm"
        assert entry["actor"] == "api"

    def test_audit_survives_reset(self, dh, tmp_path):
        dh._audit_op("arm", actor="api")
        dh.reset(reason="test")
        audit = Path(dh._store_dir) / "deadhand_audit.jsonl"
        assert audit.exists()
        assert len(audit.read_text(encoding="utf-8").strip().splitlines()) >= 1


# ── Graceful shutdown ────────────────────────────────────────────────────

class TestShutdown:
    def test_shutdown_writes_recovery_report(self, tmp_path, code_tree):
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree,
                          armed=True, exit_on_trigger=False, profile="shutdown")
        engine.record_attempt("integrity", "one")
        engine.record_attempt("state_tamper", "two")
        report_path = Path(engine._store_dir) / "deadhand_recovery_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert "how_to_recover" in report
        assert len(report["how_to_recover"]) >= 3

    def test_shutdown_no_exit_when_disabled(self, tmp_path, code_tree):
        engine = DeadHand(store_dir=tmp_path / "s", code_root=code_tree,
                          armed=True, exit_on_trigger=False, profile="shutdown")
        engine.record_attempt("integrity", "x")
        engine.record_attempt("state_tamper", "y")
        assert engine._exit_thread is None  # no exit thread spawned


# ── Destroy (manual-only, gated) ─────────────────────────────────────────

class TestDestroy:
    def _patch_frozen(self, monkeypatch, value: bool):
        from orbit.orbit.core import runtime_paths as rp
        monkeypatch.setattr(rp, "is_frozen", lambda: value, raising=False)

    def test_destroy_blocked_in_dev(self, code_tree, monkeypatch):
        self._patch_frozen(monkeypatch, False)
        result = destroy.execute_destroy(
            reason="test", confirm=destroy.CONFIRM_PHRASE, code_root=code_tree,
        )
        assert result["ok"] is False
        assert "frozen" in result["error"]

    def test_destroy_blocked_without_env(self, code_tree, monkeypatch):
        self._patch_frozen(monkeypatch, True)
        monkeypatch.delenv("ORBIT_ALLOW_DESTROY", raising=False)
        result = destroy.execute_destroy(
            reason="test", confirm=destroy.CONFIRM_PHRASE, code_root=code_tree,
        )
        assert result["ok"] is False
        assert "ORBIT_ALLOW_DESTROY" in result["error"]

    def test_destroy_blocked_without_confirm(self, code_tree, monkeypatch):
        self._patch_frozen(monkeypatch, True)
        monkeypatch.setenv("ORBIT_ALLOW_DESTROY", "1")
        result = destroy.execute_destroy(
            reason="test", confirm="wrong phrase", code_root=code_tree,
        )
        assert result["ok"] is False
        assert "confirm" in result["error"]

    def test_destroy_never_imported_by_dead_hand(self):
        import inspect
        src = inspect.getsource(dh_mod)
        # must not actually import destroy module (docs mention it by name)
        assert "import dead_hand_destroy" not in src
        assert "from .dead_hand_destroy" not in src
        assert "execute_destroy" not in src


# ── Seal + monitor ───────────────────────────────────────────────────────

class TestSealMonitor:
    def test_seal_counts_code_files(self, dh):
        count = dh.seal()
        assert count == 4  # engine.py, util.py, App.jsx, main.py

    def test_start_stop_monitor(self, dh):
        assert dh.start_monitor(interval=0.05) is True
        assert dh._monitor_thread is not None
        assert dh._monitor_thread.is_alive()
        dh.stop_monitor()
        assert dh._monitor_thread is None

    def test_monitor_seals_on_start(self, dh):
        dh.start_monitor(interval=0.05)
        assert dh._baseline is not None
        assert len(dh._baseline) == 4
        dh.stop_monitor()

    def test_singleton_lifecycle(self, tmp_path, code_tree):
        reset_dead_hand_for_tests(None)
        engine = get_dead_hand()
        assert isinstance(engine, DeadHand)
        reset_dead_hand_for_tests(None)  # clean up


# ── State persistence + .bak ─────────────────────────────────────────────

class TestPersistence:
    def test_state_writes_bak(self, dh, tmp_path):
        dh.record_attempt("debugger", "first")   # first write: no .bak yet
        dh.record_attempt("debugger", "second")  # second write: previous preserved
        state = Path(dh._store_dir) / "dead_hand.json"
        bak = Path(str(state) + ".bak")
        assert state.exists()
        assert bak.exists()

    def test_state_recovers_from_bak(self, tmp_path, code_tree):
        store = tmp_path / "s"
        first = DeadHand(store_dir=store, code_root=code_tree, armed=True)
        first.arm_manual()
        first.record_attempt("debugger", "x")   # .bak now has warnings=1
        first.record_attempt("debugger", "y")   # primary has warnings=2; .bak has 1
        state = Path(store) / "dead_hand.json"
        state.write_text("{{{corrupt", encoding="utf-8")
        second = DeadHand(store_dir=store, code_root=code_tree, armed=None)
        assert second.armed is True      # recovered from .bak
        assert second.get_status()["warnings"] == 1

    def test_atomic_write_no_partial(self, dh, tmp_path):
        # no leftover tmp files after write
        dh.record_attempt("debugger", "x")
        files = list(Path(dh._store_dir).glob(".tmp_*"))
        assert files == []
