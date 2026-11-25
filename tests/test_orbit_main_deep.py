"""Deep tests for orbit/__main__.py — package entry point (Loop 10/4).

Covers:
  * module bootstrap: repo-root sys.path insert, .env loading, and the
    dotenv-missing ``except ImportError`` fallback.
  * ``--help`` / ``-h`` banner (and help winning over other flags).
  * ``--diagnostics`` dispatch to startup_diagnostics.main.
  * ``--server`` mode: port/host parsing (valid, invalid, blank), env
    side effects (ORBIT_SKIP_STARTUP) and app.run kwargs.
  * default GUI branch — pinned to the **Bug #1 fix**: main() now calls
    ``orbit.gui.launch_desktop``. The old code did
    ``from orbit.gui import MainWindow`` which always raised ImportError
    (no such class exists), so ``python -m orbit`` silently degraded to
    Flask mode even with PyQt5 installed.
  * ImportError fallback to Flask (its own port/host parsing too).
  * the ``__main__`` guard via ``runpy.run_module("orbit")``.
"""

import contextlib
import importlib
import io
import os
import runpy
import sys
import unittest
from unittest import mock

import orbit.gui as gui
import orbit.__main__ as om


@contextlib.contextmanager
def _without_gui_launcher():
    """Hide gui.launch_desktop so ``from orbit.gui import launch_desktop``
    raises ImportError (same symptom as PyQt5 not being installed)."""
    saved = gui.launch_desktop
    del gui.launch_desktop
    try:
        yield
    finally:
        gui.launch_desktop = saved


class _MainRunner(unittest.TestCase):
    """Helpers: run main() with patched argv + captured stdout."""

    def _run(self, *argv):
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["orbit", *argv]), \
                contextlib.redirect_stdout(buf), \
                mock.patch("orbit.gui.launch_desktop") as gui_launcher, \
                mock.patch("orbit.orbit.server.create_app") as create_app, \
                mock.patch.dict(os.environ, {}, clear=False):
            for key in ("ORBIT_PORT", "ORBIT_HOST", "ORBIT_SKIP_STARTUP"):
                os.environ.pop(key, None)
            result = om.main()
        return result, buf.getvalue(), gui_launcher, create_app


class HelpTests(_MainRunner):
    def test_help_flag(self):
        result, out, gui_l, create = self._run("--help")
        self.assertIsNone(result)
        self.assertIn("ORBIT — AI Operating System", out)
        self.assertIn("The Demons Army", out)
        self.assertIn("python -m orbit --server", out)
        self.assertIn("python -m orbit --help", out)
        self.assertIn("copy .env.example to .env", out)
        gui_l.assert_not_called()
        create.assert_not_called()

    def test_short_help_flag(self):
        result, out, _, create = self._run("-h")
        self.assertIsNone(result)
        self.assertIn("Usage:", out)
        create.assert_not_called()

    def test_help_wins_over_other_flags(self):
        result, out, gui_l, create = self._run("--server", "--help")
        self.assertIsNone(result)
        self.assertIn("Usage:", out)
        gui_l.assert_not_called()
        create.assert_not_called()


class DiagnosticsTests(_MainRunner):
    def test_diagnostics_dispatch(self):
        with mock.patch(
                "orbit.orbit.core.startup_diagnostics.main") as diag:
            result, out, gui_l, create = self._run("--diagnostics")
        diag.assert_called_once_with()
        self.assertIsNone(result)
        gui_l.assert_not_called()
        create.assert_not_called()


class ServerModeTests(_MainRunner):
    def _run_server(self, env: dict):
        fake_app = mock.MagicMock()
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["orbit", "--server"]), \
                mock.patch("orbit.orbit.server.create_app",
                           return_value=fake_app) as create, \
                mock.patch("orbit.gui.launch_desktop") as gui_l, \
                mock.patch.dict(os.environ, env, clear=False), \
                contextlib.redirect_stdout(buf):
            for key in ("ORBIT_PORT", "ORBIT_HOST", "ORBIT_SKIP_STARTUP"):
                if key not in env:
                    os.environ.pop(key, None)
            om.main()
        return fake_app, create, gui_l, buf.getvalue()

    def test_custom_host_and_port(self):
        app, create, gui_l, out = self._run_server(
            {"ORBIT_PORT": "8080", "ORBIT_HOST": "0.0.0.0"})
        create.assert_called_once_with()
        app.run.assert_called_once_with(host="0.0.0.0", port=8080,
                                        debug=False)
        gui_l.assert_not_called()
        self.assertIn("http://0.0.0.0:8080", out)

    def test_skip_startup_env_set(self):
        # patch.dict restores it after the call; assert inside via side effect
        seen = {}

        def _grab(*a, **k):
            seen["skip"] = os.environ.get("ORBIT_SKIP_STARTUP")
            seen["port"] = k

        with mock.patch.object(sys, "argv", ["orbit", "--server"]), \
                mock.patch("orbit.orbit.server.create_app") as create, \
                mock.patch("orbit.gui.launch_desktop"), \
                mock.patch.dict(os.environ, {}, clear=False), \
                contextlib.redirect_stdout(io.StringIO()):
            for key in ("ORBIT_PORT", "ORBIT_HOST", "ORBIT_SKIP_STARTUP"):
                os.environ.pop(key, None)
            create.return_value.run.side_effect = _grab
            om.main()
        self.assertEqual(seen["skip"], "1")

    def test_defaults_when_env_absent(self):
        app, _, _, out = self._run_server({})
        app.run.assert_called_once_with(host="127.0.0.1", port=5000,
                                        debug=False)
        self.assertIn("http://127.0.0.1:5000", out)

    def test_invalid_port_falls_back(self):
        app, _, _, _ = self._run_server({"ORBIT_PORT": "not-a-port"})
        app.run.assert_called_once_with(host="127.0.0.1", port=5000,
                                        debug=False)

    def test_float_like_port_falls_back(self):
        app, _, _, _ = self._run_server({"ORBIT_PORT": "5000.5"})
        app.run.assert_called_once_with(host="127.0.0.1", port=5000,
                                        debug=False)

    def test_blank_host_falls_back(self):
        app, _, _, _ = self._run_server({"ORBIT_HOST": "   "})
        app.run.assert_called_once_with(host="127.0.0.1", port=5000,
                                        debug=False)

    def test_host_is_stripped(self):
        app, _, _, out = self._run_server({"ORBIT_HOST": "  10.0.0.7  ",
                                           "ORBIT_PORT": "9000"})
        app.run.assert_called_once_with(host="10.0.0.7", port=9000,
                                        debug=False)
        self.assertIn("http://10.0.0.7:9000", out)


class GuiDefaultBranchTests(_MainRunner):
    def test_default_launches_desktop_gui(self):
        # Bug #1 regression pin: main() must call orbit.gui.launch_desktop
        # (the old `from orbit.gui import MainWindow` always ImportError-ed)
        result, out, gui_l, create = self._run()
        gui_l.assert_called_once_with()
        create.assert_not_called()
        self.assertIsNone(result)
        self.assertEqual(out, "")

    def test_gui_importerror_falls_back_to_flask(self):
        # simulate missing GUI (e.g. PyQt5 not installed): the launcher
        # name is unavailable -> except ImportError -> Flask mode
        fake_app = mock.MagicMock()
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["orbit"]), \
                _without_gui_launcher(), \
                mock.patch("orbit.orbit.server.create_app",
                           return_value=fake_app), \
                mock.patch.dict(os.environ, {}, clear=False), \
                contextlib.redirect_stdout(buf):
            for key in ("ORBIT_PORT", "ORBIT_HOST"):
                os.environ.pop(key, None)
            om.main()
        out = buf.getvalue()
        self.assertIn("PyQt5 not installed", out)
        self.assertIn("Falling back to Flask server mode", out)
        fake_app.run.assert_called_once_with(host="127.0.0.1", port=5000,
                                             debug=False)

    def test_fallback_parses_bad_port_and_blank_host(self):
        fake_app = mock.MagicMock()
        with mock.patch.object(sys, "argv", ["orbit"]), \
                _without_gui_launcher(), \
                mock.patch("orbit.orbit.server.create_app",
                           return_value=fake_app), \
                mock.patch.dict(os.environ, {"ORBIT_PORT": "xyz",
                                             "ORBIT_HOST": "  "}), \
                contextlib.redirect_stdout(io.StringIO()):
            om.main()
        fake_app.run.assert_called_once_with(host="127.0.0.1", port=5000,
                                             debug=False)

    def test_fallback_strips_host(self):
        fake_app = mock.MagicMock()
        with mock.patch.object(sys, "argv", ["orbit"]), \
                _without_gui_launcher(), \
                mock.patch("orbit.orbit.server.create_app",
                           return_value=fake_app), \
                mock.patch.dict(os.environ, {"ORBIT_HOST": " 0.0.0.0 ",
                                             "ORBIT_PORT": "7777"}), \
                contextlib.redirect_stdout(io.StringIO()):
            om.main()
        fake_app.run.assert_called_once_with(host="0.0.0.0", port=7777,
                                             debug=False)


class BootstrapTests(unittest.TestCase):
    """Module-level sys.path / dotenv handling."""

    def test_repo_root_is_on_sys_path(self):
        self.assertIn(om._repo, sys.path)
        expected = os.path.dirname(
            os.path.dirname(os.path.abspath(om.__file__)))
        self.assertEqual(om._repo, expected)

    def test_sys_path_insert_runs_when_missing(self):
        saved = list(sys.path)
        try:
            sys.path[:] = [p for p in sys.path if p != om._repo]
            self.assertNotIn(om._repo, sys.path)
            with mock.patch("dotenv.load_dotenv") as ld:
                importlib.reload(om)
            self.assertIn(om._repo, sys.path)
            ld.assert_called_once_with(os.path.join(om._repo, ".env"))
        finally:
            sys.path[:] = saved
            with mock.patch("dotenv.load_dotenv"):
                importlib.reload(om)

    def test_missing_dotenv_is_tolerated(self):
        # sys.modules[name] = None forces ImportError on import
        with mock.patch.dict(sys.modules, {"dotenv": None}):
            importlib.reload(om)  # must not raise
        self.assertTrue(callable(om.main))


class RunpyTests(unittest.TestCase):
    def test_python_m_orbit_runs_main(self):
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["orbit", "--help"]), \
                mock.patch("dotenv.load_dotenv"), \
                contextlib.redirect_stdout(buf):
            runpy.run_module("orbit", run_name="__main__")
        out = buf.getvalue()
        self.assertIn("ORBIT — AI Operating System", out)
        self.assertIn("python -m orbit --help", out)


if __name__ == "__main__":
    unittest.main()
