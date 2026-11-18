"""Unit tests for orbit/orbit/core/code_generator_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.code_generator_bp import code_generator_bp


class CodeGenBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(code_generator_bp)
        self.client = self.app.test_client()
        self.gen = MagicMock()

    def _patch(self):
        return patch("orbit.core.code_generator_bp.get_code_generator",
                     return_value=self.gen)

    def test_blueprint_name(self):
        self.assertEqual(code_generator_bp.name, "code_generator")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/code/generate", "/api/code/result/<project_name>",
                  "/api/code/list", "/api/code/write", "/api/code/save",
                  "/api/code/load", "/api/code/reset", "/api/code/status"]:
            self.assertIn(p, rules)


class TestGenerate(CodeGenBpBase):
    def test_success(self):
        self.gen.generate.return_value = {"files": ["main.py"]}
        plan = {"project_name": "demo"}
        with self._patch():
            r = self.client.post("/api/code/generate",
                                 json={"architecture_plan": plan,
                                       "parsed_spec": {"x": 1}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["files"], ["main.py"])
        self.gen.generate.assert_called_once_with(plan, {"x": 1})

    def test_missing_plan_400(self):
        with self._patch():
            r = self.client.post("/api/code/generate", json={"parsed_spec": {}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("architecture_plan with project_name required",
                      r.get_json()["error"])
        self.gen.generate.assert_not_called()

    def test_plan_without_project_name_400(self):
        r = self.client.post("/api/code/generate",
                             json={"architecture_plan": {"name": "x"}})
        self.assertEqual(r.status_code, 400)

    def test_no_body_400(self):
        r = self.client.post("/api/code/generate")
        self.assertEqual(r.status_code, 400)

    def test_default_parsed_spec(self):
        self.gen.generate.return_value = {}
        plan = {"project_name": "demo"}
        with self._patch():
            r = self.client.post("/api/code/generate",
                                 json={"architecture_plan": plan})
        self.gen.generate.assert_called_once_with(plan, {})

    def test_exception_500(self):
        self.gen.generate.side_effect = RuntimeError("boom")
        with self._patch():
            r = self.client.post("/api/code/generate",
                                 json={"architecture_plan": {"project_name": "p"}})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "Code generation failed")


class TestGetResult(CodeGenBpBase):
    def test_found(self):
        self.gen.get_result.return_value = {"project_name": "demo"}
        with self._patch():
            r = self.client.get("/api/code/result/demo")
        self.assertEqual(r.status_code, 200)
        self.gen.get_result.assert_called_once_with("demo")

    def test_not_found_404(self):
        self.gen.get_result.return_value = None
        with self._patch():
            r = self.client.get("/api/code/result/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "not found")


class TestList(CodeGenBpBase):
    def test_list(self):
        self.gen.list_results.return_value = ["a", "b"]
        with self._patch():
            r = self.client.get("/api/code/list")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["results"], ["a", "b"])
        self.assertEqual(body["count"], 2)

    def test_list_empty(self):
        self.gen.list_results.return_value = []
        with self._patch():
            r = self.client.get("/api/code/list")
        self.assertEqual(r.get_json()["count"], 0)


class TestWriteFiles(CodeGenBpBase):
    def test_success(self):
        self.gen.write_files.return_value = {"written": 3}
        with self._patch():
            r = self.client.post("/api/code/write",
                                 json={"project_name": "demo",
                                       "output_dir": "."})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["written"], 3)
        self.gen.write_files.assert_called_once_with("demo", ".")

    def test_missing_fields_400(self):
        with self._patch():
            r = self.client.post("/api/code/write", json={"project_name": "demo"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("project_name and output_dir required",
                      r.get_json()["error"])

    def test_no_body_400(self):
        r = self.client.post("/api/code/write")
        self.assertEqual(r.status_code, 400)

    def test_blocked_path_403(self):
        with self._patch():
            r = self.client.post("/api/code/write",
                                 json={"project_name": "demo",
                                       "output_dir": "C:/Windows/System32"})
        self.assertEqual(r.status_code, 403)
        body = r.get_json()
        self.assertEqual(body["error"], "path not allowed")
        self.assertEqual(body["reason"], "blocked_system_directory")
        self.gen.write_files.assert_not_called()

    def test_exception_500(self):
        self.gen.write_files.side_effect = RuntimeError("x")
        with self._patch():
            r = self.client.post("/api/code/write",
                                 json={"project_name": "demo", "output_dir": "."})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "Code write failed")


class TestSave(CodeGenBpBase):
    def test_success(self):
        with self._patch():
            r = self.client.post("/api/code/save",
                                 json={"filepath": "D:/jarves/out/x.py"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.gen.save.assert_called_once_with("D:/jarves/out/x.py")

    def test_missing_filepath_400(self):
        r = self.client.post("/api/code/save", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("filepath required", r.get_json()["error"])

    def test_traversal_400(self):
        with self._patch():
            r = self.client.post("/api/code/save",
                                 json={"filepath": "../evil.py"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("traversal detected", r.get_json()["error"])
        self.gen.save.assert_not_called()

    def test_nested_traversal_400(self):
        r = self.client.post("/api/code/save",
                             json={"filepath": "a/../b.py"})
        self.assertEqual(r.status_code, 400)

    def test_blocked_path_403(self):
        with self._patch():
            r = self.client.post("/api/code/save",
                                 json={"filepath": "C:/Windows/System32/x.py"})
        self.assertEqual(r.status_code, 403)
        self.gen.save.assert_not_called()

    def test_exception_500(self):
        self.gen.save.side_effect = RuntimeError("x")
        with self._patch():
            r = self.client.post("/api/code/save",
                                 json={"filepath": "D:/jarves/x.py"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "Code save failed")


class TestLoad(CodeGenBpBase):
    def test_success(self):
        with self._patch():
            r = self.client.post("/api/code/load",
                                 json={"filepath": "D:/jarves/out/x.py"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.gen.load.assert_called_once_with("D:/jarves/out/x.py")

    def test_missing_filepath_400(self):
        r = self.client.post("/api/code/load", json={})
        self.assertEqual(r.status_code, 400)

    def test_traversal_400(self):
        with self._patch():
            r = self.client.post("/api/code/load",
                                 json={"filepath": "../x.py"})
        self.assertEqual(r.status_code, 400)
        self.gen.load.assert_not_called()

    def test_blocked_path_403(self):
        with self._patch():
            r = self.client.post("/api/code/load",
                                 json={"filepath": "C:/Windows/System32/x.py"})
        self.assertEqual(r.status_code, 403)

    def test_exception_500(self):
        self.gen.load.side_effect = RuntimeError("x")
        with self._patch():
            r = self.client.post("/api/code/load",
                                 json={"filepath": "D:/jarves/x.py"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "Code load failed")


class TestResetStatus(CodeGenBpBase):
    def test_reset(self):
        with self._patch():
            r = self.client.post("/api/code/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.gen.reset.assert_called_once()

    def test_status(self):
        self.gen.list_results.return_value = ["p1", "p2"]
        with self._patch():
            r = self.client.get("/api/code/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["generated_projects"], 2)
        self.assertEqual(body["projects"], ["p1", "p2"])


if __name__ == "__main__":
    unittest.main()
