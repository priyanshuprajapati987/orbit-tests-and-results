"""Regression tests: time-travel, companion memory, digital twin, continuity."""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def test_time_machine_record_restore():
    import pathlib
    import tempfile

    import orbit.orbit.core.time_machine as tm

    p = str(pathlib.Path(tempfile.mkdtemp()) / "tm.json")
    m = tm.TimeMachine(store_path=p)
    m.record("hi", "hello")
    m.record("bye", "cya")
    assert len(m.log(10)) == 2
    snap = m.restore(0)
    assert snap["user"] == "hi"
    m.reset()
    assert m.log(5) == []


def test_companion_memory_add_timeline():
    import pathlib
    import tempfile

    import orbit.orbit.core.companion_memory as cm

    p = str(pathlib.Path(tempfile.mkdtemp()) / "cm.json")
    mem = cm.CompanionMemory(store_path=p)
    mem.add_event("shipped v3", "milestone")
    assert len(mem.timeline(5)) == 1
    assert "shipped" in mem.summarize()


def test_digital_twin_builds():
    from orbit.orbit.core.digital_twin import build_twin

    t = build_twin()
    assert "preferences" in t and "relationships" in t


def test_continuity_export_import_roundtrip():
    from orbit.orbit.core.continuity import export_package, import_package

    pkg = export_package("secret-pass")
    assert pkg
    res = import_package(pkg, "secret-pass")
    assert res["ok"] is True
    bad = import_package(pkg, "wrong")
    assert bad["ok"] is False
