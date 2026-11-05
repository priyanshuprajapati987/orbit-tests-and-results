# ORBIT — Data Analyzer tests (Phase 1)
# Run: python -m pytest tests/test_data_analyzer.py -v

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_load_csv_basic(tmp_path):
    from orbit.orbit.core.data_analyzer import DataAnalyzer
    p = tmp_path / "data.csv"
    _write_csv(p, [{"name": "a", "val": "10"}, {"name": "b", "val": "20"}])
    res = DataAnalyzer().load_csv(str(p))
    assert res["rows"] == 2
    assert res["columns"] == 2
    assert "name" in res["columns_list"]


def test_load_csv_missing_file():
    from orbit.orbit.core.data_analyzer import DataAnalyzer
    res = DataAnalyzer().load_csv("/nonexistent/file.csv")
    assert "error" in res


def test_load_csv_empty(tmp_path):
    from orbit.orbit.core.data_analyzer import DataAnalyzer
    p = tmp_path / "empty.csv"
    p.write_text("a,b\n", encoding="utf-8")
    res = DataAnalyzer().load_csv(str(p))
    assert res["rows"] == 0


def test_numeric_stats(tmp_path):
    from orbit.orbit.core.data_analyzer import DataAnalyzer
    p = tmp_path / "data.csv"
    _write_csv(p, [{"v": "1"}, {"v": "2"}, {"v": "3"}])
    res = DataAnalyzer().load_csv(str(p))
    col = res["column_stats"]["v"]
    assert col["type"] == "numeric"
    assert col["min"] == 1.0
    assert col["max"] == 3.0
    assert col["avg"] == 2.0
