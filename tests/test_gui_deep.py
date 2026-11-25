"""Deep tests for orbit/gui.py — desktop re-export shim (Loop 10/1).

6 statements. Proves:
  * gui re-exports ``orbit.launch_desktop.main`` exactly (identity check).
  * gui exposes NO ``MainWindow`` class — ``orbit/__main__.py`` used to do
    ``from orbit.gui import MainWindow`` which always raised ImportError
    (fixed in this loop); this test pins the contract so a regression in
    either direction is caught.
  * running the module as a script (``python -m orbit.gui``) actually calls
    the desktop launcher.
"""

import runpy
import sys
import unittest
from unittest import mock

import orbit.gui as gui


class GuiExportTests(unittest.TestCase):
    def test_launch_desktop_is_desktop_main(self):
        from orbit.launch_desktop import main as desktop_main

        self.assertIs(gui.launch_desktop, desktop_main)
        self.assertTrue(callable(gui.launch_desktop))

    def test_public_names_are_restricted(self):
        # only the re-exported launcher is public; os/sys are imports
        self.assertTrue(hasattr(gui, "launch_desktop"))
        self.assertTrue(hasattr(gui, "os"))
        self.assertTrue(hasattr(gui, "sys"))

    def test_no_mainwindow_attribute(self):
        # regression pin for __main__.py's broken `from orbit.gui import
        # MainWindow` — gui never had a window class
        self.assertFalse(hasattr(gui, "MainWindow"))

    def test_dir_matches_imports(self):
        names = set(dir(gui))
        self.assertIn("launch_desktop", names)
        self.assertNotIn("MainWindow", names)


class GuiScriptModeTests(unittest.TestCase):
    def test_run_as_main_invokes_launcher(self):
        saved_path = list(sys.path)
        try:
            with mock.patch("orbit.launch_desktop.main") as launcher:
                runpy.run_module("orbit.gui", run_name="__main__")
            launcher.assert_called_once_with()
        finally:
            sys.path[:] = saved_path

    def test_run_as_main_does_not_fire_when_imported(self):
        # plain import must not launch the GUI (the ``if __name__`` guard)
        with mock.patch("orbit.launch_desktop.main") as launcher:
            import importlib

            importlib.reload(gui)
        launcher.assert_not_called()


if __name__ == "__main__":
    unittest.main()
