"""Unit tests for orbit/orbit/core/context_menu.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.context_menu as cm_mod
from orbit.core.context_menu import (
    ContextMenu,
    get_context_menu,
    CONTEXT_TYPES,
    ACTIONS_BY_CONTEXT,
)


class ContextMenuTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._old_data_dir = cm_mod.DATA_DIR
        cm_mod.DATA_DIR = self.tmp

    def tearDown(self):
        cm_mod.DATA_DIR = self._old_data_dir


class TestConstants(unittest.TestCase):
    def test_context_types(self):
        self.assertEqual(CONTEXT_TYPES, ["text", "code", "image", "file"])

    def test_all_contexts_have_actions(self):
        for ct in CONTEXT_TYPES:
            self.assertIn(ct, ACTIONS_BY_CONTEXT)
            self.assertGreater(len(ACTIONS_BY_CONTEXT[ct]), 0)

    def test_action_entries_shape(self):
        for ct, actions in ACTIONS_BY_CONTEXT.items():
            for a in actions:
                self.assertIn("id", a, ct)
                self.assertIn("label", a, ct)
                self.assertIn("description", a, ct)


class TestGetActions(ContextMenuTestBase):
    def setUp(self):
        super().setUp()
        self.cm = ContextMenu()

    def test_text_actions(self):
        ids = [a["id"] for a in self.cm.get_actions("text")]
        self.assertIn("summarize", ids)
        self.assertIn("translate", ids)
        self.assertIn("improve", ids)
        self.assertIn("analyze", ids)

    def test_code_actions(self):
        ids = [a["id"] for a in self.cm.get_actions("code")]
        self.assertIn("debug", ids)
        self.assertIn("explain", ids)
        self.assertIn("optimize", ids)

    def test_image_actions(self):
        ids = [a["id"] for a in self.cm.get_actions("image")]
        self.assertIn("extract_text", ids)
        self.assertIn("analyze", ids)

    def test_file_actions(self):
        ids = [a["id"] for a in self.cm.get_actions("file")]
        self.assertIn("summarize", ids)

    def test_unknown_context_empty(self):
        self.assertEqual(self.cm.get_actions("unknown"), [])
        self.assertEqual(self.cm.get_actions(""), [])


class TestExecuteAction(ContextMenuTestBase):
    def setUp(self):
        super().setUp()
        self.cm = ContextMenu()

    def test_execute_summarize_text(self):
        r = self.cm.execute_action("summarize", "hello world", "text")
        self.assertEqual(r["action_id"], "summarize")
        self.assertEqual(r["context"], "text")
        self.assertEqual(r["status"], "executed")
        self.assertIn("timestamp", r)
        self.assertIn("result", r)
        self.assertIn("11 chars", r["result"])

    def test_execute_invalid_action(self):
        r = self.cm.execute_action("nope", "content", "text")
        self.assertIn("error", r)
        self.assertIn("not available", r["error"])

    def test_execute_wrong_context(self):
        # summarize not in code actions
        r = self.cm.execute_action("summarize", "x", "code")
        self.assertIn("error", r)

    def test_execute_unknown_context(self):
        r = self.cm.execute_action("summarize", "x", "bogus")
        self.assertIn("error", r)

    def test_content_preview_truncated(self):
        content = "x" * 500
        r = self.cm.execute_action("summarize", content, "text")
        self.assertEqual(len(r["content_preview"]), 100)

    def test_content_preview_short(self):
        r = self.cm.execute_action("summarize", "short", "text")
        self.assertEqual(r["content_preview"], "short")

    def test_history_appended(self):
        self.cm.execute_action("summarize", "a", "text")
        self.cm.execute_action("translate", "b", "text")
        self.assertEqual(len(self.cm._history), 2)

    def test_history_persisted(self):
        self.cm.execute_action("summarize", "a", "text")
        p = self.tmp / "action_history.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 1)

    def test_execute_code_debug(self):
        r = self.cm.execute_action("debug", "print(1)", "code")
        self.assertEqual(r["status"], "executed")
        self.assertEqual(r["content_preview"], "print(1)")


class TestSaveLoad(ContextMenuTestBase):
    def test_save_truncates_to_500(self):
        cm = ContextMenu()
        cm._history = [{"i": i} for i in range(600)]
        cm._save()
        p = self.tmp / "action_history.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 500)
        self.assertEqual(data[0]["i"], 100)  # first 100 dropped

    def test_save_atomic_no_tmp(self):
        cm = ContextMenu()
        cm._history = [{"a": 1}]
        cm._save()
        self.assertFalse((self.tmp / "action_history.json.tmp").exists())

    def test_load_existing(self):
        p = self.tmp / "action_history.json"
        p.write_text(json.dumps([{"x": 1}]), encoding="utf-8")
        cm = ContextMenu()
        self.assertEqual(cm._history, [{"x": 1}])

    def test_load_corrupt(self):
        p = self.tmp / "action_history.json"
        p.write_text("not-json", encoding="utf-8")
        cm = ContextMenu()
        self.assertEqual(cm._history, [])

    def test_load_no_file(self):
        cm = ContextMenu()
        self.assertEqual(cm._history, [])

    def test_path_location(self):
        cm = ContextMenu()
        self.assertEqual(cm._path(), self.tmp / "action_history.json")


class TestGetContextMenu(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_context_menu(), get_context_menu())

    def test_type(self):
        self.assertIsInstance(get_context_menu(), ContextMenu)


if __name__ == "__main__":
    unittest.main()
