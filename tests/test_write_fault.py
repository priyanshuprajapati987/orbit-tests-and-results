"""Phase 17 - write-adequacy fault injection (silent persistence handlers).

Static scan (precise, receiver-dataflow based - write = atomic/write_text
helpers, json.dump to a file var, or f.write on open()-bound names):
  CRASH axis: 115 unguarded write sites (deferred to Phase 18 - many are
    cross-function contained, triage needed)
  SILENT axis: 18 genuine sites in 17 files where persistence failure was
    swallowed with a bare `except: pass` -> data silently lost while the
    caller kept returning success (the write-side twin of Phase 16's
    rc-ignored fabricated success)

Fix: every silent handler now logs at ERROR (`logger.error("<site> failed:
%s", e)`); 3 modules gained a module logger (background_trainer,
chat_archive_bp, device_manager).

Triaged FALSE POSITIVES (kept as pins below - they already had a signal):
  - code_generator.write_files / code_integrator.integrate: OSError appended
    to errors/actions returned to the caller
  - security_guard.auto_fix: failure appended fixes entry {"applied": False}
  - policy_engine._prune_audit_logs: v2-scan replace() FP

Every test forces OSError at the primitive layer (builtins/io/Path.open) and
asserts an ERROR record appears - pre-fix these were silent (stash-verifiable).
"""
import builtins
import io
import logging
import pathlib
from datetime import datetime


def _explode_writes(monkeypatch):
    """Fail WRITE-mode opens (disk-full), let READ-mode opens pass through."""
    real_builtins_open = builtins.open
    real_io_open = io.open
    real_path_open = pathlib.Path.open

    def _make_boom(real):
        def boom(*args, **kwargs):
            mode = kwargs.get("mode")
            if mode is None and len(args) >= 2 and isinstance(args[1], str):
                mode = args[1]
            mode = mode or "r"
            if any(c in mode for c in "wax+"):
                raise OSError("disk full (phase17)")
            return real(*args, **kwargs)

        return boom

    monkeypatch.setattr(builtins, "open", _make_boom(real_builtins_open))
    monkeypatch.setattr(io, "open", _make_boom(real_io_open))
    monkeypatch.setattr(pathlib.Path, "open", _make_boom(real_path_open))


def _assert_logged(caplog, snippet):
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(snippet in m for m in messages), (
        f"persistence failure was SILENT - no ERROR log containing {snippet!r}; got: {messages}"
    )


class TestSilentSaveHandlers:
    def test_transcript_logger_reports_append_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.autonomous_chat import TranscriptLogger

        logger = TranscriptLogger(tmp_path)
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            logger.log(tmp_path / "t.jsonl", {"a": 1})
        _assert_logged(caplog, "transcript log append failed")

    def test_background_trainer_reports_save_failure(self, monkeypatch, caplog):
        from orbit.orbit.core.background_trainer import BackgroundTrainer

        trainer = BackgroundTrainer()
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            trainer._save()
        _assert_logged(caplog, "background trainer save failed")

    def test_chat_archive_stats_report_persist_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core import chat_archive_bp

        monkeypatch.setattr(chat_archive_bp, "_stats_file", lambda: tmp_path / "stats.json")
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            stats = chat_archive_bp._bump_stats(exports=1)
        assert isinstance(stats, dict) and stats.get("exports", 0) >= 1
        _assert_logged(caplog, "chat archive stats persist failed")

    def test_context_window_reports_save_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        mgr = ContextWindowManager(storage_file=tmp_path / "ctx.json")
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            mgr._save()
        _assert_logged(caplog, "context window save failed")

    def test_device_manager_reports_save_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.device_manager import DeviceManager

        dm = DeviceManager(storage_file=str(tmp_path / "devices.json"))
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            dm._save()
        _assert_logged(caplog, "device manager save failed")

    def test_diagnostics_trim_reports_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.diagnostics import _MAX_FILE_LINES, Diagnostics

        # trim only runs when size >= 2MB AND lines > _MAX_FILE_LINES (5000)
        p = tmp_path / "log.txt"
        p.write_text(("x" * 440 + "\n") * (_MAX_FILE_LINES + 100), encoding="utf-8")
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            Diagnostics._maybe_trim(p)
        _assert_logged(caplog, "diagnostics log trim failed")

    def test_doc_pipeline_reports_save_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.doc_pipeline import DocumentPipeline

        dp = DocumentPipeline(storage_file=tmp_path / "docs.json")
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            dp._save()
        _assert_logged(caplog, "doc pipeline save failed")

    def test_gesture_log_reports_append_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.hand_gesture import HandGestureRecognizer

        g = HandGestureRecognizer.__new__(HandGestureRecognizer)
        g._log_file = tmp_path / "gesture_log.jsonl"
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            g._append_log("wave", 0.9, datetime.now())
        _assert_logged(caplog, "gesture log append failed")

    def test_gesture_action_event_reports_append_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.hand_gesture import HandGestureRecognizer

        g = HandGestureRecognizer.__new__(HandGestureRecognizer)
        g._log_file = tmp_path / "gesture_log.jsonl"
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            g._append_action_event("tts", "spoken")
        _assert_logged(caplog, "gesture action event log append failed")

    def test_mood_detector_reports_save_failure(self, monkeypatch, caplog):
        from orbit.orbit.core.mood_detector import MoodDetector

        md = MoodDetector()
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            md._save_state()
        _assert_logged(caplog, "mood state save failed")

    def test_plugin_bridge_reports_save_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.plugin_bridge import PluginBridge

        pb = PluginBridge(storage_file=tmp_path / "bridge.json", poll_interval=5)
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            pb._save()
        _assert_logged(caplog, "plugin bridge save failed")

    def test_policy_engine_reports_approvals_persist_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.policy_engine import PolicyEngine

        pe = PolicyEngine(workspace=str(tmp_path), audit_dir=str(tmp_path / "audit"))
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            pe._save_approvals()
        _assert_logged(caplog, "ToolGate approvals persist failed")

    def test_proactive_context_reports_save_failure(self, monkeypatch, caplog):
        from orbit.orbit.core.proactive_context import ProactiveContext

        pc = ProactiveContext()
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            pc._save()
        _assert_logged(caplog, "proactive context save failed")

    def test_smart_file_watcher_reports_save_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.smart_file_watcher import SmartFileWatcher

        w = SmartFileWatcher(storage_file=tmp_path / "watch.json", poll_interval=5)
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            w._save()
        _assert_logged(caplog, "file watcher save failed")

    def test_performance_tracker_reports_save_failure(self, monkeypatch, caplog):
        from orbit.orbit.core.smart_intelligence import AgentPerformanceTracker

        t = AgentPerformanceTracker()
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            t._save()
        _assert_logged(caplog, "performance tracker save failed")

    def test_smart_memory_reports_save_failure(self, monkeypatch, caplog):
        from orbit.orbit.core.smart_memory import SmartMemory

        sm = SmartMemory()
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            sm._save()
        _assert_logged(caplog, "smart memory save failed")

    def test_smart_scheduler_reports_save_failure(self, tmp_path, monkeypatch, caplog):
        from orbit.orbit.core.smart_scheduler import SmartScheduler

        ss = SmartScheduler(storage_file=str(tmp_path / "sched.json"))
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            ss._save()
        _assert_logged(caplog, "smart scheduler save failed")

    def test_task_continuity_reports_save_failure(self, monkeypatch, caplog):
        from orbit.orbit.core.task_continuity import TaskContinuity

        tc = TaskContinuity()
        _explode_writes(monkeypatch)
        with caplog.at_level(logging.ERROR):
            tc._save()
        _assert_logged(caplog, "task continuity save failed")


class TestTriagedFalsePositives:
    """These already reported failures - pins proving they stay that way."""

    def test_code_generator_collects_write_errors(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from orbit.orbit.core.code_generator import CodeGenerator

        cg = CodeGenerator()
        cg.results["proj"] = SimpleNamespace(
            files=[SimpleNamespace(path="a.py", content="x = 1")]
        )
        _explode_writes(monkeypatch)
        out = cg.write_files("proj", str(tmp_path))
        assert out["written"] == 0 and out["errors"], "write failure must surface in errors"

    def test_security_guard_autofix_reports_gitignore_failure(self, tmp_path, monkeypatch):
        from orbit.orbit.core.security_guard import SecurityGuard

        (tmp_path / ".gitignore").write_text("# tracked files\n", encoding="utf-8")
        sg = SecurityGuard(root=str(tmp_path))
        _explode_writes(monkeypatch)
        out = sg.auto_fix()
        gitignore_fixes = [f for f in out["fixes"] if f.get("item") == "gitignore"]
        assert gitignore_fixes and gitignore_fixes[0]["applied"] is False
