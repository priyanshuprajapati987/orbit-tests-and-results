"""Unit tests for orbit/orbit/core/skill_learning_bp.py."""

import os
import sys
class _Skill:
    def __init__(self, **kw):
        self.__dict__.update(kw)
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.skill_learning_bp import skill_learning_bp


class TestSkillLearningBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(skill_learning_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(skill_learning_bp.name, "skill_learning")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/skill-learning/dashboard", "/api/skill-learning/record",
                  "/api/skill-learning/search", "/api/skill-learning/skills",
                  "/api/skill-learning/skills/<skill_id>", "/api/skill-learning/patterns",
                  "/api/skill-learning/stats"]:
            self.assertIn(p, rules)

    def test_dashboard(self):
        with patch("orbit.core.skill_learning_bp.get_skill_dashboard", return_value={"total": 5}):
            r = self.client.get("/api/skill-learning/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_record_missing_fields_400(self):
        r = self.client.post("/api/skill-learning/record", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_missing_description_400(self):
        r = self.client.post("/api/skill-learning/record", json={"task_id": "t1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_success(self):
        trace = MagicMock()
        trace.task_id = "t1"
        trace.extracted_skills = ["s1"]
        with patch("orbit.core.skill_learning_bp.get_skill_learner") as gl:
            gl.return_value.record_task.return_value = trace
            r = self.client.post("/api/skill-learning/record", json={
                "task_id": "t1", "description": "d", "steps": [1, 2], "result": "r", "success": True, "duration_ms": 10
            })
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["task_id"], "t1")
        self.assertEqual(body["extracted_skills"], ["s1"])
        gl.return_value.record_task.assert_called_once_with("t1", "d", [1, 2], "r", True, 10)

    def test_record_defaults(self):
        trace = MagicMock()
        trace.task_id = "t2"
        trace.extracted_skills = []
        with patch("orbit.core.skill_learning_bp.get_skill_learner") as gl:
            gl.return_value.record_task.return_value = trace
            r = self.client.post("/api/skill-learning/record", json={"task_id": "t2", "description": "d"})
        gl.return_value.record_task.assert_called_once_with("t2", "d", [], "", True, 0)

    def test_record_no_body(self):
        r = self.client.post("/api/skill-learning/record")
        self.assertEqual(r.status_code, 400)

    def test_search(self):
        skill = _Skill(id="s1")
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.search.return_value = [skill]
            r = self.client.get("/api/skill-learning/search?q=q&category=c&limit=5")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["skills"], [{"id": "s1"}])
        self.assertEqual(body["count"], 1)
        gs.return_value.search.assert_called_once_with("q", category="c", limit=5)

    def test_search_defaults(self):
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.search.return_value = []
            r = self.client.get("/api/skill-learning/search")
        gs.return_value.search.assert_called_once_with("", category="", limit=20)

    def test_search_invalid_limit(self):
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.search.return_value = []
            r = self.client.get("/api/skill-learning/search?limit=abc")
        self.assertEqual(r.status_code, 200)
        gs.return_value.search.assert_called_once_with("", category="", limit=20)

    def test_search_clamped(self):
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.search.return_value = []
            r = self.client.get("/api/skill-learning/search?limit=1000")
        gs.return_value.search.assert_called_once_with("", category="", limit=200)

    def test_list_skills(self):
        skill = _Skill(id="s1")
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value._skills = {"s1": skill}
            r = self.client.get("/api/skill-learning/skills")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["skills"], [{"id": "s1"}])
        self.assertEqual(body["count"], 1)

    def test_list_skills_empty(self):
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value._skills = {}
            r = self.client.get("/api/skill-learning/skills")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["skills"], [])

    def test_get_skill_found(self):
        skill = _Skill(id="s1")
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.get.return_value = skill
            r = self.client.get("/api/skill-learning/skills/s1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "s1")
        gs.return_value.get.assert_called_once_with("s1")

    def test_get_skill_not_found_404(self):
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.get.return_value = None
            r = self.client.get("/api/skill-learning/skills/s1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_delete_skill(self):
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.delete.return_value = True
            r = self.client.delete("/api/skill-learning/skills/s1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gs.return_value.delete.assert_called_once_with("s1")

    def test_delete_skill_not_found_404(self):
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.delete.return_value = False
            r = self.client.delete("/api/skill-learning/skills/s1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_patterns(self):
        with patch("orbit.core.skill_learning_bp.get_skill_learner") as gl:
            gl.return_value.learn_from_failures.return_value = [{"p": 1}]
            r = self.client.get("/api/skill-learning/patterns")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["patterns"], [{"p": 1}])
        self.assertEqual(r.get_json()["count"], 1)

    def test_stats(self):
        with patch("orbit.core.skill_learning_bp.get_skill_store") as gs:
            gs.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/skill-learning/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
