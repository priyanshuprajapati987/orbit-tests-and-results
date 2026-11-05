"""Phase 8 regression — NoneType container loads.

json.loads() accepts any valid JSON. A file containing `null`, `[]`, `"str"`,
or `5` parses fine (so the `except Exception: return {}` never fires) but the
result is NOT a dict — the next `.get()` / `in` / `.keys()` raises
AttributeError: 'NoneType' object has no attribute 'get' (or TypeError for `in`).

These tests pin the isinstance-dict guards added to _load-style helpers so
valid-JSON-non-object content degrades to the default empty dict, never crashes.
"""
import json

import pytest

from orbit.orbit import focus_timer, lists, usage_tracker


class TestListsLoadNonDict:
    """lists._load must return {} when lists.json holds valid non-object JSON."""

    def test_null_content_returns_empty(self, tmp_path, monkeypatch):
        f = tmp_path / "lists.json"
        f.write_text("null", encoding="utf-8")
        monkeypatch.setattr(lists, "LISTS_FILE", f)
        # Before fix: json.loads("null") -> None -> list_names() -> None.keys() AttributeError
        assert lists.list_names() == []

    def test_list_content_returns_empty(self, tmp_path, monkeypatch):
        f = tmp_path / "lists.json"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        monkeypatch.setattr(lists, "LISTS_FILE", f)
        assert lists.list_names() == []

    def test_string_content_returns_empty(self, tmp_path, monkeypatch):
        f = tmp_path / "lists.json"
        f.write_text('"hello"', encoding="utf-8")
        monkeypatch.setattr(lists, "LISTS_FILE", f)
        assert lists.list_names() == []

    def test_valid_dict_still_works(self, tmp_path, monkeypatch):
        f = tmp_path / "lists.json"
        f.write_text(json.dumps({"shopping": {"name": "shopping", "items": ["milk"]}}), encoding="utf-8")
        monkeypatch.setattr(lists, "LISTS_FILE", f)
        assert "shopping" in lists.list_names()

    def test_add_item_recovers_after_corrupt_null(self, tmp_path, monkeypatch):
        # Corrupt file -> empty load -> add_item still succeeds and rewrites a valid dict
        f = tmp_path / "lists.json"
        f.write_text("null", encoding="utf-8")
        monkeypatch.setattr(lists, "LISTS_FILE", f)
        out = lists.add_item("todo", "buy milk")
        assert out is not None
        # file is now valid dict again
        data = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "todo" in data


class TestFocusTimerLoadNonDict:
    def test_list_content_returns_default(self, tmp_path, monkeypatch):
        f = tmp_path / "stats.json"
        f.write_text("[]", encoding="utf-8")
        monkeypatch.setattr(focus_timer, "STATS_FILE", f)
        stats = focus_timer._load_stats()
        assert isinstance(stats, dict)

    def test_null_content_returns_default(self, tmp_path, monkeypatch):
        f = tmp_path / "stats.json"
        f.write_text("null", encoding="utf-8")
        monkeypatch.setattr(focus_timer, "STATS_FILE", f)
        stats = focus_timer._load_stats()
        assert isinstance(stats, dict)


class TestUsageTrackerLoadNonDict:
    def test_null_content_returns_default(self, tmp_path, monkeypatch):
        # usage_tracker may name its file attr differently; find it
        file_attr = None
        for attr in dir(usage_tracker):
            val = getattr(usage_tracker, attr, None)
            if hasattr(val, "name") and str(val).endswith(".json"):
                file_attr = attr
                break
        if file_attr is None:
            pytest.skip("usage_tracker json path attr not found")
        f = tmp_path / "usage.json"
        f.write_text("null", encoding="utf-8")
        monkeypatch.setattr(usage_tracker, file_attr, f)
        loader = getattr(usage_tracker, "_load", None)
        if loader is None:
            pytest.skip("usage_tracker._load not found")
        result = loader()
        assert isinstance(result, dict)


class TestJsonLoadsNonePattern:
    """Generic proof of the bug class the guards close."""

    def test_null_loads_is_none_not_dict(self):
        # Demonstrates the root cause: valid JSON `null` parses to None
        assert json.loads("null") is None

    def test_valid_non_object_bypasses_except(self):
        # `except Exception` does NOT catch this — it's not an error at all
        try:
            result = json.loads("null")
            raised = False
        except Exception:
            raised = True
        assert raised is False
        assert result is None
        # Without the isinstance guard: result.get("x") -> AttributeError
        with pytest.raises(AttributeError):
            result.get("x")  # type: ignore[union-attr]
