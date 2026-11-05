"""Phase 15 - concurrency race injection (static + deterministic pins + hammers).

Static triage: 182 "mutate-without-lock in locked class" suspects -> 21 public
-> 2 GENUINE (rest FPs: Event ops are thread-safe, single dict setitems are
atomic under the GIL, init-time loaders run before threads, *_locked naming
convention = callers hold the lock, multi_tier admin ops have no crash path):

1. scheduler.ORBITcheduler - had a _lock but schedule/enable/disable/delete/
   execute/_save_tasks/register_handler/get_statistics all ran LOCKLESS:
   - runner thread + chat thread = concurrent json.dump over live dict
     ("dictionary changed size") + concurrent open("w") corruption (Phase-12
     class) + live-values() generator iteration in get_statistics
2. plugin_system.PluginSystem - discover_plugins + reset_error inserted into
   _plugins LOCKLESS while monitor/API threads iterate (list comprehensions
   over live dict = RuntimeError); readers now snapshot via _snapshot().

Deterministic pins use the "hold lock, worker must block" pattern: pre-fix
the lockless code completes instantly (pin FAILS), post-fix it blocks on the
lock (pin PASSES). Handler-outside-lock is the inverse pin: main must be able
to ACQUIRE the lock while a handler is mid-flight (guards the fix itself).

Hammer tests then run real thread storms to verify no exceptions and valid
JSON on disk end-to-end.
"""
import json
import threading

import pytest


def _hold_lock_worker_blocks(lock, worker_fn, settle=0.4):
    """Run worker_fn in a thread while `lock` is held here.

    Returns (blocked_while_held, post_release_ok). blocked_while_held is
    True iff the worker was STILL RUNNING after `settle` seconds (i.e. it
    tried to acquire the held lock instead of racing straight through).
    """
    lock.acquire()
    done = threading.Event()
    errors = []

    def _run():
        try:
            worker_fn()
        except Exception as e:  # noqa: BLE001 - collect for assertion
            errors.append(e)
        finally:
            done.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    blocked = not done.wait(settle)
    lock.release()
    finished = done.wait(2.0)
    return blocked, finished, errors


# ------------------------------------------------------- scheduler (genuine 1)
@pytest.fixture
def sched(tmp_path):
    from orbit.orbit.core.scheduler import ORBITcheduler

    return ORBITcheduler(storage_file=str(tmp_path / "tasks.json"))


def test_scheduler_delete_task_takes_lock(sched):
    tid = sched.schedule_task("t", "noop", "interval", {"interval_seconds": 9999})
    blocked, finished, errors = _hold_lock_worker_blocks(
        sched._lock, lambda: sched.delete_task(tid)
    )
    assert blocked, "delete_task ran WITHOUT acquiring the lock (Phase-15 regression)"
    assert finished and not errors


def test_scheduler_schedule_task_takes_lock(sched):
    blocked, finished, errors = _hold_lock_worker_blocks(
        sched._lock, lambda: sched.schedule_task("t", "noop", "interval", {"interval_seconds": 9999})
    )
    assert blocked, "schedule_task ran WITHOUT acquiring the lock"
    assert finished and not errors


def test_scheduler_save_takes_lock(sched):
    """The json.dump/open('w') serialization point itself must be locked."""
    blocked, finished, errors = _hold_lock_worker_blocks(sched._lock, sched._save_tasks)
    assert blocked, "_save_tasks ran WITHOUT the lock (concurrent dump/write race)"
    assert finished and not errors


def test_scheduler_statistics_takes_lock(sched):
    blocked, finished, errors = _hold_lock_worker_blocks(sched._lock, sched.get_statistics)
    assert blocked, "get_statistics iterated the live dict WITHOUT the lock"
    assert finished and not errors


def test_scheduler_enable_disable_delete_locked(sched):
    tid = sched.schedule_task("t", "noop", "interval", {"interval_seconds": 9999})
    for op in (lambda: sched.enable_task(tid), lambda: sched.disable_task(tid)):
        blocked, finished, errors = _hold_lock_worker_blocks(sched._lock, op)
        assert blocked, "enable/disable ran WITHOUT the lock"
        assert finished and not errors


def test_scheduler_handler_runs_outside_lock(sched):
    """Inverse pin: a blocking action handler must NOT hold the lock."""
    entered = threading.Event()
    release = threading.Event()

    def blocking_handler(params):
        entered.set()
        release.wait(5)

    sched.register_handler("block", blocking_handler)
    tid = sched.schedule_task("t", "block", "interval", {"interval_seconds": 9999})
    result = {}

    def _run():
        result["ok"] = sched.execute_task(tid)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    assert entered.wait(3), "handler never ran"
    # If execute_task held the lock during the handler, this would time out.
    acquired = sched._lock.acquire(timeout=1.0)
    assert acquired, "execute_task held the lock while the handler ran (deadlock class)"
    if acquired:
        sched._lock.release()
    release.set()
    t.join(5)
    assert result.get("ok") is True


def test_scheduler_execute_records_result(sched):
    calls = []
    sched.register_handler("count", lambda p: calls.append(p))
    tid = sched.schedule_task("t", "count", "interval", {"interval_seconds": 9999})
    assert sched.execute_task(tid) is True
    assert calls == [{}]
    assert sched.get_task(tid)["run_count"] == 1
    assert sched.get_task(tid)["last_status"] == "success"


def test_scheduler_concurrent_storm_no_exceptions_and_valid_json(tmp_path):
    """Hammer: schedule/delete/execute/statistics/list from 6 threads."""
    from orbit.orbit.core.scheduler import ORBITcheduler

    storage = str(tmp_path / "storm.json")
    s = ORBITcheduler(storage_file=storage)
    s.register_handler("noop", lambda p: None)
    errors = []
    barrier = threading.Barrier(6)

    def mutator():
        try:
            barrier.wait()
            for _ in range(60):
                tid = s.schedule_task("m", "noop", "interval", {"interval_seconds": 1})
                s.enable_task(tid)
                s.execute_task(tid)
                s.delete_task(tid)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def reader():
        try:
            barrier.wait()
            for _ in range(60):
                s.get_statistics()
                s.list_tasks()
                s.get_due_tasks()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=mutator, daemon=True) for _ in range(3)]
    threads += [threading.Thread(target=reader, daemon=True) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not any(t.is_alive() for t in threads), "thread hung (possible deadlock)"
    assert errors == [], f"race exceptions: {errors[:5]}"
    # Storage must end up as parseable JSON with a dict of tasks
    with open(storage, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_scheduler_concurrent_saves_leave_valid_json(tmp_path):
    """Focused write race: many threads saving the same file (Phase-12 class)."""
    from orbit.orbit.core.scheduler import ORBITcheduler

    storage = str(tmp_path / "saves.json")
    s = ORBITcheduler(storage_file=storage)
    errors = []
    barrier = threading.Barrier(4)

    def worker(i):
        try:
            barrier.wait()
            for n in range(40):
                tid = s.schedule_task(f"w{i}-{n}", "noop", "interval", {"interval_seconds": 1})
                s.delete_task(tid)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert errors == [], f"write-race exceptions: {errors[:5]}"
    with open(storage, encoding="utf-8") as f:
        assert isinstance(json.load(f), dict)


# ------------------------------------------------- plugin_system (genuine 2)
@pytest.fixture
def plugin_sys(tmp_path):
    from orbit.orbit.core.plugin_system import PluginSystem

    pdir = tmp_path / "plugins"
    pdir.mkdir()
    for i in range(6):
        (pdir / f"mod_{i}.py").write_text(f"__version__ = '1.0'\nX = {i}\n", encoding="utf-8")
    (pdir / "pkg_mod").mkdir()
    (pdir / "pkg_mod" / "__init__.py").write_text("Y = 1\n", encoding="utf-8")
    return PluginSystem(plugins_dir=str(pdir))


def test_plugin_discover_takes_lock(plugin_sys):
    blocked, finished, errors = _hold_lock_worker_blocks(
        plugin_sys._plugin_lock, plugin_sys.discover_plugins, settle=0.4
    )
    assert blocked, "discover_plugins mutated _plugins WITHOUT the lock"
    assert finished and not errors


def test_plugin_list_plugins_uses_lock_snapshot(plugin_sys):
    blocked, finished, errors = _hold_lock_worker_blocks(
        plugin_sys._plugin_lock, plugin_sys.list_plugins, settle=0.4
    )
    assert blocked, "list_plugins iterated the live dict WITHOUT the lock"
    assert finished and not errors


def test_plugin_stats_and_category_readers_use_lock(plugin_sys):
    for op in (plugin_sys.get_stats, lambda: plugin_sys.get_plugins_by_category("unknown"),
               plugin_sys.list_enabled, plugin_sys.get_errors, lambda: plugin_sys.get_plugins_with_hook("on_query")):
        blocked, finished, errors = _hold_lock_worker_blocks(plugin_sys._plugin_lock, op, settle=0.4)
        assert blocked, f"{getattr(op, '__name__', op)} iterated WITHOUT the lock"
        assert finished and not errors


def test_plugin_reset_error_takes_lock(plugin_sys):
    # Seed an errored descriptor so reset_error has work to do
    plugin_sys.discover_plugins()
    name = sorted(plugin_sys._plugins)[0]
    plugin_sys._plugins[name].status = plugin_sys._plugins[name].status.ERROR
    blocked, finished, errors = _hold_lock_worker_blocks(
        plugin_sys._plugin_lock, lambda: plugin_sys.reset_error(name)
    )
    assert blocked, "reset_error mutated/serialized WITHOUT the lock"
    assert finished and not errors


def test_plugin_discover_vs_readers_storm(plugin_sys):
    """Hammer: discover thread vs reader threads over the same _plugins."""
    errors = []
    barrier = threading.Barrier(5)

    def discoverer():
        try:
            barrier.wait()
            for _ in range(50):
                plugin_sys.discover_plugins()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def reader():
        try:
            barrier.wait()
            for _ in range(50):
                plugin_sys.list_plugins()
                plugin_sys.get_stats()
                plugin_sys.get_plugins_by_category("unknown")
                plugin_sys.list_enabled()
                plugin_sys.get_errors()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=discoverer, daemon=True)]
    threads += [threading.Thread(target=reader, daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not any(t.is_alive() for t in threads), "thread hung (possible deadlock)"
    assert errors == [], f"race exceptions: {errors[:5]}"
    # All discovered modules must still be visible and counted
    stats = plugin_sys.get_stats()
    assert stats["total"] >= 7  # 6 modules + 1 package


def test_plugin_reset_error_storm(plugin_sys):
    """reset_error (mutates + _save_registry JSON) vs concurrent stats reads."""
    plugin_sys.discover_plugins()
    name = sorted(plugin_sys._plugins)[0]
    plugin_sys._plugins[name].status = plugin_sys._plugins[name].status.ERROR
    errors = []
    barrier = threading.Barrier(2)

    def resetter():
        try:
            barrier.wait()
            for _ in range(40):
                plugin_sys.reset_error(name)
                plugin_sys._plugins[name].status = plugin_sys._plugins[name].status.ERROR
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def reader():
        try:
            barrier.wait()
            for _ in range(40):
                plugin_sys.get_stats()
                plugin_sys.list_plugins()
                plugin_sys.get_errors()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=resetter, daemon=True)
    t2 = threading.Thread(target=reader, daemon=True)
    t1.start()
    t2.start()
    t1.join(30)
    t2.join(30)
    assert errors == [], f"race exceptions: {errors[:5]}"
    # Registry JSON written by _save_registry must be parseable
    reg = plugin_sys._registry_path
    if reg.exists():
        assert isinstance(json.loads(reg.read_text(encoding="utf-8")), dict)
