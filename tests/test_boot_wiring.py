"""
Boot wiring tests (Phase A — Task 4)
=====================================
Covers the newly wired 18-step StartupSequence:
- run_startup() writes a boot_*.json report
- ORBIT_SKIP_STARTUP guard skips the sequence in start_server()
- /api/boot/latest serves the panel-shaped schema via the adapter
- A failing boot step logs and continues (never raises out of start_server)

Run: python -m pytest tests/test_boot_wiring.py -v
"""

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import startup as startup_module
from orbit.orbit.core.boot_report import adapt_startup_report, get_boot_report
from orbit.orbit.core.startup import StartupSequence


def _make_report() -> dict:
    """A minimal startup-style report matching StartupSequence output."""
    return {
        "timestamp": "2026-08-02T10:00:00.000000",
        "elapsed_ms": 123.4,
        "boot_message": "Sir, ORBIT boot completed.",
        "summary": {
            "total": 18,
            "passed": 17,
            "failed": 1,
            "skipped": 0,
            "ready": False,
        },
        "steps": [
            {
                "name": "Config Validation",
                "status": "pass",
                "latency_ms": 1.0,
                "message": "Config loaded successfully",
                "required": True,
            },
            {
                "name": "Agent Registry",
                "status": "fail",
                "latency_ms": 2.0,
                "message": "No module named 'requests'",
                "required": True,
            },
            {
                "name": "Self-Test",
                "status": "skip",
                "latency_ms": 0.5,
                "message": "No previous self-test found",
                "required": False,
            },
        ],
    }


class TestStartupSequenceReport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_run_startup_writes_report_file(self):
        seq = StartupSequence()
        with mock.patch.object(seq, "_check_ollama_alive", return_value=True):
            report = seq.run_startup()
        self.assertEqual(report["summary"]["total"], 18)
        self.assertIn("timestamp", report)
        self.assertIn("steps", report)

    def test_run_startup_real_write_creates_json(self):
        with mock.patch.object(startup_module, "DATA_DIR", Path(self._tmp.name)):
            seq = StartupSequence()
            with mock.patch.object(seq, "_check_ollama_alive", return_value=True):
                report = seq.run_startup()
            files = list(Path(self._tmp.name).glob("boot_*.json"))
            self.assertEqual(len(files), 1)
            data = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(data["timestamp"], report["timestamp"])

    def test_ollama_step_degraded_to_skip_on_failure(self):
        seq = StartupSequence()
        with (
            mock.patch.object(seq, "_check_ollama_alive", return_value=False),
            mock.patch("subprocess.Popen", side_effect=FileNotFoundError),
        ):
            step = seq._step_ollama_auto_start()
        self.assertEqual(step.status, "skip")
        self.assertIn("fallback", step.message.lower())


class TestAdaptStartupReport(unittest.TestCase):
    def test_adapter_maps_panel_schema(self):
        adapted = adapt_startup_report(_make_report())
        self.assertEqual(adapted["status"], "partial")  # 1 failed step
        self.assertEqual(adapted["modules_count"], 3)
        self.assertEqual(
            sorted(adapted["modules_loaded"]), ["Config Validation", "Self-Test"]
        )
        self.assertEqual(len(adapted["errors"]), 1)
        self.assertIn("Agent Registry", adapted["errors"][0])
        self.assertEqual(adapted["source"], "startup")
        # timing values are seconds (floats)
        self.assertAlmostEqual(adapted["timing"]["Config Validation"], 0.001)

    def test_adapter_empty_returns_none(self):
        self.assertIsNone(adapt_startup_report(None))
        self.assertIsNone(adapt_startup_report({}))

    def test_adapter_success_status_when_ready(self):
        report = _make_report()
        report["summary"]["ready"] = True
        report["summary"]["failed"] = 0
        report["steps"] = [s for s in report["steps"] if s["status"] != "fail"]
        adapted = adapt_startup_report(report)
        self.assertEqual(adapted["status"], "success")
        self.assertEqual(adapted["errors"], [])


class TestBootReportBlueprint(unittest.TestCase):
    def _app(self):
        from flask import Flask

        from orbit.orbit.core.boot_report_bp import boot_report_bp

        app = Flask(__name__)
        app.register_blueprint(boot_report_bp)
        return app

    def test_latest_serves_startup_report_when_boot_report_empty(self):
        app = self._app()
        with (
            mock.patch.object(
                get_boot_report(), "get_latest_report", return_value=None
            ),
            mock.patch("orbit.orbit.core.boot_report_bp.get_startup") as m_startup,
        ):
            m_startup.return_value.get_latest.return_value = _make_report()
            resp = app.test_client().get("/api/boot/latest")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "partial")
        self.assertEqual(data["modules_count"], 3)
        self.assertEqual(data["source"], "startup")

    def test_latest_404_when_nothing_available(self):
        app = self._app()
        with (
            mock.patch.object(
                get_boot_report(), "get_latest_report", return_value=None
            ),
            mock.patch("orbit.orbit.core.boot_report_bp.get_startup") as m_startup,
        ):
            m_startup.return_value.get_latest.return_value = None
            resp = app.test_client().get("/api/boot/latest")
        self.assertEqual(resp.status_code, 404)

    def test_history_serves_adapted_startup(self):
        app = self._app()
        with (
            mock.patch.object(get_boot_report(), "get_history", return_value=[]),
            mock.patch("orbit.orbit.core.boot_report_bp.get_startup") as m_startup,
        ):
            m_startup.return_value.get_history.return_value = [_make_report()]
            resp = app.test_client().get("/api/boot/history?limit=1")
        self.assertEqual(resp.status_code, 200)
        history = resp.get_json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["source"], "startup")


class TestLaunchDesktopGuard(unittest.TestCase):
    """run_startup_sequence imports `orbit.orbit.core.startup` INSIDE the
    function (matching launch_desktop's runtime sys.path layout), so we inject
    a fake `orbit.orbit.core.startup` module via sys.modules to control the
    import."""

    def _inject_fake_startup(self, run_side_effect=None, get_latest=None):
        get_startup = mock.Mock()
        seq = mock.Mock()
        seq.run_startup.side_effect = run_side_effect
        get_startup.return_value = seq
        startup_mod = types.ModuleType("orbit.orbit.core.startup")
        startup_mod.get_startup = get_startup
        core_pkg = types.ModuleType("orbit.orbit.core")
        core_pkg.__path__ = []
        saved = {}
        for name in ("orbit.orbit.core", "orbit.orbit.core.startup"):
            saved[name] = sys.modules.get(name)
        sys.modules["orbit.orbit.core"] = core_pkg
        sys.modules["orbit.orbit.core.startup"] = startup_mod
        return get_startup, saved

    def _restore(self, saved):
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_skip_env_guard(self):
        import orbit.launch_desktop as ld

        get_startup, saved = self._inject_fake_startup()
        try:
            with mock.patch.dict(os.environ, {"ORBIT_SKIP_STARTUP": "1"}, clear=False):
                ld.run_startup_sequence()
                get_startup.assert_not_called()
        finally:
            self._restore(saved)

    def test_run_sequence_does_not_raise_on_failure(self):
        import orbit.launch_desktop as ld

        _, saved = self._inject_fake_startup(run_side_effect=RuntimeError("boom"))
        try:
            with mock.patch.dict(os.environ, {}, clear=False):
                ld.run_startup_sequence()  # must not raise
        finally:
            self._restore(saved)

    def test_run_sequence_reports_completed_summary(self):
        import orbit.launch_desktop as ld

        get_startup, saved = self._inject_fake_startup()
        get_startup.return_value.run_startup.return_value = {
            "elapsed_ms": 42.0,
            "boot_message": "Sir, ORBIT boot completed.",
            "summary": {
                "total": 18,
                "passed": 18,
                "failed": 0,
                "skipped": 0,
                "ready": True,
            },
        }
        try:
            with mock.patch.dict(os.environ, {}, clear=False):
                ld.run_startup_sequence()  # must not raise
                get_startup.assert_called_once()
        finally:
            self._restore(saved)


if __name__ == "__main__":
    unittest.main()
