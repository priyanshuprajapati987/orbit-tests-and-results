"""Tests for the computer-use completion-rate eval (keyless, hermetic)."""

import json
import os


def test_task_list_shape():
    from orbit.orbit.core.computer_use_eval import TASKS

    assert len(TASKS) >= 10
    for t in TASKS:
        assert "id" in t and "category" in t and "instruction" in t
        assert callable(t["instruction"])
        assert "verify" in t or "verify_route" in t or "verify_chat" in t


def test_full_run_high_completion():
    from orbit.orbit.core.computer_use_eval import run_eval, summarize

    results = run_eval()
    assert len(results) == 12
    s = summarize(results)
    assert s["total"] == 12
    assert s["completion_rate"] >= 0.9, f"too low: {s}"
    assert s["by_category"]["routing"]["rate"] == 1.0


def test_summarize_math():
    from orbit.orbit.core.computer_use_eval import summarize

    s = summarize(
        {
            "a": {"ok": True, "category": "files", "latency_ms": 1},
            "b": {"ok": False, "category": "files", "latency_ms": 1},
            "c": {"ok": True, "category": "routing", "latency_ms": 1},
        }
    )
    assert s["total"] == 3
    assert s["passed"] == 2
    assert s["by_category"]["files"]["rate"] == 0.5
    assert s["failed"] == ["b"]


def test_save_eval_roundtrip(tmp_path):
    from orbit.orbit.core.computer_use_eval import run_eval, save_eval

    results = run_eval()
    path = str(tmp_path / "eval.json")
    saved = save_eval(results, path)
    assert saved == path
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert "summary" in data and "results" in data
    assert data["summary"]["total"] == 12


def test_sandbox_cleaned_up():
    from orbit.orbit.core.computer_use_eval import SANDBOX, run_eval

    run_eval()
    assert not SANDBOX.exists()
    assert not os.path.exists(str(SANDBOX))
