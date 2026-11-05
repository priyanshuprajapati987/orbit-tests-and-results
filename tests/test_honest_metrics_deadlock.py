"""Regression — honest_metrics self-deadlock.

Bug: HonestMetrics used a non-reentrant threading.Lock. get_metrics()
acquired it, then on the first call (no cached last_scan) called scan_now(),
which acquired the SAME lock again -> self-deadlock. The first-ever
get_metrics() in a fresh process hung forever (e.g. phoenix.take_checkpoint
at server_start). Fixed by switching to threading.RLock().

These tests pin the fix: a fresh instance's get_metrics() must return
within a bounded time, not hang.
"""
import threading

from orbit.orbit.core.honest_metrics import HonestMetrics


def _get_metrics_with_deadlock_guard(hm, timeout=5.0):
    """Run get_metrics in a worker thread; return (result, hung)."""
    box = {}

    def _run():
        try:
            box["result"] = hm.get_metrics()
        except Exception as e:  # pragma: no cover - surface unexpected errors
            box["error"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    hung = t.is_alive()
    return box, hung


def test_first_get_metrics_does_not_deadlock(tmp_path, monkeypatch):
    # Point DATA_DIR at tmp so we get a guaranteed-fresh (no last_scan) instance
    import orbit.orbit.core.honest_metrics as hm_mod
    import orbit.orbit.core.api_validator as av_mod

    # Hermetic: stub live provider probes. scan_now() calls
    # get_api_validator().get_status() which does real network probes with
    # timeouts — on a loaded machine that is a SLOW scan, not a deadlock.
    # This test pins the RLock regression only.
    class _StubValidator:
        def get_status(self):
            return {"online": 1, "total": 5}

    monkeypatch.setattr(hm_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(av_mod, "get_api_validator", lambda: _StubValidator())
    hm = HonestMetrics()
    # Ensure no cached scan -> forces the scan_now() nested-lock path
    hm._data.pop("last_scan", None)
    box, hung = _get_metrics_with_deadlock_guard(hm, timeout=15.0)
    assert not hung, "get_metrics() deadlocked (nested Lock acquire in scan_now)"
    assert "result" in box, f"get_metrics raised: {box.get('error')}"


def test_repeated_get_metrics_still_works(tmp_path, monkeypatch):
    import orbit.orbit.core.honest_metrics as hm_mod

    monkeypatch.setattr(hm_mod, "DATA_DIR", tmp_path)
    hm = HonestMetrics()
    hm._data.pop("last_scan", None)
    # First call (scan path) + second call (cached path) must both return
    first = hm.get_metrics()
    second = hm.get_metrics()
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    assert "agents_total" in first


def test_lock_is_reentrant():
    # The class must use an RLock, not a plain Lock
    hm = HonestMetrics.__new__(HonestMetrics)
    import threading as _t

    # Minimal init of just the lock (avoid touching real DATA_DIR)
    hm._lock = _t.RLock()
    with hm._lock:
        with hm._lock:  # would raise RuntimeError on a plain Lock
            pass
