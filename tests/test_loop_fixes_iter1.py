"""Regression tests for orbit-bugfix-loop iteration 1 (phase level A).

Each test reproduces a VERIFIED finding from the 2026-09-30 bug-hunt run
against ``orbit/orbit/core/*.py`` and locks the fix in. All hermetic:
tmp dirs, no network, no real user data.
"""

import json
import os
from datetime import datetime

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")


# ── BUG-1: mass.mg factor is 1000x off (base unit is kg, mg==g in table) ──
def test_unit_converter_milligram_factor():
    from orbit.orbit.core.unit_converter import UnitConverter

    conv = UnitConverter()
    assert conv.convert(1000, "mg", "g")["value"] == 1.0
    assert conv.convert(1, "g", "mg")["value"] == 1000.0
    assert conv.convert(1, "mg", "kg")["value"] == 0.000001
    assert conv.convert(1000000, "mg", "kg")["value"] == 1.0
    assert conv.convert(2.5, "kg", "mg")["value"] == 2500000.0


def test_unit_converter_mass_round_trip():
    from orbit.orbit.core.unit_converter import UnitConverter

    conv = UnitConverter()
    for unit in ("mg", "g", "kg", "oz", "lb", "ton"):
        back = conv.convert(conv.convert(7, "kg", unit)["value"], unit, "kg")
        assert abs(back["value"] - 7.0) < 1e-4, f"{unit} round trip"


# ── BUG-2: cron day-of-week matched datetime.weekday() (0=Mon) not cron ──
def test_smart_scheduler_cron_dow_sunday_is_zero():
    from orbit.orbit.core.smart_scheduler import _cron_matches, _parse_cron

    sunday = datetime(2026, 10, 4)  # weekday()==6
    monday = datetime(2026, 10, 5)  # weekday()==0
    saturday = datetime(2026, 10, 3)  # weekday()==5
    friday = datetime(2026, 10, 2)  # weekday()==4

    assert _cron_matches(_parse_cron("0 0 * * 0"), sunday) is True
    assert _cron_matches(_parse_cron("0 0 * * 0"), monday) is False
    assert _cron_matches(_parse_cron("0 0 * * 6"), saturday) is True
    assert _cron_matches(_parse_cron("0 0 * * 7"), sunday) is True
    assert _cron_matches(_parse_cron("0 0 * * 5"), friday) is True


def test_smart_scheduler_cron_dow_ranges_and_lists():
    from orbit.orbit.core.smart_scheduler import _cron_matches, _parse_cron

    sunday = datetime(2026, 10, 4)
    monday = datetime(2026, 10, 5)
    saturday = datetime(2026, 10, 3)
    friday = datetime(2026, 10, 2)
    tuesday = datetime(2026, 10, 6)

    # 5-7 = Fri,Sat,Sun in cron
    assert _cron_matches(_parse_cron("0 0 * * 5-7"), friday) is True
    assert _cron_matches(_parse_cron("0 0 * * 5-7"), saturday) is True
    assert _cron_matches(_parse_cron("0 0 * * 5-7"), sunday) is True
    assert _cron_matches(_parse_cron("0 0 * * 5-7"), monday) is False

    # 1-5 = Mon..Fri
    assert _cron_matches(_parse_cron("0 0 * * 1-5"), monday) is True
    assert _cron_matches(_parse_cron("0 0 * * 1-5"), tuesday) is True
    assert _cron_matches(_parse_cron("0 0 * * 1-5"), saturday) is False
    assert _cron_matches(_parse_cron("0 0 * * 1-5"), sunday) is False

    # comma list 0,3 = Sun + Wed
    assert _cron_matches(_parse_cron("0 0 * * 0,3"), sunday) is True
    assert _cron_matches(_parse_cron("0 0 * * 0,3"), monday) is False

    # */2 steps from Sunday
    assert _cron_matches(_parse_cron("0 0 * * */2"), sunday) is True
    assert _cron_matches(_parse_cron("0 0 * * */2"), monday) is False
    assert _cron_matches(_parse_cron("0 0 * * */2"), saturday) is True

    # non-dow fields untouched
    assert _cron_matches(_parse_cron("0 12 * * *"), datetime(2026, 10, 5, 12, 0)) is True
    assert _cron_matches(_parse_cron("0 12 * * *"), datetime(2026, 10, 5, 13, 0)) is False


def test_smart_scheduler_next_cron_lands_on_sunday():
    from orbit.orbit.core.smart_scheduler import _next_cron_time, _parse_cron

    # 2026-09-30 is a Wednesday; next `0 0 * * 0` must be Sunday 2026-10-04.
    nxt = _next_cron_time(_parse_cron("0 0 * * 0"), datetime(2026, 9, 30, 12, 0))
    assert nxt == datetime(2026, 10, 4, 0, 0)


# ── BUG-3: completed_today never rolls over (daily habit completable once) ─
def _fresh_tracker(tmp_path, monkeypatch):
    import orbit.orbit.core.habit_tracker as ht

    monkeypatch.setattr(ht, "DATA_DIR", tmp_path)
    tracker = ht.HabitTracker()
    return tracker, tracker.list_habits()[0]["id"]


def test_habit_completed_flag_rolls_over_to_new_day(tmp_path, monkeypatch):
    tracker, hid = _fresh_tracker(tmp_path, monkeypatch)

    # Yesterday's completion: flag still True, history only has yesterday.
    with tracker._lock:
        tracker._habits[0]["completed_today"] = True
        tracker._habits[0]["streak"] = 3
        tracker._habits[0]["history"] = [{"date": "2000-01-01", "completed": True}]
        tracker._save()

    assert tracker.get_habit(hid)["completed_today"] is False
    assert tracker.list_habits()[0]["completed_today"] is False

    out = tracker.complete_habit(hid)
    today = datetime.now().strftime("%Y-%m-%d")
    assert out["streak"] == 4
    assert out["completed_today"] is True
    assert [e for e in out["history"] if e["date"] == today]


def test_habit_complete_is_idempotent_per_day(tmp_path, monkeypatch):
    tracker, hid = _fresh_tracker(tmp_path, monkeypatch)
    today = datetime.now().strftime("%Y-%m-%d")

    tracker.complete_habit(hid)
    tracker.reset_daily()
    again = tracker.complete_habit(hid)

    # Second completion on the same day must not inflate the streak.
    assert again["streak"] == 1
    assert sum(1 for e in again["history"] if e["date"] == today) == 1
    assert again["completed_today"] is True
    assert again["completion_rate"] == 100.0


def test_habit_uncomplete_works_after_flag_reset(tmp_path, monkeypatch):
    tracker, hid = _fresh_tracker(tmp_path, monkeypatch)

    tracker.complete_habit(hid)
    tracker.reset_daily()
    out = tracker.uncomplete_habit(hid)

    assert out["streak"] == 0
    assert out["history"] == []
    assert out["completed_today"] is False


# ── BUG-4: corrupt ideas.json is reseeded with stock ideas (data loss) ──
def _fresh_vault(tmp_path, monkeypatch):
    import orbit.orbit.core.idea_vault as iv

    monkeypatch.setattr(iv, "DATA_DIR", tmp_path)
    return iv.IdeaVault()


def test_idea_vault_corrupt_file_quarantined_not_reseeded(tmp_path, monkeypatch):
    (tmp_path / "ideas.json").write_text('[{"id": "user1", "title": "MY IDEA"', encoding="utf-8")

    vault = _fresh_vault(tmp_path, monkeypatch)

    # User's file must NOT be silently replaced by the 5 stock ideas.
    assert vault.list_ideas() == []
    assert (tmp_path / "ideas.json.corrupt").exists()

    added = vault.add_idea("fresh idea", "description")
    assert [i["title"] for i in vault.list_ideas()] == ["fresh idea"]
    assert added["title"] == "fresh idea"


def test_idea_vault_wrong_shape_file_quarantined(tmp_path, monkeypatch):
    (tmp_path / "ideas.json").write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    vault = _fresh_vault(tmp_path, monkeypatch)

    # Wrong-shaped JSON used to leave a dict in place: list_ideas()/add_idea()
    # then raised AttributeError on every call.
    assert vault.list_ideas() == []
    assert (tmp_path / "ideas.json.corrupt").exists()
    vault.add_idea("works now", "ok")
    assert len(vault.list_ideas()) == 1


def test_idea_vault_explicit_empty_list_is_preserved(tmp_path, monkeypatch):
    (tmp_path / "ideas.json").write_text("[]", encoding="utf-8")

    vault = _fresh_vault(tmp_path, monkeypatch)

    assert vault.list_ideas() == []


def test_idea_vault_save_is_atomic(tmp_path, monkeypatch):
    import orbit.orbit.core.idea_vault as iv

    monkeypatch.setattr(iv, "DATA_DIR", tmp_path)
    calls = []
    real_write = iv.atomic_write_text

    def spy(path, text, encoding="utf-8"):
        calls.append(str(path))
        real_write(path, text, encoding)

    monkeypatch.setattr(iv, "atomic_write_text", spy)
    vault = iv.IdeaVault()
    vault.add_idea("atomic", "check")
    assert calls, "IdeaVault._save must write through atomic_write_text"
    titles = [i["title"] for i in json.loads((tmp_path / "ideas.json").read_text(encoding="utf-8"))]
    assert "atomic" in titles
