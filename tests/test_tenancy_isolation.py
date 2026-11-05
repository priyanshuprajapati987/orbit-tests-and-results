"""Milestone 3 row-level isolation leak tests (hermetic, tmp dirs).

Rule under test: user A must NEVER see user B's rows, and solo
("local") behavior is unchanged. A leak fails the test.
"""

import os

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


def _mempool(tmp_path, monkeypatch):
    import orbit.orbit.core.memory_store as ms

    monkeypatch.setattr(ms, "_pool", None)
    pool = ms.SharedMemoryPool.__new__(ms.SharedMemoryPool)
    import threading

    pool._lock = threading.RLock()
    pool._store = {}
    pool.storage_file = str(tmp_path / "mem.json")
    from orbit.orbit.core.memory_store import AccessControl, RelevanceScorer

    pool.access_control = AccessControl()
    pool.scorer = RelevanceScorer()
    from orbit.orbit.core.memory_store import DecayEngine

    pool.decay = DecayEngine()
    pool._save = lambda: None
    return pool


def test_memory_no_cross_user_leak(tmp_path, monkeypatch):
    pool = _mempool(tmp_path, monkeypatch)
    pool.write("MEM", "agent", "secret", {"v": "A-private"}, user_id="alice")
    pool.write("MEM", "agent", "secret", {"v": "B-private"}, user_id="bob")

    # Same namespace+key, different owners: no overwrite, no visibility.
    assert pool.read("MEM", "agent", "secret", user_id="alice").value == {"v": "A-private"}
    assert pool.read("MEM", "agent", "secret", user_id="bob").value == {"v": "B-private"}

    res_b = pool.search("secret", "MEM", user_id="bob")
    assert all("B-private" in str(r.get("value", "")) or "secret" not in str(r).lower() for r in res_b)
    assert not any("A-private" in str(r) for r in res_b)

    assert pool.delete("MEM", "agent", "secret", user_id="alice") is True
    # Bob's row survives Alice's delete.
    assert pool.read("MEM", "agent", "secret", user_id="bob") is not None
    # Alice can no longer see it (hers is gone).
    assert pool.read("MEM", "agent", "secret", user_id="alice") is None


def test_memory_solo_unchanged(tmp_path, monkeypatch):
    pool = _mempool(tmp_path, monkeypatch)
    pool.write("MEM", "agent", "k", {"v": 1})
    assert pool.read("MEM", "agent", "k").value == {"v": 1}
    assert pool.search("k", "MEM") != []


def test_conversation_no_cross_user_leak(tmp_path, monkeypatch):
    from orbit.orbit.core.conversation_manager import ConversationManager

    mgr = ConversationManager.__new__(ConversationManager)
    import threading

    mgr._lock = threading.RLock()
    mgr._conversations = {}
    mgr._active_id = None
    mgr._save_all = lambda: None
    mgr._save_single = lambda cid: None

    a = mgr.create("A chat", "hello", user_id="alice")
    b = mgr.create("B chat", "hello", user_id="bob")

    assert mgr.get(a["id"], user_id="alice")["id"] == a["id"]
    assert mgr.get(a["id"], user_id="bob") is None
    assert mgr.get(b["id"], user_id="alice") is None

    assert {c["id"] for c in mgr.list_all(user_id="alice")} == {a["id"]}
    assert {c["id"] for c in mgr.list_all(user_id="bob")} == {b["id"]}

    assert mgr.send(a["id"], "user", "hi", user_id="bob") is None
    assert mgr.delete(a["id"], user_id="bob") is False
    assert mgr.get(a["id"], user_id="alice") is not None
    assert mgr.rename(a["id"], "X", user_id="bob") is False
    assert mgr.search("hello", user_id="alice") != []
    assert mgr.search("hello", user_id="mallory") == []
    assert mgr.export_markdown(a["id"], user_id="bob") == ""


def test_conversation_solo_unchanged(tmp_path, monkeypatch):
    from orbit.orbit.core.conversation_manager import ConversationManager

    mgr = ConversationManager.__new__(ConversationManager)
    import threading

    mgr._lock = threading.RLock()
    mgr._conversations = {}
    mgr._active_id = None
    mgr._save_all = lambda: None
    mgr._save_single = lambda cid: None

    c = mgr.create("solo")
    assert mgr.get(c["id"])["id"] == c["id"]
    assert mgr.send(c["id"], "user", "hi") is not None
    assert len(mgr.list_all()) == 1


def test_tasks_no_cross_user_leak(tmp_path):
    from orbit.orbit.core.task_scheduler import TaskScheduler

    s = TaskScheduler(data_dir=tmp_path)
    s.register_handler("noop", lambda payload: "ok")
    a = s.add_task("a-task", payload={"handler": "noop"}, user_id="alice")
    b = s.add_task("b-task", payload={"handler": "noop"}, user_id="bob")

    assert {t.task_id for t in s.list_tasks(user_id="alice")} == {a.task_id}
    assert {t.task_id for t in s.list_tasks(user_id="bob")} == {b.task_id}
    assert s.get_task(a.task_id, user_id="bob") is None
    assert s.remove_task(a.task_id, user_id="bob") is False
    assert s.get_task(a.task_id, user_id="alice") is not None
    e = s.run_task_now(b.task_id)
    assert e is not None and e.success is True


def test_engine_sessions_isolated():
    from orbit.orbit.core.conversation_engine import get_engine, reset_session

    reset_session("u-alice")
    reset_session("u-bob")
    ea = get_engine("u-alice")
    eb = get_engine("u-bob")
    assert ea is not eb
    assert ea.session_id == "u-alice"
    ea._history.append({"role": "user", "content": "alice-secret"})
    assert all("alice-secret" not in str(m) for m in eb._history)
    assert get_engine("u-alice") is ea  # stable within TTL
    reset_session("u-alice")
    reset_session("u-bob")
    assert get_engine() is get_engine()  # default solo stable
