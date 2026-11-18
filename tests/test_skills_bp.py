"""Unit tests for orbit/orbit/core/skills_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.skills_bp import skills_bp


class SkillsBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(skills_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(skills_bp.name, "skills")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/skills", "/api/skills/categories", "/api/skills/install",
                  "/api/skills/crystallize", "/api/skills/recall",
                  "/api/skills/<skill_id>", "/api/skills/<skill_id>/toggle",
                  "/api/skills/<skill_id>/run"]:
            self.assertIn(p, rules)


class TestListSkills(SkillsBpBase):
    def test_list(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.list_skills.return_value = [{"id": "s1"}]
            r = self.client.get("/api/skills")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["skills"], [{"id": "s1"}])

    def test_list_empty(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.list_skills.return_value = []
            r = self.client.get("/api/skills")
        self.assertEqual(r.get_json()["skills"], [])


class TestCategories(SkillsBpBase):
    def test_categories(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.get_categories.return_value = {"categories": ["a", "b"]}
            r = self.client.get("/api/skills/categories")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"categories": ["a", "b"]})


class TestInstall(SkillsBpBase):
    def test_install_success(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.install.return_value = {"ok": True}
            r = self.client.post("/api/skills/install", json={"id": "s1", "name": "Skill"})
        self.assertEqual(r.status_code, 200)
        gm.return_value.install.assert_called_once_with(
            "s1", name="Skill", description="", version="1.0.0",
            author="user", category="general", filename="",
        )

    def test_install_missing_id_400(self):
        r = self.client.post("/api/skills/install", json={"name": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_install_no_body_400(self):
        r = self.client.post("/api/skills/install")
        self.assertEqual(r.status_code, 400)

    def test_install_all_fields(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.install.return_value = {"ok": True}
            r = self.client.post("/api/skills/install", json={
                "id": "s1", "name": "N", "description": "D", "version": "2.0.0",
                "author": "me", "category": "tools", "filename": "f.py",
            })
        self.assertEqual(r.status_code, 200)
        gm.return_value.install.assert_called_once_with(
            "s1", name="N", description="D", version="2.0.0",
            author="me", category="tools", filename="f.py",
        )


class TestToggle(SkillsBpBase):
    def test_toggle_enabled(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.toggle.return_value = True
            r = self.client.post("/api/skills/s1/toggle")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok", "enabled": True})

    def test_toggle_disabled(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.toggle.return_value = False
            r = self.client.post("/api/skills/s1/toggle")
        self.assertEqual(r.get_json()["enabled"], False)

    def test_toggle_not_found_404(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.toggle.return_value = None
            r = self.client.post("/api/skills/nope/toggle")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Not found")


class TestUninstall(SkillsBpBase):
    def test_uninstall_ok(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.uninstall.return_value = True
            r = self.client.delete("/api/skills/s1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

    def test_uninstall_not_found_404(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.uninstall.return_value = False
            r = self.client.delete("/api/skills/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Not found")


class TestRunSkill(SkillsBpBase):
    def test_run_success(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.run_skill.return_value = {"output": "done"}
            r = self.client.post("/api/skills/s1/run", json={"arg": 1})
        self.assertEqual(r.status_code, 200)
        gm.return_value.run_skill.assert_called_once_with("s1", arg=1)

    def test_run_no_body(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.run_skill.return_value = {"output": "x"}
            r = self.client.post("/api/skills/s1/run")
        self.assertEqual(r.status_code, 200)
        gm.return_value.run_skill.assert_called_once_with("s1")

    def test_run_exception_500(self):
        with patch("orbit.core.skills_bp.get_skills_marketplace") as gm:
            gm.return_value.run_skill.side_effect = RuntimeError("boom")
            r = self.client.post("/api/skills/s1/run", json={})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


class TestCrystallize(SkillsBpBase):
    def test_crystallize_success(self):
        skill = MagicMock()
        skill.id = "sk1"
        skill.name = "My Skill"
        with patch("orbit.skill_library.get_skill_library") as gl:
            gl.return_value.crystallize.return_value = skill
            r = self.client.post("/api/skills/crystallize", json={"task": "do X"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "crystallized")
        self.assertEqual(body["skill_id"], "sk1")
        self.assertEqual(body["name"], "My Skill")
        gl.return_value.crystallize.assert_called_once_with(
            task="do X", steps=[], tools_used=[], agent_id="",
            success=True, tags=[], duration_ms=0.0,
        )

    def test_crystallize_missing_task_400(self):
        r = self.client.post("/api/skills/crystallize", json={"steps": []})
        self.assertEqual(r.status_code, 400)
        self.assertIn("task is required", r.get_json()["error"])

    def test_crystallize_no_body_400(self):
        r = self.client.post("/api/skills/crystallize")
        self.assertEqual(r.status_code, 400)

    def test_crystallize_exception_500(self):
        with patch("orbit.skill_library.get_skill_library", side_effect=RuntimeError("x")):
            r = self.client.post("/api/skills/crystallize", json={"task": "x"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("crystallize failed", r.get_json()["error"])

    def test_crystallize_all_fields(self):
        skill = MagicMock()
        skill.id = "sk2"
        skill.name = "N2"
        with patch("orbit.skill_library.get_skill_library") as gl:
            gl.return_value.crystallize.return_value = skill
            r = self.client.post("/api/skills/crystallize", json={
                "task": "T", "steps": ["a"], "tools_used": ["b"],
                "agent_id": "ag", "success": False, "tags": ["x"],
                "duration_ms": 12.5,
            })
        self.assertEqual(r.status_code, 200)
        gl.return_value.crystallize.assert_called_once_with(
            task="T", steps=["a"], tools_used=["b"], agent_id="ag",
            success=False, tags=["x"], duration_ms=12.5,
        )


class TestRecall(SkillsBpBase):
    def test_recall_success(self):
        with patch("orbit.skill_library.get_skill_library") as gl:
            gl.return_value.recall.return_value = [{"id": "s1"}]
            r = self.client.post("/api/skills/recall", json={"query": "format json"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["skills"], [{"id": "s1"}])
        gl.return_value.recall.assert_called_once_with("format json", 5)

    def test_recall_limit(self):
        with patch("orbit.skill_library.get_skill_library") as gl:
            gl.return_value.recall.return_value = []
            r = self.client.post("/api/skills/recall", json={"query": "x", "limit": 10})
        gl.return_value.recall.assert_called_once_with("x", 10)

    def test_recall_missing_query_400(self):
        r = self.client.post("/api/skills/recall", json={"limit": 3})
        self.assertEqual(r.status_code, 400)
        self.assertIn("query is required", r.get_json()["error"])

    def test_recall_no_body_400(self):
        r = self.client.post("/api/skills/recall")
        self.assertEqual(r.status_code, 400)

    def test_recall_exception_500(self):
        with patch("orbit.skill_library.get_skill_library", side_effect=RuntimeError("x")):
            r = self.client.post("/api/skills/recall", json={"query": "x"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("recall failed", r.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
