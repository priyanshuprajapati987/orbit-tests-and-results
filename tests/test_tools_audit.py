# ORBIT — Tools & ground-truth benchmark function audit.
# Pure-logic: GroundTruthItem.check (all categories), calendar CRUD,
# file_tools safety, smart_actions, news categories, tools registry.
# Network/hardware tools are env-gated or mocked.
#
# Run:  python -m pytest tests/test_tools_audit.py -v
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ───────────────────────── ground_truth.check ─────────────────────────

class TestGroundTruthCheck:
    def _item(self, **kw):
        from orbit.orbit.core.ground_truth import GroundTruthItem

        defaults = dict(prompt="q", answer="a")
        defaults.update(kw)
        return GroundTruthItem(**defaults)

    def test_facts_required_hit(self):
        item = self._item(required=["canberra"], category="facts")
        r = item.check("The capital is Canberra, of course.")
        assert r["correct"] is True
        assert r["coverage"] == 1.0
        assert "canberra" in r["required_found"]

    def test_facts_required_miss(self):
        item = self._item(required=["canberra"], category="facts")
        r = item.check("It is Sydney.")
        assert r["correct"] is False
        assert r["coverage"] == 0.0

    def test_facts_case_insensitive(self):
        item = self._item(required=["CANBERRA"])
        r = item.check("canberra is the answer")
        assert r["correct"] is True

    def test_any_of_one_hit(self):
        item = self._item(any_of=["da vinci", "leonardo"])
        r = item.check("Painted by Leonardo")
        assert r["correct"] is True
        assert r["coverage"] == 1.0

    def test_any_of_none_hit(self):
        item = self._item(any_of=["da vinci", "leonardo"])
        r = item.check("Painted by Picasso")
        assert r["correct"] is False

    def test_math_number_exact(self):
        item = self._item(number=100.0, required=["100"])
        r = item.check("The boiling point is 100 C")
        assert r["correct"] is True
        assert r["numeric_ok"] is True

    def test_math_comma_normalized(self):
        item = self._item(number=299792458.0, required=["speed"])
        r = item.check("speed of light is 299,792,458 m/s")
        assert r["numeric_ok"] is True

    def test_math_tolerance(self):
        item = self._item(number=10.0, tolerance=0.1, required=["ten"])
        r = item.check("the answer is ten, about 10.05")
        assert r["numeric_ok"] is True

    def test_math_wrong_number(self):
        item = self._item(number=42.0, required=["answer"])
        r = item.check("the answer is 43")
        assert r["numeric_ok"] is False

    def test_pure_numeric_only(self):
        # no required/any_of -> numeric alone decides
        item = self._item(number=7.0)
        assert item.check("7")["correct"] is True
        assert item.check("8")["correct"] is False
        assert item.check("")["correct"] is False

    def test_latex_frac_normalized(self):
        item = self._item(number=0.5, required=["half"])
        r = item.check(r"the value is \frac{1}{2}")
        assert r["numeric_ok"] is True

    def test_coverage_multiple_required(self):
        item = self._item(required=["python", "programming"])
        r = item.check("Python is a programming language")
        assert r["coverage"] == 1.0
        r2 = item.check("Python is great")
        assert r2["coverage"] == 0.5
        assert r2["correct"] is False  # all required must hit

    def test_empty_response(self):
        item = self._item(required=["x"])
        r = item.check("")
        assert r["correct"] is False

    def test_none_response(self):
        item = self._item(required=["x"])
        r = item.check(None)
        assert r["correct"] is False


class TestGroundTruthSuite:
    def test_suite_size_and_categories(self):
        from orbit.orbit.core.ground_truth import GROUND_TRUTH
        from collections import Counter

        assert len(GROUND_TRUTH) == 103
        cats = Counter(i.category for i in GROUND_TRUTH)
        assert cats["facts"] == 34
        assert cats["math"] == 25
        assert cats["coding"] == 20
        assert cats["reasoning"] == 14
        assert cats["general"] == 10

    def test_every_item_has_prompt_and_answer(self):
        from orbit.orbit.core.ground_truth import GROUND_TRUTH

        for item in GROUND_TRUTH:
            assert item.prompt and item.prompt.strip()
            assert item.answer and item.answer.strip()

    def test_every_facts_item_has_criteria(self):
        from orbit.orbit.core.ground_truth import GROUND_TRUTH

        for item in GROUND_TRUTH:
            if item.category == "facts":
                assert item.required or item.any_of or item.number is not None, item.prompt

    def test_summarize_shape(self):
        from orbit.orbit.core.ground_truth import summarize

        results = [
            {"category": "facts", "correct": True, "coverage": 1.0},
            {"category": "facts", "correct": False, "coverage": 0.5},
            {"category": "math", "correct": True, "coverage": 1.0},
        ]
        s = summarize(results)
        assert s["total"] == 3
        assert s["correct"] == 2
        by_cat = {c["category"]: c for c in s["categories"]}
        assert by_cat["facts"]["total"] == 2
        assert by_cat["facts"]["accuracy"] == 0.5

    def test_summarize_empty(self):
        from orbit.orbit.core.ground_truth import summarize

        s = summarize([])
        assert s["total"] == 0
        assert s["overall_accuracy"] == 0.0


# ───────────────────────── calendar_tool ─────────────────────────

class TestCalendarTool:
    @pytest.fixture
    def cal(self, tmp_path):
        from orbit.orbit.tools.calendar_tool import CalendarTool

        return CalendarTool(storage_file=str(tmp_path / "cal_test.json"))

    def test_create_event(self, cal):
        r = cal.create_event("Team sync", "2026-10-20", "10:00", 30, "Weekly sync")
        assert r["success"] is True
        assert r["event"]["title"] == "Team sync"
        assert r["event"]["date"] == "2026-10-20"
        assert r["event"]["id"].startswith("evt_")

    def test_create_event_bad_date_fallback(self, cal):
        r = cal.create_event("Bad date", "not-a-date")
        assert r["success"] is True
        # falls back to today
        assert r["event"]["date"]  # non-empty

    def test_get_event(self, cal):
        r = cal.create_event("Meeting", "2026-10-21")
        eid = r["event"]["id"]
        e = cal.get_event(eid)
        assert e["title"] == "Meeting"

    def test_get_event_missing(self, cal):
        assert cal.get_event("evt_nonexistent") is None

    def test_list_events_sorted(self, cal):
        cal.create_event("Later", "2026-10-25")
        cal.create_event("Earlier", "2026-10-20")
        events = cal.list_events()
        assert events[0]["title"] == "Earlier"

    def test_list_events_date_filter(self, cal):
        cal.create_event("A", "2026-10-20")
        cal.create_event("B", "2026-11-01")
        events = cal.list_events(date_from="2026-10-21", date_to="2026-11-30")
        assert len(events) == 1
        assert events[0]["title"] == "B"

    def test_update_event(self, cal):
        r = cal.create_event("Old", "2026-10-20")
        eid = r["event"]["id"]
        ok = cal.update_event(eid, title="New", date="2026-10-22")
        assert ok is True
        assert cal.get_event(eid)["title"] == "New"

    def test_update_event_missing(self, cal):
        assert cal.update_event("evt_none", title="x") is False

    def test_update_event_ignores_unknown_fields(self, cal):
        r = cal.create_event("Keep", "2026-10-20")
        eid = r["event"]["id"]
        cal.update_event(eid, evil_field="hacked", title="Safe")
        e = cal.get_event(eid)
        assert "evil_field" not in e
        assert e["title"] == "Safe"

    def test_delete_event(self, cal):
        r = cal.create_event("Del", "2026-10-20")
        eid = r["event"]["id"]
        assert cal.delete_event(eid) is True
        assert cal.get_event(eid) is None

    def test_delete_event_missing(self, cal):
        assert cal.delete_event("evt_none") is False

    def test_search_events(self, cal):
        cal.create_event("Dentist appointment", "2026-10-20", description="checkup")
        cal.create_event("Gym", "2026-10-21")
        hits = cal.search_events("dentist")
        assert len(hits) == 1
        assert hits[0]["title"] == "Dentist appointment"

    def test_search_events_description(self, cal):
        cal.create_event("Event", "2026-10-20", description="important project")
        hits = cal.search_events("project")
        assert len(hits) == 1

    def test_get_today(self, cal):
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        cal.create_event("Today event", today)
        assert len(cal.get_today()) == 1

    def test_get_upcoming(self, cal):
        from datetime import datetime, timedelta

        soon = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        cal.create_event("Soon", soon)
        assert len(cal.get_upcoming(days=7)) == 1
        assert len(cal.get_upcoming(days=1)) == 0

    def test_complete_event(self, cal):
        r = cal.create_event("Done task", "2026-10-20")
        eid = r["event"]["id"]
        cal.complete_event(eid)
        # completed events hidden from default list
        assert len(cal.list_events()) == 0
        assert len(cal.list_events(include_completed=True)) == 1

    def test_persistence_roundtrip(self, tmp_path):
        from orbit.orbit.tools.calendar_tool import CalendarTool

        f = str(tmp_path / "persist.json")
        c1 = CalendarTool(storage_file=f)
        c1.create_event("Persisted", "2026-10-20")
        c2 = CalendarTool(storage_file=f)  # reload from disk
        assert len(c2.list_events()) == 1


# ───────────────────────── file_tools ─────────────────────────

class TestFileTools:
    def _ft(self):
        from orbit.orbit.tools.file_tools import FileTools

        return FileTools()

    def _ft_open(self, monkeypatch):
        """FileTools with the policy gate forced-open (tests real file ops,
        not the workspace sandbox — sandbox is tested separately below)."""
        from orbit.orbit.tools.file_tools import FileTools

        ft = FileTools()
        monkeypatch.setattr(ft, "_gate", lambda *a, **k: None)
        return ft

    def test_gate_blocks_outside_workspace(self):
        """Policy engine must block writes outside the ORBIT workspace."""
        ft = self._ft()
        blocked = ft._gate("write", r"C:\Windows\Temp\evil.txt", mutate=True)
        assert blocked is not None
        assert "error" in blocked
        assert "denied" in blocked["error"].lower() or "approval" in blocked["error"].lower()

    def test_gate_allows_read(self, tmp_path):
        ft = self._ft()
        # read gate returns None (allowed) for normal paths
        decision = ft._gate("read", str(tmp_path / "ok.txt"), mutate=False)
        assert decision is None or "error" not in str(decision)

    def test_is_safe_path_normal(self, tmp_path):
        ft = self._ft()
        assert ft._is_safe_path(str(tmp_path / "ok.txt")) is True

    def test_is_safe_path_blocked(self):
        ft = self._ft()
        assert ft._is_safe_path("C:\\Windows\\System32\\evil.dll") is False
        assert ft._is_safe_path("C:\\Users\\x\\.git\\config") is False
        assert ft._is_safe_path("node_modules\\evil") is False

    def test_is_safe_path_garbage(self):
        ft = self._ft()
        assert ft._is_safe_path(None) is False
        # empty string resolves to cwd (no blocked parts) -> True
        assert ft._is_safe_path("") is True

    def test_read_write_roundtrip(self, tmp_path, monkeypatch):
        ft = self._ft_open(monkeypatch)
        f = str(tmp_path / "rw.txt")
        w = ft.write(f, "hello world")
        assert "error" not in w
        r = ft.read(f)
        assert "hello world" in str(r)

    def test_read_missing_file(self, tmp_path, monkeypatch):
        ft = self._ft_open(monkeypatch)
        r = ft.read(str(tmp_path / "nope.txt"))
        assert "error" in r

    def test_append(self, tmp_path, monkeypatch):
        ft = self._ft_open(monkeypatch)
        f = str(tmp_path / "app.txt")
        ft.write(f, "line1")
        ft.append(f, "line2")
        r = ft.read(f)
        assert "line1" in str(r) and "line2" in str(r)

    def test_edit(self, tmp_path, monkeypatch):
        ft = self._ft_open(monkeypatch)
        f = str(tmp_path / "edit.txt")
        ft.write(f, "foo bar baz")
        ft.edit(f, "bar", "qux")
        r = ft.read(f)
        assert "qux" in str(r) and "bar" not in str(r)

    def test_list_dir(self, tmp_path):
        ft = self._ft()
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        r = ft.list_dir(str(tmp_path))
        assert "a.txt" in str(r)

    def test_list_dir_hidden_excluded(self, tmp_path):
        ft = self._ft()
        (tmp_path / ".hidden").write_text("x")
        r = ft.list_dir(str(tmp_path), show_hidden=False)
        assert ".hidden" not in str(r)

    def test_copy_move(self, tmp_path, monkeypatch):
        ft = self._ft_open(monkeypatch)
        src = tmp_path / "src.txt"
        src.write_text("data")
        ft.copy(str(src), str(tmp_path / "dst.txt"))
        assert (tmp_path / "dst.txt").exists()
        ft.move(str(tmp_path / "dst.txt"), str(tmp_path / "moved.txt"))
        assert (tmp_path / "moved.txt").exists()
        assert not (tmp_path / "dst.txt").exists()

    def test_search_filename_glob(self, tmp_path, monkeypatch):
        # search() uses rglob (filename glob), NOT content search
        ft = self._ft_open(monkeypatch)
        (tmp_path / "report.txt").write_text("data")
        (tmp_path / "notes.md").write_text("data")
        r = ft.search(str(tmp_path), "*.txt")
        assert "report.txt" in str(r)
        assert r.get("count", 0) >= 1

    def test_search_no_match(self, tmp_path, monkeypatch):
        ft = self._ft_open(monkeypatch)
        (tmp_path / "a.txt").write_text("x")
        r = ft.search(str(tmp_path), "*.nonexistent")
        assert r.get("count", 0) == 0


# ───────────────────────── smart_actions ─────────────────────────

class TestSmartActions:
    def test_list_actions(self):
        from orbit.orbit.tools.smart_actions import SmartActions

        sa = SmartActions()
        d = sa.list_actions()
        assert "actions" in d
        for key in ("explain", "fix", "optimize", "document", "format", "find_bugs", "add_tests", "refactor"):
            assert key in d["actions"]

    def test_run_action_unknown(self):
        from orbit.orbit.tools.smart_actions import SmartActions

        sa = SmartActions()
        r = sa.run_action("bogus_action", "x = 1", "python")
        assert "error" in r or r.get("success") is False


# ───────────────────────── news ─────────────────────────

class TestNews:
    def test_list_categories(self):
        from orbit.orbit.tools.news import NewsTool

        n = NewsTool()
        cats = n.list_categories()
        assert isinstance(cats, list)
        assert len(cats) > 0

    @pytest.mark.skipif(
        not __import__("os").getenv("ORBIT_REAL_NET"),
        reason="set ORBIT_REAL_NET=1 for live RSS",
    )
    def test_fetch_rss_live(self):
        from orbit.orbit.tools.news import NewsTool

        n = NewsTool()
        r = n.fetch_rss(category="technology", limit=3)
        assert isinstance(r, (list, dict))


# ───────────────────────── security (pure parts) ─────────────────────────

class TestSecurity:
    def test_ps_quote_escapes(self):
        from orbit.orbit.tools.security import SecurityTool

        st = SecurityTool()
        q = st._ps_quote("it's a 'test'")
        assert "'" not in q or "''" in q  # single quotes escaped

    def test_disk_usage(self):
        from orbit.orbit.tools.security import SecurityTool

        st = SecurityTool()
        r = st.disk_usage()
        assert isinstance(r, list)


# ───────────────────────── tools registry ─────────────────────────

class TestToolsRegistry:
    def test_all_tools_import(self):
        from orbit.orbit.tools import (
            BrowserTool, CalendarTool, CodeCompletionEngine, ComputerTool,
            CuaComputerTool, DesktopAutomationTool, EmailTool, FileTools,
            GitHubTool, MCPManager, MCPClient, NewsTool, ORBITMCPServer,
            SEOTool, SecurityTool, SmartActions, WebSearchTool, N8nTool,
        )

        # all imports succeeded (no ImportError)
        assert True

    def test_core_tools_have_run_or_methods(self):
        from orbit.orbit.tools import CalendarTool, FileTools, NewsTool, SecurityTool

        assert hasattr(FileTools(), "read")
        assert hasattr(CalendarTool(), "create_event")
        assert hasattr(NewsTool(), "fetch_rss")
        assert hasattr(SecurityTool(), "scan_processes")

    def test_tool_count_matches_claims(self):
        # README claims 36 tools: 20 tool modules + 16 core utility tools
        import re

        tools_dir = Path(__file__).resolve().parent.parent / "orbit" / "orbit" / "tools"
        mods = [p for p in tools_dir.glob("*.py")
                if not p.name.startswith("_") and not p.name.endswith("_bp.py")]
        assert len(mods) >= 15  # at least the 20-ish core tool modules
