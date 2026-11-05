import shutil
import tempfile
from pathlib import Path

from orbit.orbit.core.code_integrator import (
    CodeIntegrator,
    IntegrationAction,
    IntegrationReport,
    get_code_integrator,
)


class TestCodeIntegrator:
    def setup_method(self):
        self.integrator = CodeIntegrator()
        self.tmpdir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_singleton(self):
        assert get_code_integrator() is get_code_integrator()

    def test_integrate_writes_files(self):
        files = [{"path": "src/main.py", "content": "print('hello')"}]
        result = self.integrator.integrate(files, str(self.tmpdir), "test")
        assert result["error"] is None
        assert result["successful"] == 1
        assert (self.tmpdir / "src" / "main.py").exists()
        assert (self.tmpdir / "src" / "main.py").read_text() == "print('hello')"

    def test_integrate_skip_existing(self):
        target = self.tmpdir / "sub"
        target.mkdir(exist_ok=True)
        (target / "keep.txt").write_text("original", encoding="utf-8")
        files = [{"path": "keep.txt", "content": "overwritten"}]
        result = self.integrator.integrate(
            files, str(target), "skip-test", skip_existing=True
        )
        assert result["skipped"] == 1
        assert (target / "keep.txt").read_text() == "original"

    def test_integrate_overwrite_if_not_skip(self):
        target = self.tmpdir / "sub2"
        target.mkdir(exist_ok=True)
        (target / "overwrite.txt").write_text("old", encoding="utf-8")
        files = [{"path": "overwrite.txt", "content": "new"}]
        result = self.integrator.integrate(
            files, str(target), "overwrite-test", skip_existing=False
        )
        assert result["successful"] == 1
        assert (target / "overwrite.txt").read_text() == "new"

    def test_integrate_nonexistent_dir(self):
        files = [{"path": "x.py", "content": "x"}]
        result = self.integrator.integrate(files, "/nonexistent/path", "fail")
        assert "error" in result

    def test_integrate_empty_files(self):
        result = self.integrator.integrate([], str(self.tmpdir), "empty")
        assert result["error"] is None
        assert result["total_actions"] == 0

    def test_integrate_creates_nested_dirs(self):
        files = [{"path": "a/b/c/d.py", "content": "# nested"}]
        result = self.integrator.integrate(files, str(self.tmpdir), "nested")
        assert result["successful"] == 1
        assert (self.tmpdir / "a" / "b" / "c" / "d.py").exists()

    def test_get_report_existing(self):
        files = [{"path": "hello.py", "content": "print('hi')"}]
        self.integrator.integrate(files, str(self.tmpdir), "report-me")
        report = self.integrator.get_report("report-me")
        assert report is not None
        assert report["project_name"] == "report-me"
        assert len(report["actions"]) == 1

    def test_get_report_missing(self):
        assert self.integrator.get_report("nope") is None

    def test_list_reports(self):
        assert self.integrator.list_reports() == []
        self.integrator.integrate(
            [{"path": "a.py", "content": ""}], str(self.tmpdir), "p1"
        )
        self.integrator.integrate(
            [{"path": "b.py", "content": ""}], str(self.tmpdir), "p2"
        )
        reports = self.integrator.list_reports()
        assert "p1" in reports
        assert "p2" in reports

    def test_reset(self):
        self.integrator.integrate(
            [{"path": "a.py", "content": ""}], str(self.tmpdir), "gone"
        )
        self.integrator.reset()
        assert self.integrator.list_reports() == []

    def test_save_and_load(self):
        self.integrator.integrate(
            [{"path": "saved.py", "content": "# saved"}],
            str(self.tmpdir),
            "saved-project",
        )
        p = self.tmpdir / "reports.json"
        self.integrator.save(str(p))

        fresh = CodeIntegrator()
        assert fresh.list_reports() == []
        fresh.load(str(p))
        r = fresh.get_report("saved-project")
        assert r is not None
        assert r["successful"] == 1

    def test_load_missing(self):
        fresh = CodeIntegrator()
        fresh.load(str(self.tmpdir / "nonexistent.json"))
        assert fresh.list_reports() == []

    def test_actions_have_detail(self):
        files = [{"path": "detailed.py", "content": "ok"}]
        result = self.integrator.integrate(files, str(self.tmpdir), "details")
        action = result["actions"][0]
        assert action["detail"] != ""

    def test_multiple_files(self):
        files = [
            {"path": "mod1.py", "content": "a"},
            {"path": "mod2.py", "content": "b"},
        ]
        result = self.integrator.integrate(files, str(self.tmpdir), "multi")
        assert result["successful"] == 2
        assert (self.tmpdir / "mod1.py").exists()
        assert (self.tmpdir / "mod2.py").exists()

    def test_error_on_nonexistent_base_dir(self):
        result = self.integrator.integrate(
            [{"path": "f.py", "content": ""}],
            str(self.tmpdir / "not-here"),
            "bad-dir",
        )
        assert "error" in result

    def test_skipped_count(self):
        (self.tmpdir / "existing.py").write_text("original", encoding="utf-8")
        result = self.integrator.integrate(
            [
                {"path": "existing.py", "content": "new"},
                {"path": "new.py", "content": "new"},
            ],
            str(self.tmpdir),
            "skipped-test",
        )
        assert result["skipped"] == 1
        assert result["successful"] == 1


class TestIntegrationReport:
    def test_defaults(self):
        r = IntegrationReport()
        assert r.project_name == ""
        assert r.actions == []
        assert r.error is None

    def test_actions_tracking(self):
        r = IntegrationReport(project_name="p")
        r.actions.append(
            IntegrationAction(file="f.py", action="write", status="completed")
        )
        assert len(r.actions) == 1
        assert r.actions[0].file == "f.py"
