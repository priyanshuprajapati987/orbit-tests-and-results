"""Unit tests for orbit/orbit/core/workflow_bp.py."""

import os
import sys
import threading
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.workflow_bp import workflow_bp, _VALID_ACTIONS


def _engine():
    """Fake engine with real lock + plain dicts (blueprint uses internals)."""
    eng = MagicMock()
    eng._lock = threading.RLock()
    eng.workflows = {}
    eng.instances = {}
    return eng


def _wf(name="WF", status="idle", steps=None):
    wf = MagicMock()
    wf.name = name
    wf.status = status
    wf.steps = steps if steps is not None else {}
    return wf


def _step(name="S", action="log", status="pending"):
    st = MagicMock()
    st.name = name
    st.action = action
    st.status = status
    return st


class WorkflowBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(workflow_bp)
        self.client = self.app.test_client()
        self.eng = _engine()

    def _patch(self):
        return patch("orbit.core.workflow_bp.get_workflow_engine",
                     return_value=self.eng)

    def test_blueprint_name(self):
        self.assertEqual(workflow_bp.name, "workflow")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/workflow/list", "/api/workflow/create",
                  "/api/workflow/<wf_id>/run", "/api/workflow/<wf_id>/status",
                  "/api/workflow/<wf_id>", "/api/workflow/stats"]:
            self.assertIn(p, rules)


class TestListWorkflows(WorkflowBpBase):
    def test_list_empty(self):
        with self._patch():
            r = self.client.get("/api/workflow/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"workflows": [], "count": 0})

    def test_list_with_workflows(self):
        self.eng.workflows["w1"] = _wf(name="Alpha", status="running",
                                       steps={"a": _step(), "b": _step()})
        self.eng.workflows["w2"] = _wf(name="Beta")
        with self._patch():
            r = self.client.get("/api/workflow/list")
        body = r.get_json()
        self.assertEqual(body["count"], 2)
        wfs = {w["id"]: w for w in body["workflows"]}
        self.assertEqual(wfs["w1"]["name"], "Alpha")
        self.assertEqual(wfs["w1"]["status"], "running")
        self.assertEqual(wfs["w1"]["steps"], 2)
        self.assertEqual(wfs["w2"]["steps"], 0)

    def test_list_missing_attrs_defaults(self):
        wf = MagicMock(spec=[])  # no name/status/steps attrs
        self.eng.workflows["w3"] = wf
        with self._patch():
            r = self.client.get("/api/workflow/list")
        w = r.get_json()["workflows"][0]
        self.assertEqual(w["name"], "w3")
        self.assertEqual(w["status"], "unknown")
        self.assertEqual(w["steps"], 0)


class TestCreateWorkflow(WorkflowBpBase):
    def test_create_defaults(self):
        self.eng.create_workflow.return_value = "wf-1"
        with self._patch():
            r = self.client.post("/api/workflow/create", json={"name": "My WF"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["workflow_id"], "wf-1")
        self.eng.create_workflow.assert_called_once_with("My WF", "")
        self.eng.add_step.assert_not_called()

    def test_create_with_steps(self):
        self.eng.create_workflow.return_value = "wf-1"
        steps = [{"id": "s1", "name": "Step1", "action": "log",
                  "config": {"msg": "hi"}, "dependencies": []}]
        with self._patch():
            r = self.client.post("/api/workflow/create",
                                 json={"name": "WF", "description": "D",
                                       "steps": steps})
        self.assertEqual(r.status_code, 200)
        self.eng.create_workflow.assert_called_once_with("WF", "D")
        self.eng.add_step.assert_called_once_with(
            "wf-1", step_id="s1", name="Step1", action="log",
            config={"msg": "hi"}, dependencies=[])

    def test_create_step_defaults(self):
        self.eng.create_workflow.return_value = "wf-1"
        with self._patch():
            r = self.client.post("/api/workflow/create",
                                 json={"name": "WF", "steps": [{}]})
        self.assertEqual(r.status_code, 200)
        args, kwargs = self.eng.add_step.call_args
        self.assertEqual(args[0], "wf-1")
        self.assertTrue(kwargs["step_id"].startswith("step_"))
        self.assertEqual(kwargs["name"], "unnamed")
        self.assertEqual(kwargs["action"], "log")

    def test_name_stripped_and_truncated(self):
        self.eng.create_workflow.return_value = "wf-1"
        with self._patch():
            r = self.client.post("/api/workflow/create",
                                 json={"name": "  " + "x" * 300 + "  "})
        self.eng.create_workflow.assert_called_once_with("x" * 200, "")

    def test_empty_name_400(self):
        with self._patch():
            r = self.client.post("/api/workflow/create", json={"name": "   "})
        self.assertEqual(r.status_code, 400)
        self.eng.create_workflow.assert_not_called()

    def test_non_string_name_400(self):
        r = self.client.post("/api/workflow/create", json={"name": 123})
        self.assertEqual(r.status_code, 400)

    def test_default_name_when_missing(self):
        # missing name -> data.get("name", "unnamed") -> "unnamed" valid
        self.eng.create_workflow.return_value = "wf-1"
        with self._patch():
            r = self.client.post("/api/workflow/create", json={})
        self.assertEqual(r.status_code, 200)
        self.eng.create_workflow.assert_called_once_with("unnamed", "")

    def test_non_string_description_400(self):
        r = self.client.post("/api/workflow/create",
                             json={"name": "WF", "description": 42})
        self.assertEqual(r.status_code, 400)
        self.assertIn("description must be a string", r.get_json()["error"])

    def test_description_truncated(self):
        self.eng.create_workflow.return_value = "wf-1"
        with self._patch():
            r = self.client.post("/api/workflow/create",
                                 json={"name": "WF", "description": "d" * 5000})
        self.eng.create_workflow.assert_called_once_with("WF", "d" * 2000)

    def test_steps_not_list_400(self):
        r = self.client.post("/api/workflow/create",
                             json={"name": "WF", "steps": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("at most 100", r.get_json()["error"])

    def test_steps_too_many_400(self):
        r = self.client.post("/api/workflow/create",
                             json={"name": "WF", "steps": [{}] * 101})
        self.assertEqual(r.status_code, 400)

    def test_step_not_dict_400(self):
        r = self.client.post("/api/workflow/create",
                             json={"name": "WF", "steps": ["str-step"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("each step must be an object", r.get_json()["error"])

    def test_invalid_action_400(self):
        r = self.client.post("/api/workflow/create",
                             json={"name": "WF",
                                   "steps": [{"action": "explode"}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid action", r.get_json()["error"])

    def test_valid_actions_accepted(self):
        self.eng.create_workflow.return_value = "wf-1"
        steps = [{"action": a} for a in sorted(_VALID_ACTIONS)]
        with self._patch():
            r = self.client.post("/api/workflow/create",
                                 json={"name": "WF", "steps": steps})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.eng.add_step.call_count, len(_VALID_ACTIONS))

    def test_bad_dependencies_400(self):
        r = self.client.post("/api/workflow/create",
                             json={"name": "WF",
                                   "steps": [{"dependencies": [1, 2]}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("dependencies must be a list of step ids",
                      r.get_json()["error"])

    def test_dependencies_not_list_400(self):
        r = self.client.post("/api/workflow/create",
                             json={"name": "WF",
                                   "steps": [{"dependencies": "x"}]})
        self.assertEqual(r.status_code, 400)

    def test_config_not_dict_400(self):
        r = self.client.post("/api/workflow/create",
                             json={"name": "WF", "steps": [{"config": [1]}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("config must be an object", r.get_json()["error"])

    def test_no_body(self):
        # name defaults to "unnamed" -> valid
        self.eng.create_workflow.return_value = "wf-1"
        with self._patch():
            r = self.client.post("/api/workflow/create")
        self.assertEqual(r.status_code, 200)


class TestRunWorkflow(WorkflowBpBase):
    def test_run_success(self):
        self.eng.execute_workflow.return_value = "inst-1"
        with self._patch():
            r = self.client.post("/api/workflow/w1/run", json={"context": {"a": 1}})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["instance_id"], "inst-1")
        self.eng.execute_workflow.assert_called_once_with("w1", {"a": 1})

    def test_run_default_context(self):
        self.eng.execute_workflow.return_value = "inst-1"
        with self._patch():
            r = self.client.post("/api/workflow/w1/run", json={})
        self.eng.execute_workflow.assert_called_once_with("w1", {})

    def test_run_no_body(self):
        self.eng.execute_workflow.return_value = "inst-1"
        with self._patch():
            r = self.client.post("/api/workflow/w1/run")
        self.assertEqual(r.status_code, 200)

    def test_run_bad_context_400(self):
        with self._patch():
            r = self.client.post("/api/workflow/w1/run", json={"context": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("context must be an object", r.get_json()["error"])
        self.eng.execute_workflow.assert_not_called()

    def test_run_exception_500(self):
        self.eng.execute_workflow.side_effect = RuntimeError("boom")
        with self._patch():
            r = self.client.post("/api/workflow/w1/run", json={})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "Workflow execution failed")


class TestWorkflowStatus(WorkflowBpBase):
    def test_status(self):
        steps = {"s1": _step(name="One", action="log", status="done"),
                 "s2": _step(name="Two", action="delay", status="pending")}
        self.eng.workflows["w1"] = _wf(name="Alpha", status="running",
                                       steps=steps)
        with self._patch():
            r = self.client.get("/api/workflow/w1/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["id"], "w1")
        self.assertEqual(body["name"], "Alpha")
        self.assertEqual(body["status"], "running")
        self.assertEqual(body["steps"]["s1"],
                         {"name": "One", "action": "log", "status": "done"})
        self.assertEqual(body["steps"]["s2"]["status"], "pending")

    def test_status_not_found_404(self):
        with self._patch():
            r = self.client.get("/api/workflow/nope/status")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Not found")

    def test_status_empty_steps(self):
        self.eng.workflows["w1"] = _wf(steps={})
        with self._patch():
            r = self.client.get("/api/workflow/w1/status")
        self.assertEqual(r.get_json()["steps"], {})


class TestDeleteWorkflow(WorkflowBpBase):
    def test_delete_ok(self):
        self.eng.workflows["w1"] = _wf()
        with self._patch():
            r = self.client.delete("/api/workflow/w1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertNotIn("w1", self.eng.workflows)

    def test_delete_not_found_404(self):
        with self._patch():
            r = self.client.delete("/api/workflow/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Not found")


class TestStats(WorkflowBpBase):
    def test_stats(self):
        self.eng.workflows["w1"] = _wf()
        self.eng.workflows["w2"] = _wf()
        self.eng.instances["i1"] = object()
        with self._patch():
            r = self.client.get("/api/workflow/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"total_workflows": 2, "total_instances": 1})

    def test_stats_empty(self):
        with self._patch():
            r = self.client.get("/api/workflow/stats")
        self.assertEqual(r.get_json(),
                         {"total_workflows": 0, "total_instances": 0})


if __name__ == "__main__":
    unittest.main()
