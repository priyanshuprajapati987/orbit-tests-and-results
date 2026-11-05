"""Regression tests for orbit-bugfix-loop iteration 2 (phase level B).

Each test reproduces a VERIFIED finding from the 2026-09-30 round-2 bug hunt
against areas iteration 1 did not cover (date/time arithmetic in a core module,
HTTP blueprint input validation). All hermetic: tmp dirs, frozen clock, no
network, no real user data.
"""

import os
from datetime import datetime

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


def _freeze_clock(monkeypatch, mod, when):
    """Replace ``mod.datetime`` with a subclass whose ``now()`` is pinned."""
    assert isinstance(when, datetime)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return when

    monkeypatch.setattr(mod, "datetime", Frozen)


def _fresh_tracker(tmp_path, monkeypatch):
    import orbit.orbit.core.relationship_tracker as rt

    monkeypatch.setattr(rt, "DATA_DIR", tmp_path)
    return rt.RelationshipTracker()


# ── BUG-5: birthday reminders vanish on the actual birthday (midnight math) ──
def test_birthday_reminder_present_on_the_birthday_itself(tmp_path, monkeypatch):
    import orbit.orbit.core.relationship_tracker as rt

    # 14:30 on the birthday: today() carries a time-of-day, bday_dt is midnight.
    _freeze_clock(monkeypatch, rt, datetime(2026, 10, 5, 14, 30, 0))
    tracker = _fresh_tracker(tmp_path, monkeypatch)
    tracker.add_contact(name="Asha", relationship="friend", importance=8, birthday="2026-10-05")

    bdays = tracker.get_birthday_reminders()

    assert len(bdays) == 1, "birthday must be reported on the birthday itself"
    assert bdays[0]["name"] == "Asha"
    assert bdays[0]["days_until"] == 0


def test_birthday_days_until_counts_whole_days(tmp_path, monkeypatch):
    import orbit.orbit.core.relationship_tracker as rt

    # 14:30 the day BEFORE the birthday -> exactly 1 day left.
    _freeze_clock(monkeypatch, rt, datetime(2026, 10, 4, 14, 30, 0))
    tracker = _fresh_tracker(tmp_path, monkeypatch)
    tracker.add_contact(name="Ravi", relationship="friend", importance=8, birthday="2026-10-05")

    bdays = tracker.get_birthday_reminders()

    assert len(bdays) == 1
    assert bdays[0]["days_until"] == 1, "day-before must report 1 day left, not 0"


def test_leap_day_birthday_reminder_works_in_non_leap_year(tmp_path, monkeypatch):
    import orbit.orbit.core.relationship_tracker as rt

    # 2027 is not a leap year: strptime("2000-02-29").replace(year=2027) raises,
    # the %m-%d fallback then rejects "2000-02-29", and the contact is skipped
    # forever -> a leap-day contact is NEVER reminded outside leap years.
    _freeze_clock(monkeypatch, rt, datetime(2027, 2, 27, 12, 0, 0))
    tracker = _fresh_tracker(tmp_path, monkeypatch)
    tracker.add_contact(name="Meera", relationship="friend", importance=9, birthday="2000-02-29")

    bdays = tracker.get_birthday_reminders()

    assert len(bdays) == 1, "leap-day birthdays must still produce a reminder"
    assert bdays[0]["days_until"] == 1  # observed Feb 28 (2027-02-28)


def test_birthday_outside_window_not_reported(tmp_path, monkeypatch):
    import orbit.orbit.core.relationship_tracker as rt

    _freeze_clock(monkeypatch, rt, datetime(2026, 10, 5, 14, 30, 0))
    tracker = _fresh_tracker(tmp_path, monkeypatch)
    tracker.add_contact(name="Far", relationship="friend", importance=8, birthday="2026-10-20")

    assert tracker.get_birthday_reminders() == []


# ── BUG-6: /api/notes returns 500 (not 400) on wrong-typed JSON fields ──────
def _notes_client(tmp_path, monkeypatch):
    from flask import Flask

    import orbit.orbit.core.quick_notes as qn
    import orbit.orbit.core.quick_notes_bp as qbp

    monkeypatch.setattr(qn, "DATA_DIR", tmp_path)
    notes = qn.QuickNotes()
    monkeypatch.setattr(qbp, "get_notes", lambda: notes)

    app = Flask(__name__)
    app.register_blueprint(qbp.quick_notes_bp)
    app.config["TESTING"] = True
    app.config["PROPAGATE_EXCEPTIONS"] = False  # mirror live server: 500, not a raise
    return app.test_client(), notes


def test_add_note_null_content_is_400(tmp_path, monkeypatch):
    client, _ = _notes_client(tmp_path, monkeypatch)

    res = client.post("/api/notes", json={"content": None})

    assert res.status_code == 400
    assert "error" in res.get_json()


def test_add_note_non_string_content_is_400(tmp_path, monkeypatch):
    client, _ = _notes_client(tmp_path, monkeypatch)

    res = client.post("/api/notes", json={"content": 123})

    assert res.status_code == 400


def test_add_note_non_string_tags_is_400(tmp_path, monkeypatch):
    client, _ = _notes_client(tmp_path, monkeypatch)

    res = client.post("/api/notes", json={"content": "hello", "tags": 5})

    assert res.status_code == 400


def test_update_note_non_string_content_is_400(tmp_path, monkeypatch):
    client, notes = _notes_client(tmp_path, monkeypatch)
    created = client.post("/api/notes", json={"content": "keep me"})
    note_id = created.get_json()["note"]["id"]

    res = client.put(f"/api/notes/{note_id}", json={"content": 42})

    assert res.status_code == 400
    assert notes.get(note_id).content == "keep me", "original note must be untouched"


def test_valid_note_requests_still_work(tmp_path, monkeypatch):
    client, notes = _notes_client(tmp_path, monkeypatch)

    created = client.post("/api/notes", json={"content": "  hello  ", "tags": ["Work", " Pri"]})
    assert created.status_code == 201
    note = created.get_json()["note"]
    assert note["content"] == "hello"
    assert note["tags"] == ["work", "pri"]

    updated = client.put(f"/api/notes/{note['id']}", json={"content": "changed", "tags": []})
    assert updated.status_code == 200
    assert updated.get_json()["note"]["content"] == "changed"

    listed = client.get("/api/notes")
    assert listed.status_code == 200
    assert listed.get_json()["count"] == 1


# ── BUG-7: /api/health blocked 100 ms per call on psutil CPU sampling ──────
def test_health_endpoint_cpu_sampling_is_non_blocking(monkeypatch):
    """psutil.cpu_percent(interval=0.1) sleeps 100ms, so the health endpoint
    - which frontends poll - always took ~118ms instead of ~15ms and held a
    worker thread for the whole sleep."""
    import threading
    import time as _time

    import psutil

    from orbit.orbit.server import create_app

    # The Flask test client runs the WSGI app synchronously in this thread, so
    # filtering on it excludes samples from background monitor threads.
    test_thread = threading.current_thread()
    sampled_intervals = []

    def _fake_cpu_percent(interval=None, percpu=False):
        if threading.current_thread() is test_thread:
            sampled_intervals.append(interval)
            if interval:  # mirror the real psutil: it sleeps `interval` seconds
                _time.sleep(interval)
        return 12.5

    monkeypatch.setattr(psutil, "cpu_percent", _fake_cpu_percent)

    app = create_app()
    with app.test_client() as client:
        sampled_intervals.clear()
        started = _time.perf_counter()
        res = client.get("/api/health")
        elapsed_ms = (_time.perf_counter() - started) * 1000

    assert res.status_code == 200
    assert res.get_json()["cpu_percent"] == 12.5, "health must still report cpu"
    assert sampled_intervals, "health must still sample cpu"
    blocking = [i for i in sampled_intervals if i not in (None, 0)]
    assert not blocking, f"health asked psutil for a blocking sample: {blocking}"
    assert elapsed_ms < 100, f"health took {elapsed_ms:.0f}ms (must not sleep)"
