# ORBIT — Phase 2 redacted diagnostics tests
#
# Run:  python -m pytest tests/test_diagnostics.py -v
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def diag_mod():
    return pytest.importorskip("orbit.orbit.core.diagnostics")


def test_record_event_happy_path(diag_mod):
    d = diag_mod.Diagnostics()
    ev = d.record("llm_call", model="llama3.2", agent="QUEEN", elapsed_ms=12.3, ok=True, detail="fine")
    assert ev["category"] == "llm_call"
    assert ev["ok"] is True
    assert ev["model"] == "llama3.2"
    assert d.recent(1)[-1]["category"] == "llm_call"


def test_secrets_are_redacted_in_detail(diag_mod):
    d = diag_mod.Diagnostics()
    ev = d.record(
        "error",
        ok=False,
        detail="provider failed with key sk-or-v1-abcdefghijklmnop and apx_live_BNcgH6XAuwfmWAgeoz9vnCfhZCaXZXd5v8v4FlUh",
    )
    blob = str(ev)
    assert "sk-or-v1-abcdefghijklmnop" not in blob
    assert "apx_live_BNcgH6XAuwfmWAgeoz9" not in blob


def test_secrets_are_redacted_in_extra_dict(diag_mod):
    d = diag_mod.Diagnostics()
    ev = d.record("http", extra={"headers": {"Authorization": "Bearer sk-abcdef1234567890secret"}})
    assert "sk-abcdef1234567890secret" not in str(ev.get("extra", {}))


def test_memory_ring_is_bounded(diag_mod):
    d = diag_mod.Diagnostics()
    for i in range(600):
        d.record("t", detail=str(i))
    assert len(d.recent(1000)) <= 500


def test_singleton_accessor(diag_mod):
    a = diag_mod.get_diagnostics()
    b = diag_mod.get_diagnostics()
    assert a is b
