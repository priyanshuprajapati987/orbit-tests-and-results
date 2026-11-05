"""Regression tests: Local oracle — NL answers over local files, zero cloud."""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _oracle_with_files(tmp_path):
    from orbit.orbit.core.local_oracle import LocalOracle

    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "ideas.md").write_text(
        "The launch code is ORBIT-42.\nProject Nebula ships in Q3.\n", encoding="utf-8"
    )
    (notes / "tasks.md").write_text(
        "We must finish the billing module before launch.\n", encoding="utf-8"
    )
    o = LocalOracle()
    o.index(str(tmp_path))
    return o


def _stub_router(monkeypatch, answer):
    import orbit.orbit.core.llm.router as rmod

    class _Resp:
        def __init__(self):
            self.content = answer
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


def test_ask_grounds_in_local_files(tmp_path, monkeypatch):
    o = _oracle_with_files(tmp_path)
    _stub_router(monkeypatch, "The launch code is ORBIT-42.")
    res = o.ask("what is the launch code?")
    assert res["grounded"] is True
    assert "ORBIT-42" in res["answer"]
    assert len(res["sources"]) >= 1


def test_empty_query_errors(tmp_path, monkeypatch):
    o = _oracle_with_files(tmp_path)
    res = o.ask("")
    assert "error" in res


def test_no_hits_returns_ungrounded(tmp_path, monkeypatch):
    from orbit.orbit.core.local_oracle import LocalOracle

    empty = tmp_path / "empty"
    empty.mkdir()
    o = LocalOracle()
    o.index(str(empty))
    res = o.ask("anything at all")
    assert res["grounded"] is False
    assert res["sources"] == []


def test_status_reports_index(tmp_path, monkeypatch):
    o = _oracle_with_files(tmp_path)
    st = o.status()
    assert st["chunks"] >= 1
