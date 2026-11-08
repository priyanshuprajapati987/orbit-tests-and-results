"""Unit tests for orbit/orbit/core/dead_hand_destroy.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.dead_hand_destroy import execute_destroy, CONFIRM_PHRASE


class TestExecuteDestroy(unittest.TestCase):
    def test_not_frozen(self):
        with patch("orbit.core.runtime_paths.is_frozen", return_value=False):
            r = execute_destroy(confirm=CONFIRM_PHRASE)
        self.assertFalse(r["ok"])
        self.assertIn("frozen build", r["error"])

    def test_missing_env_gate(self):
        with patch("orbit.core.runtime_paths.is_frozen", return_value=True), \
             patch.dict(os.environ, {"ORBIT_ALLOW_DESTROY": "0"}, clear=False):
            os.environ.pop("ORBIT_ALLOW_DESTROY", None)
            r = execute_destroy(confirm=CONFIRM_PHRASE)
        self.assertFalse(r["ok"])
        self.assertIn("ORBIT_ALLOW_DESTROY", r["error"])

    def test_env_gate_true(self):
        # just ensure gate passes when env set
        with patch("orbit.core.runtime_paths.is_frozen", return_value=True), \
             patch.dict(os.environ, {"ORBIT_ALLOW_DESTROY": "1"}):
            with patch("orbit.core.dead_hand.get_dead_hand", side_effect=RuntimeError("no dh")):
                with patch("orbit.core.dead_hand._iter_code_files", return_value=[]):
                    r = execute_destroy(confirm=CONFIRM_PHRASE)
        self.assertTrue(r["ok"])

    def test_confirm_mismatch(self):
        with patch("orbit.core.runtime_paths.is_frozen", return_value=True), \
             patch.dict(os.environ, {"ORBIT_ALLOW_DESTROY": "1"}):
            r = execute_destroy(confirm="wrong phrase")
        self.assertFalse(r["ok"])
        self.assertIn("confirm phrase", r["error"])

    def test_confirm_default_empty(self):
        with patch("orbit.core.runtime_paths.is_frozen", return_value=True), \
             patch.dict(os.environ, {"ORBIT_ALLOW_DESTROY": "1"}):
            r = execute_destroy()
        self.assertFalse(r["ok"])
        self.assertIn("confirm phrase", r["error"])

    def test_destroy_with_code_root(self):
        p1 = MagicMock()
        p2 = MagicMock()
        p2.unlink.side_effect = OSError("locked")
        p2.with_suffix.return_value = Path("/tmp/b.py.dead")
        with patch("orbit.core.runtime_paths.is_frozen", return_value=True), \
             patch.dict(os.environ, {"ORBIT_ALLOW_DESTROY": "1"}), \
             patch("orbit.core.dead_hand.get_dead_hand", side_effect=RuntimeError("no dh")), \
             patch("orbit.core.dead_hand._iter_code_files", return_value=[p1, p2]):
            r = execute_destroy(confirm=CONFIRM_PHRASE, code_root="/tmp/root")
        self.assertTrue(r["ok"])
        self.assertEqual(r["deleted"], 2)  # p1 unlinked + p2 renamed
        self.assertEqual(r["failed"], 0)
        self.assertEqual(r["code_root"], str(Path("/tmp/root")))
        p1.unlink.assert_called_once()
        p2.rename.assert_called_once()

    def test_destroy_audit_called(self):
        audit = MagicMock()
        with patch("orbit.core.runtime_paths.is_frozen", return_value=True), \
             patch.dict(os.environ, {"ORBIT_ALLOW_DESTROY": "1"}), \
             patch("orbit.core.dead_hand.get_dead_hand", return_value=audit), \
             patch("orbit.core.dead_hand._iter_code_files", return_value=[]):
            r = execute_destroy(confirm=CONFIRM_PHRASE, reason="test reason")
        self.assertTrue(r["ok"])
        # audit called at least for "executing" and "complete"
        self.assertGreaterEqual(audit._audit_op.call_count, 2)

    def test_destroy_uses_repo_root_when_not_frozen_path(self):
        # is_frozen True but code_root None → app_root() (since is_frozen() True branch)
        with patch("orbit.core.runtime_paths.is_frozen", return_value=True), \
             patch("orbit.core.runtime_paths.app_root", return_value=Path("/app")), \
             patch.dict(os.environ, {"ORBIT_ALLOW_DESTROY": "1"}), \
             patch("orbit.core.dead_hand.get_dead_hand", side_effect=RuntimeError("x")), \
             patch("orbit.core.dead_hand._iter_code_files", return_value=[]):
            r = execute_destroy(confirm=CONFIRM_PHRASE)
        self.assertTrue(r["ok"])
        self.assertEqual(r["code_root"], str(Path("/app")))

    def test_constant(self):
        self.assertEqual(CONFIRM_PHRASE, "DESTROY ORBIT CODE")


if __name__ == "__main__":
    unittest.main()
