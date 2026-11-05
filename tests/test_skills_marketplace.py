"""Tests for ORBIT Skills Marketplace.

Verifies the plugin path-traversal guard and that `install` produces a
runnable skill (matching builtin behavior) instead of a dead entry.
"""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from orbit.orbit.core import skills_marketplace as kb

MODULE = kb


class TestSkillsMarketplace(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plugins = self.tmp / "plugins"
        self._patchers = [
            unittest.mock.patch.object(MODULE, "PLUGINS_DIR", self.plugins),
            unittest.mock.patch.object(
                MODULE, "REGISTRY_PATH", self.plugins / "registry.json"
            ),
        ]
        for p in self._patchers:
            p.start()
        self.sm = kb.SkillsMarketplace()

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def test_path_traversal_rejected_on_install(self):
        res = self.sm.install("evil", filename="../../escape.py")
        self.assertIn("error", res)
        # Nothing registered, and no file written outside the plugins dir.
        self.assertNotIn("evil", {s["id"] for s in self.sm.list_skills()})
        self.assertFalse((self.tmp / "escape.py").exists())

    def test_install_creates_runnable_stub(self):
        res = self.sm.install("my_skill", name="My Skill", description="does things")
        self.assertEqual(res["status"], "ok")
        # Builtin-like: running it returns a ready status, not "file not found".
        out = self.sm.run_skill("my_skill")
        self.assertEqual(out.get("status"), "ready")
        self.assertEqual(out.get("skill"), "my_skill")

    def test_uninstall_removes_file_and_entry(self):
        self.sm.install("my_skill", name="My Skill")
        self.assertTrue(self.sm.uninstall("my_skill"))
        self.assertIsNone(self.sm.get_skill("my_skill"))
        self.assertFalse((self.plugins / "my_skill.py").exists())

    def test_run_disabled_skill_errors(self):
        self.sm.install("my_skill", name="My Skill")
        self.sm.toggle("my_skill")  # disable
        out = self.sm.run_skill("my_skill")
        self.assertIn("error", out)

    def test_run_unknown_skill_errors(self):
        self.assertIn("error", self.sm.run_skill("nope"))

    def test_builtin_skills_present_and_runnable(self):
        ids = {s["id"] for s in self.sm.list_skills()}
        self.assertIn("web_scraper", ids)
        out = self.sm.run_skill("web_scraper")
        self.assertEqual(out.get("status"), "ready")

    def test_get_categories(self):
        self.sm.install("cat1", category="vision")
        cats = self.sm.get_categories()
        self.assertGreaterEqual(cats.get("vision", 0), 1)


if __name__ == "__main__":
    unittest.main()
