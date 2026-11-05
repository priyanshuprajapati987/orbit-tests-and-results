"""Regression — nested non-reentrant lock self-deadlocks.

Phase 10 of the improvement loop. Same class as the honest_metrics bug
(found in Phase 8b): a method holds a non-reentrant threading.Lock, then
calls another method of the same class that acquires the SAME lock ->
the thread waits forever on its own lock.

Precise AST nesting scan (call inside a `with self._lock` block, callee
also a lock-holder) found exactly 3 true sites in 2 classes (98 raw
suspects collapsed after verifying sequential acquire-release is safe):

1. resource_tracker.ResourceTracker.record_usage() -> _save_data()
2. security_scanner.SecurityScanner.check_login_attempt() -> _record_threat()
   (two call sites: brute_force HIGH + suspicious_login MEDIUM)

Fix for both: threading.Lock() -> threading.RLock() (reentrant).

These tests run the outer method (which triggers the nested acquire) in a
worker thread with a bounded join; a regression to a plain Lock hangs the
thread and fails the assertion.
"""
import threading

from orbit.orbit.core.resource_tracker import ResourceTracker
from orbit.orbit.core.security_scanner import SecurityScanner


def _run_with_deadlock_guard(fn, timeout=5.0):
    """Run fn in a worker thread; return (box, hung)."""
    box = {}

    def _run():
        try:
            box["result"] = fn()
            box["ok"] = True
        except Exception as e:  # pragma: no cover
            box["error"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    return box, t.is_alive()


class TestResourceTrackerDeadlock:
    def test_record_usage_does_not_deadlock(self, tmp_path):
        rt = ResourceTracker(storage_file=str(tmp_path / "usage.json"))
        # record_usage holds the lock then calls _save_data() (nested acquire)
        box, hung = _run_with_deadlock_guard(
            lambda: rt.record_usage("ollama", "token", 10, 0.0, {"model": "qwen"}),
            timeout=5.0,
        )
        assert not hung, "record_usage() deadlocked (nested Lock acquire in _save_data)"
        assert box.get("ok"), f"record_usage raised: {box.get('error')}"

    def test_lock_is_reentrant(self):
        import threading as _t

        rt = ResourceTracker.__new__(ResourceTracker)
        rt._lock = _t.RLock()
        with rt._lock:
            with rt._lock:  # raises RuntimeError on a plain Lock
                pass


class TestSecurityScannerDeadlock:
    def test_check_login_attempt_threat_path_does_not_deadlock(self, tmp_path):
        ss = SecurityScanner(storage_file=str(tmp_path / "threats.json"))
        # 3+ failed attempts trigger _record_threat() while the lock is held
        def _flood():
            for _ in range(6):
                ss.check_login_attempt("10.0.0.1", "admin", success=False)
            return True

        box, hung = _run_with_deadlock_guard(_flood, timeout=5.0)
        assert not hung, "check_login_attempt() deadlocked (nested Lock acquire in _record_threat)"
        assert box.get("ok"), f"check_login_attempt raised: {box.get('error')}"

    def test_brute_force_still_blocks(self, tmp_path):
        ss = SecurityScanner(storage_file=str(tmp_path / "threats.json"))
        result = None
        for _ in range(ss.max_login_attempts + 1):
            result = ss.check_login_attempt("10.0.0.2", "admin", success=False)
        assert result is not None
        assert result.get("blocked") is True

    def test_lock_is_reentrant(self):
        import threading as _t

        ss = SecurityScanner.__new__(SecurityScanner)
        ss._lock = _t.RLock()
        with ss._lock:
            with ss._lock:  # raises RuntimeError on a plain Lock
                pass
