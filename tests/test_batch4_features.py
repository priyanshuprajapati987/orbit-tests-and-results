"""Regression tests: thoughtatorium, macro, prefetch, mesh, wellness, capabilities."""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def test_thoughtatorium_no_material():
    from orbit.orbit.core.thoughtatorium import spark

    # no companion memory / fragments -> graceful error, no LLM
    res = spark()
    assert res.get("ok") is False


def test_macro_record_list_replay():
    import pathlib
    import tempfile

    import orbit.orbit.core.macro_learner as ml

    p = str(pathlib.Path(tempfile.mkdtemp()) / "macros.json")
    m = ml.MacroLearner(store_path=p)
    m.record(
        "build", [{"action": "open", "target": "x"}, {"action": "run", "target": "y"}]
    )
    assert "build" in m.list_macros()
    plan = m.replay_plan("build")
    assert plan["risky_steps"] >= 1


def test_prefetch_get_missing():
    import pathlib
    import tempfile

    import orbit.orbit.core.prefetch as pf

    p = str(pathlib.Path(tempfile.mkdtemp()) / "prefetch.json")
    pre = pf.Prefetch(store_path=p)
    assert pre.get("nonexistent topic") is None


def test_mesh_roundtrip():
    from orbit.orbit.core.mesh import export_capsule, import_capsule

    cap = export_capsule("tool_x", "def run(): pass", "pw")
    assert cap
    res = import_capsule(cap, "pw")
    assert res["ok"] and res["name"] == "tool_x"
    assert import_capsule(cap, "wrong")["ok"] is False


def test_wellness_status():
    from orbit.orbit.core.wellness import status

    s = status()
    assert "suggestion" in s and "session_minutes" in s


def test_capabilities_registry():
    from orbit.orbit.core.capabilities import list_capabilities

    caps = list_capabilities()
    assert len(caps) >= 27
