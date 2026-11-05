"""Regression tests: Cross-reboot long-horizon goals (persistent execution)."""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _manager(tmp_path):
    from orbit.orbit.core.long_horizon import LongHorizonManager

    return LongHorizonManager(
        store_path=str(tmp_path / "lh.json"),
        notes_dir=str(tmp_path / "notes"),
        interval_sec=1,  # small for tests
    )


def _stub_router(monkeypatch, content):
    import orbit.orbit.core.llm.router as rmod

    class _Resp:
        def __init__(self):
            self.content = content
            self.provider = "ollama"
            self.model = "local"
            self.latency_ms = 1
            self.success = True
            self.error = None
            self.used_cache = False
            self.confidence = None
            self.refined = False
            self.critique = None
            self.counter_arguments = None

    class _Stub:
        def generate(self, req):
            return _Resp()

    monkeypatch.setattr(rmod, "get_router", lambda: _Stub())


def test_start_decomposes_and_advance_completes_step(tmp_path, monkeypatch):
    _stub_router(monkeypatch, '["Research it", "Plan it", "Build it"]')
    m = _manager(tmp_path)
    entry = m.start_goal("Ship a side project")
    assert len(entry["steps"]) == 3
    # Advance one step.
    g = m.advance()
    assert g is not None
    assert sum(1 for s in g["steps"] if s["status"] == "done") == 1
    # Corresponding deliverable note written.
    done = next(s for s in g["steps"] if s["status"] == "done")
    assert os.path.exists(done["deliverable"])


def test_status_reflects_progress(tmp_path, monkeypatch):
    _stub_router(monkeypatch, '["A", "B"]')
    m = _manager(tmp_path)
    m.start_goal("learn guitar")
    m.advance()
    st = m.status()
    assert st["active"] == 1
    assert st["goals"][0]["steps_done"] == 1


def test_empty_goal_rejected(tmp_path, monkeypatch):
    _stub_router(monkeypatch, "[]")
    m = _manager(tmp_path)
    try:
        m.start_goal("   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_daemon_start_stop(tmp_path, monkeypatch):
    _stub_router(monkeypatch, '["A"]')
    m = _manager(tmp_path)
    assert m.start_daemon() is True
    m.stop_daemon()
