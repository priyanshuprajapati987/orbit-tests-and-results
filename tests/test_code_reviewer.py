"""Tests for Code Reviewer (System 14)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.core.code_reviewer import (
    ReviewIssue,
    ReviewReport,
    _check_line,
    get_code_reviewer,
)

CLEAN_FILES = [
    {
        "path": "src/main.py",
        "content": 'import os\n\ndef main():\n    """Entry point."""\n    return os.getenv(\'PORT\')\n',
    },
    {
        "path": "src/config.py",
        "content": 'import os\n\nclass Config:\n    """App config."""\n    DEBUG = True\n',
    },
]

DIRTY_FILES = [
    {
        "path": "src/auth.py",
        "content": """import os
password = "supersecret"
api_key = "abc123"
token = "xyz"

def login():
    password = "hardcoded"
    eval("dangerous")
    exec("bad")
    return True

except:
    pass

def bad_default(items=[]):
    pass
""",
    },
    {
        "path": "src/db.py",
        "content": 'import sqlite3\n\ndef query():\n    f"SELECT * FROM users WHERE id = {id}".execute()\n',
    },
]


class TestCodeReviewer:
    def test_singleton(self):
        r1 = get_code_reviewer()
        r2 = get_code_reviewer()
        assert r1 is r2

    def test_review_clean_files(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(CLEAN_FILES, "clean_project")
        assert result["project_name"] == "clean_project"
        assert result["total_issues"] == 0

    def test_review_dirty_files(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(DIRTY_FILES, "dirty_project")
        assert result["total_issues"] > 0

    def test_review_detects_secrets(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(DIRTY_FILES, "secrets_test")
        issues = result["issues"]
        secret_msgs = [i["message"] for i in issues]
        assert any("password" in m.lower() for m in secret_msgs)
        assert any(
            "api_key" in m.lower() or "api key" in m.lower() for m in secret_msgs
        )

    def test_review_detects_eval(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(DIRTY_FILES, "eval_test")
        msgs = [i["message"] for i in result["issues"]]
        assert any("eval" in m.lower() for m in msgs)

    def test_review_detects_bare_except(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(DIRTY_FILES, "except_test")
        msgs = [i["message"] for i in result["issues"]]
        assert any("except" in m.lower() for m in msgs)

    def test_review_detects_mutable_default(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(DIRTY_FILES, "mutable_test")
        msgs = [i["message"] for i in result["issues"]]
        assert any("default" in m.lower() for m in msgs)

    def test_review_summary_has_by_category(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(DIRTY_FILES, "summary_test")
        assert "by_category" in result["summary"]

    def test_review_summary_has_by_severity(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(DIRTY_FILES, "severity_test")
        assert "by_severity" in result["summary"]

    def test_review_summary_score(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(DIRTY_FILES, "score_test")
        assert result["summary"]["pass"] is False
        assert result["summary"]["score"] < 100

    def test_review_clean_gets_full_score(self):
        reviewer = get_code_reviewer()
        result = reviewer.review(CLEAN_FILES, "full_score")
        assert result["summary"]["pass"] is True
        assert result["summary"]["score"] == 100

    def test_get_report_existing(self):
        reviewer = get_code_reviewer()
        reviewer.review(CLEAN_FILES, "get_test")
        report = reviewer.get_report("get_test")
        assert report is not None

    def test_get_report_missing(self):
        reviewer = get_code_reviewer()
        report = reviewer.get_report("nonexistent")
        assert report is None

    def test_list_reports(self):
        reviewer = get_code_reviewer()
        reviewer.reset()
        reviewer.review(CLEAN_FILES, "proj_a")
        reviewer.review(DIRTY_FILES, "proj_b")
        reports = reviewer.list_reports()
        assert "proj_a" in reports
        assert "proj_b" in reports

    def test_reset(self):
        reviewer = get_code_reviewer()
        reviewer.review(CLEAN_FILES, "reset_test")
        reviewer.reset()
        assert reviewer.list_reports() == []

    def test_empty_list(self):
        reviewer = get_code_reviewer()
        reviewer.reset()
        assert reviewer.list_reports() == []


class TestCheckLine:
    def test_detect_secret_pattern(self):
        issues = _check_line(
            'password = "secret123"',
            1,
            "test.py",
            [("password\\s*=\\s*[\"'][^\"']+[\"']", "Hardcoded password", "use env")],
            "security",
            "critical",
        )
        assert len(issues) == 1
        assert issues[0].severity == "critical"

    def test_clean_line(self):
        issues = _check_line(
            "x = 1",
            1,
            "test.py",
            [("password\\s*=\\s*[\"'][^\"']+[\"']", "Hardcoded password", "use env")],
            "security",
            "critical",
        )
        assert len(issues) == 0


class TestReviewIssue:
    def test_defaults(self):
        issue = ReviewIssue(
            file="test.py",
            line=1,
            severity="high",
            category="security",
            message="test",
            suggestion="fix it",
        )
        assert issue.code_snippet == ""
        assert issue.file == "test.py"


class TestReviewReport:
    def test_defaults(self):
        report = ReviewReport(project_name="test")
        assert report.files_reviewed == 0
        assert report.total_issues == 0
        assert report.issues == []
