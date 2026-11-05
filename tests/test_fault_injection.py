"""Phase 12 - fault-injection regression (fixed test APIs)."""
import json
from pathlib import Path


def _dir_fault(tmp_path):
    d = tmp_path / "unwritable"
    d.mkdir(exist_ok=True)
    return str(d)


def test_honest_metrics_save_survives_disk_fault(tmp_path):
    from orbit.orbit.core.honest_metrics import HonestMetrics
    hm = HonestMetrics()
    hm._path = lambda: _dir_fault(tmp_path)
    hm._save()


def test_mood_tracker_save_survives_disk_fault(tmp_path):
    from orbit.orbit.core.mood_tracker import MoodTracker
    mt = MoodTracker()
    mt._mood_file = _dir_fault(tmp_path)
    mt._save()


def test_experimentation_framework_save_survives_disk_fault(tmp_path):
    from orbit.orbit.core.experimentation_framework import ExperimentationFramework
    ef = ExperimentationFramework()
    ef._path = lambda: Path(_dir_fault(tmp_path))
    ef._save()


def test_team_restructurer_save_survives_disk_fault(tmp_path):
    from orbit.orbit.core.team_restructurer import TeamRestructurer
    tr = TeamRestructurer()
    tr._path = lambda: Path(_dir_fault(tmp_path))
    tr._save()


def test_opportunity_scout_save_survives_disk_fault(tmp_path):
    from orbit.orbit.core.opportunity_scout import OpportunityScan
    os_ = OpportunityScan()
    os_._data_path = lambda: Path(_dir_fault(tmp_path))
    os_._save()


def test_agent_awareness_save_survives_disk_fault(tmp_path):
    from orbit.orbit.core.agent_awareness import AgentAwarenessManager
    am = AgentAwarenessManager()
    am._data_path = lambda: Path(_dir_fault(tmp_path))
    am._save()


def test_agent_learning_save_survives_disk_fault(tmp_path):
    from orbit.orbit.core.agent_learning import SolutionPatternIndexer
    spi = SolutionPatternIndexer()
    spi._data_path = lambda: Path(_dir_fault(tmp_path))
    spi._save()


def test_context_engine_save_survives_disk_fault(tmp_path):
    from orbit.orbit.core.context_engine import ContextEngine
    ce = ContextEngine()
    fault = Path(_dir_fault(tmp_path))
    ce._briefings_path = lambda: fault
    ce._save("_briefings", "_briefings_path")


def test_get_metrics_survives_disk_fault(tmp_path, monkeypatch):
    import orbit.orbit.core.honest_metrics as hm_mod
    monkeypatch.setattr(hm_mod, "DATA_DIR", tmp_path)
    hm = hm_mod.HonestMetrics()
    fault = _dir_fault(tmp_path)
    monkeypatch.setattr(hm, "_path", lambda: fault)
    hm._data.pop("last_scan", None)
    result = hm.get_metrics()
    assert isinstance(result, dict)


def test_honest_metrics_load_recovers_from_corrupt_json(tmp_path, monkeypatch):
    import orbit.orbit.core.honest_metrics as hm_mod
    monkeypatch.setattr(hm_mod, "DATA_DIR", tmp_path)
    store = tmp_path / "honest_metrics.json"
    store.write_text("{corrupt", encoding="utf-8")
    hm = hm_mod.HonestMetrics()
    assert isinstance(hm._data, dict)


def test_mood_tracker_load_recovers_from_corrupt_json(tmp_path, monkeypatch):
    import orbit.orbit.core.mood_tracker as mt_mod
    monkeypatch.setattr(mt_mod, "DATA_DIR", tmp_path)
    bad = tmp_path / "mood_entries.json"
    bad.write_text("null", encoding="utf-8")  # valid JSON, wrong type
    mt = mt_mod.MoodTracker()  # __init__ loads; must NOT raise
    assert isinstance(mt._entries, (list, dict))


def test_experimentation_framework_load_recovers_from_corrupt_json(tmp_path):
    from orbit.orbit.core.experimentation_framework import ExperimentationFramework
    ef = ExperimentationFramework()
    bad = tmp_path / "exps.json"
    bad.write_text("[]", encoding="utf-8")  # valid JSON, wrong shape
    ef._path = lambda: bad
    ef._load()  # already guarded; must NOT raise
    assert isinstance(ef._experiments, (list, dict))
# --------------------------------------------------- null-load batch guard
# json.load("null") returns None without raising - before the guard this
# poisoned self.X and the next container op (.append/.get) crashed.


def _write_null_and_load(cls_factory, tmp_path, filename, attr):
    bad = tmp_path / filename
    bad.write_text("null", encoding="utf-8")
    obj = cls_factory()
    return obj, attr


def test_audit_trail_null_load(tmp_path, monkeypatch):
    import orbit.orbit.core.audit_trail as m
    monkeypatch.setattr(m, "DATA_DIR", tmp_path, raising=False)
    bad = tmp_path / "audit.json"
    bad.write_text("null", encoding="utf-8")
    at = m.AuditTrail()
    if hasattr(at, "_path"):
        at._path = lambda: bad
        at._load_entries()
    assert isinstance(at.entries, list)


def test_scheduler_null_load(tmp_path, monkeypatch):
    import orbit.orbit.core.scheduler as m
    # find storage path attr used by _load_tasks
    sch = m.Scheduler() if hasattr(m, "Scheduler") else None
    if sch is None:
        import inspect
        cls = next(v for k, v in vars(m).items() if inspect.isclass(v) and hasattr(v, "_load_tasks"))
        sch = cls()
    bad = tmp_path / "tasks.json"
    bad.write_text("null", encoding="utf-8")
    # redirect whatever path method/attr _load_tasks uses
    for attr in ("_path", "_tasks_path", "_file", "_store_path"):
        if hasattr(sch, attr):
            val = getattr(sch, attr)
            if callable(val):
                setattr(sch, attr, lambda b=bad: b)
            else:
                setattr(sch, attr, bad)
            break
    sch._load_tasks()
    assert isinstance(sch.tasks, dict)


def test_prefetch_null_load(tmp_path):
    from orbit.orbit.core.prefetch import Prefetch
    pf = Prefetch()
    bad = tmp_path / "cache.json"
    bad.write_text("null", encoding="utf-8")
    for attr in ("_path", "_cache_path", "_file"):
        if hasattr(pf, attr):
            val = getattr(pf, attr)
            if callable(val):
                setattr(pf, attr, lambda b=bad: b)
            else:
                setattr(pf, attr, bad)
            break
    if hasattr(pf, "_load"):
        pf._load()
    assert isinstance(pf._cache, dict)


def test_time_machine_null_load(tmp_path):
    from orbit.orbit.core.time_machine import TimeMachine
    tm = TimeMachine()
    bad = tmp_path / "snapshots.json"
    bad.write_text("null", encoding="utf-8")
    for attr in ("_path", "_snapshots_path", "_file"):
        if hasattr(tm, attr):
            val = getattr(tm, attr)
            if callable(val):
                setattr(tm, attr, lambda b=bad: b)
            else:
                setattr(tm, attr, bad)
            break
    if hasattr(tm, "_load"):
        tm._load()
    assert isinstance(tm._snapshots, list)


def test_long_horizon_null_load(tmp_path):
    from orbit.orbit.core.long_horizon import LongHorizonManager
    lh = LongHorizonManager()
    bad = tmp_path / "goals.json"
    bad.write_text("null", encoding="utf-8")
    for attr in ("_path", "_goals_path", "_file"):
        if hasattr(lh, attr):
            val = getattr(lh, attr)
            if callable(val):
                setattr(lh, attr, lambda b=bad: b)
            else:
                setattr(lh, attr, bad)
            break
    if hasattr(lh, "_load"):
        lh._load()
    assert isinstance(lh._goals, list)


def test_mood_tracker_append_works_after_null_load(tmp_path, monkeypatch):
    """The crash path: null load -> next log_mood().append must not raise."""
    import orbit.orbit.core.mood_tracker as mt_mod
    monkeypatch.setattr(mt_mod, "DATA_DIR", tmp_path)
    bad = tmp_path / "mood_entries.json"
    bad.write_text("null", encoding="utf-8")
    mt = mt_mod.MoodTracker()
    assert isinstance(mt._entries, list)
    entry = mt.log_mood(score=7, category="happy", note="after null load")
    assert entry and len(mt._entries) == 1