"""Unit tests for orbit/orbit/core/financial_api_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.financial_api_bp import financial_api_bp

COST = "orbit.core.cost_optimizer.get_cost_optimizer"
TRACKER = "orbit.core.financial_tracker.get_financial_tracker"
ORCH = "orbit.core.ai_orchestrator.get_ai_orchestrator"
IMPROVER = "orbit.core.self_improver_v2.get_self_improver_v2"
COORD = "orbit.core.multi_ai_coordinator.get_multi_ai_coordinator"

GENERIC_500 = {"error": "Internal server error"}


class FinancialBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(financial_api_bp)
        self.client = self.app.test_client()

        self.cost = MagicMock()
        self.tracker = MagicMock()
        self.orch = MagicMock()
        self.improver = MagicMock()
        self.coord = MagicMock()

        for target, mock in (
            (COST, self.cost),
            (TRACKER, self.tracker),
            (ORCH, self.orch),
            (IMPROVER, self.improver),
            (COORD, self.coord),
        ):
            p = patch(target, return_value=mock)
            p.start()
            self.addCleanup(p.stop)

    def assert500(self, resp):
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json(), GENERIC_500)

    def test_blueprint_name(self):
        self.assertEqual(financial_api_bp.name, "financial_api")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/cost/stats", "/cost/optimize", "/cost/select-model",
                  "/cost/estimate", "/cost/budget",
                  "/cost/recommendations", "/cost/recent",
                  "/finance/stats", "/finance/expense", "/finance/income",
                  "/finance/roi", "/finance/budget", "/finance/project",
                  "/finance/projects",
                  "/orchestrate/classify", "/orchestrate/rankings",
                  "/orchestrate/stats",
                  "/improve/benchmark", "/improve/compare",
                  "/improve/upgrades", "/improve/apply", "/improve/rollback",
                  "/improve/stats", "/improve/models",
                  "/coordinate/workflow", "/coordinate/execute/<workflow_id>",
                  "/coordinate/parallel", "/coordinate/workflow/<workflow_id>",
                  "/coordinate/workflows", "/coordinate/stats"]:
            self.assertIn(p, rules)


class TestCost(FinancialBase):
    def test_stats(self):
        self.cost.get_stats.return_value = {"spent": 3.5}
        r = self.client.get("/cost/stats")
        self.assertEqual(r.get_json(), {"spent": 3.5})

    def test_stats_exception_500(self):
        with self.assertLogs("orbit.core.financial_api_bp",
                             level="ERROR"):
            self.cost.get_stats.side_effect = RuntimeError("cost fail")
            r = self.client.get("/cost/stats")
        self.assert500(r)

    def test_optimize_success(self):
        self.cost.optimize_prompt.return_value = {"tokens": 42}
        r = self.client.post("/cost/optimize",
                             json={"prompt": "say hi"})
        self.assertEqual(r.get_json(), {"tokens": 42})
        self.cost.optimize_prompt.assert_called_once_with(
            "say hi", "general")

    def test_optimize_custom_task_type(self):
        self.cost.optimize_prompt.return_value = {}
        self.client.post("/cost/optimize", json={
            "prompt": "p", "task_type": "coding"})
        self.cost.optimize_prompt.assert_called_once_with(
            "p", "coding")

    def test_optimize_missing_prompt_400(self):
        r = self.client.post("/cost/optimize", json={"task_type": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "prompt required"})
        self.cost.optimize_prompt.assert_not_called()

    def test_optimize_no_body_400(self):
        r = self.client.post("/cost/optimize")
        self.assertEqual(r.status_code, 400)

    def test_optimize_exception_500(self):
        self.cost.optimize_prompt.side_effect = RuntimeError("op")
        r = self.client.post("/cost/optimize", json={"prompt": "p"})
        self.assert500(r)

    def test_select_model_success(self):
        self.cost.select_model.return_value = {"model": "mini"}
        r = self.client.post("/cost/select-model",
                             json={"task_type": "chat"})
        self.assertEqual(r.get_json(), {"model": "mini"})
        self.cost.select_model.assert_called_once_with(
            "chat", "medium", 0.05)

    def test_select_model_full_fields(self):
        self.cost.select_model.return_value = {}
        self.client.post("/cost/select-model", json={
            "task_type": "code", "quality_needed": "high",
            "max_cost": 0.2})
        self.cost.select_model.assert_called_once_with(
            "code", "high", 0.2)

    def test_select_model_missing_task_type_400(self):
        r = self.client.post("/cost/select-model", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "task_type required"})

    def test_select_model_exception_500(self):
        self.cost.select_model.side_effect = RuntimeError("sm")
        r = self.client.post("/cost/select-model",
                             json={"task_type": "t"})
        self.assert500(r)

    def test_estimate_defaults(self):
        self.cost.estimate_cost.return_value = {"usd": 0.001}
        r = self.client.post("/cost/estimate", json={})
        self.assertEqual(r.get_json(), {"usd": 0.001})
        self.cost.estimate_cost.assert_called_once_with(
            "gpt-4o-mini", 100, 100)

    def test_estimate_full_fields(self):
        self.cost.estimate_cost.return_value = {}
        self.client.post("/cost/estimate", json={
            "model": "gpt-4o", "tokens_in": 500, "tokens_out": 50})
        self.cost.estimate_cost.assert_called_once_with(
            "gpt-4o", 500, 50)

    def test_estimate_no_body(self):
        self.cost.estimate_cost.return_value = {"usd": 0.0}
        r = self.client.post("/cost/estimate")
        self.assertEqual(r.status_code, 200)

    def test_estimate_exception_500(self):
        self.cost.estimate_cost.side_effect = RuntimeError("est")
        r = self.client.post("/cost/estimate", json={})
        self.assert500(r)

    def test_budget_get(self):
        self.cost.get_budget_status.return_value = {"used": 2}
        r = self.client.get("/cost/budget")
        self.assertEqual(r.get_json(), {"used": 2})
        self.cost.set_budget.assert_not_called()

    def test_budget_post_default_limit(self):
        self.cost.set_budget.return_value = {"limit": 10}
        r = self.client.post("/cost/budget", json={})
        self.assertEqual(r.get_json(), {"limit": 10})
        self.cost.set_budget.assert_called_once_with(10)

    def test_budget_post_custom_limit(self):
        self.cost.set_budget.return_value = {}
        self.client.post("/cost/budget", json={"limit": 50})
        self.cost.set_budget.assert_called_once_with(50)

    def test_budget_exception_500(self):
        self.cost.get_budget_status.side_effect = RuntimeError("bg")
        r = self.client.get("/cost/budget")
        self.assert500(r)

    def test_recommendations(self):
        self.cost.get_recommendations.return_value = ["downgrade"]
        r = self.client.get("/cost/recommendations")
        self.assertEqual(r.get_json(), ["downgrade"])

    def test_recommendations_exception_500(self):
        self.cost.get_recommendations.side_effect = RuntimeError("rc")
        r = self.client.get("/cost/recommendations")
        self.assert500(r)

    def test_recent_default_limit(self):
        self.cost.get_recent.return_value = ["e1"]
        r = self.client.get("/cost/recent")
        self.assertEqual(r.get_json(), ["e1"])
        self.cost.get_recent.assert_called_once_with(20)

    def test_recent_custom_limit(self):
        self.cost.get_recent.return_value = []
        self.client.get("/cost/recent?limit=3")
        self.cost.get_recent.assert_called_once_with(3)

    def test_recent_exception_500(self):
        self.cost.get_recent.side_effect = RuntimeError("cr")
        r = self.client.get("/cost/recent")
        self.assert500(r)


class TestFinance(FinancialBase):
    def test_stats(self):
        self.tracker.get_stats.return_value = {"balance": 100}
        r = self.client.get("/finance/stats")
        self.assertEqual(r.get_json(), {"balance": 100})

    def test_stats_exception_500(self):
        self.tracker.get_stats.side_effect = RuntimeError("fs")
        r = self.client.get("/finance/stats")
        self.assert500(r)

    def test_expense_defaults(self):
        self.tracker.record_expense.return_value = {"id": "e1"}
        r = self.client.post("/finance/expense", json={})
        self.assertEqual(r.get_json(), {"id": "e1"})
        self.tracker.record_expense.assert_called_once_with(
            category="other", description="", amount_usd=0,
            model="", provider="", project_id="")

    def test_expense_full_fields(self):
        self.tracker.record_expense.return_value = {}
        self.client.post("/finance/expense", json={
            "category": "api", "description": "llm calls",
            "amount": 4.2, "model": "gpt-4o", "provider": "openai",
            "project_id": "p1"})
        self.tracker.record_expense.assert_called_once_with(
            category="api", description="llm calls", amount_usd=4.2,
            model="gpt-4o", provider="openai", project_id="p1")

    def test_expense_exception_500(self):
        self.tracker.record_expense.side_effect = RuntimeError("re")
        r = self.client.post("/finance/expense", json={})
        self.assert500(r)

    def test_income_defaults(self):
        self.tracker.record_income.return_value = {"id": "i1"}
        r = self.client.post("/finance/income", json={})
        self.assertEqual(r.get_json(), {"id": "i1"})
        self.tracker.record_income.assert_called_once_with(
            source="other", description="", amount_usd=0,
            platform_fee=0, project_id="")

    def test_income_full_fields(self):
        self.tracker.record_income.return_value = {}
        self.client.post("/finance/income", json={
            "source": "client", "description": "retainer",
            "amount": 500, "fee": 25, "project_id": "p2"})
        self.tracker.record_income.assert_called_once_with(
            source="client", description="retainer", amount_usd=500,
            platform_fee=25, project_id="p2")

    def test_income_exception_500(self):
        self.tracker.record_income.side_effect = RuntimeError("ri")
        r = self.client.post("/finance/income", json={})
        self.assert500(r)

    def test_roi_default_period(self):
        self.tracker.calculate_roi.return_value = {"roi": 1.4}
        r = self.client.get("/finance/roi")
        self.assertEqual(r.get_json(), {"roi": 1.4})
        self.tracker.calculate_roi.assert_called_once_with("month")

    def test_roi_custom_period(self):
        self.tracker.calculate_roi.return_value = {}
        self.client.get("/finance/roi?period=year")
        self.tracker.calculate_roi.assert_called_once_with("year")

    def test_roi_exception_500(self):
        self.tracker.calculate_roi.side_effect = RuntimeError("roi")
        r = self.client.get("/finance/roi")
        self.assert500(r)

    def test_budget_get(self):
        self.tracker.get_budget_status.return_value = {"limit": 100}
        r = self.client.get("/finance/budget")
        self.assertEqual(r.get_json(), {"limit": 100})
        self.tracker.set_budget.assert_not_called()

    def test_budget_post_default(self):
        self.tracker.set_budget.return_value = {"set": True}
        r = self.client.post("/finance/budget", json={})
        self.assertEqual(r.get_json(), {"set": True})
        self.tracker.set_budget.assert_called_once_with(100)

    def test_budget_post_custom(self):
        self.tracker.set_budget.return_value = {}
        self.client.post("/finance/budget", json={"limit": 750})
        self.tracker.set_budget.assert_called_once_with(750)

    def test_budget_exception_500(self):
        self.tracker.get_budget_status.side_effect = RuntimeError("fb")
        r = self.client.get("/finance/budget")
        self.assert500(r)

    def test_project_create_defaults(self):
        self.tracker.create_project.return_value = {"id": "p1"}
        r = self.client.post("/finance/project", json={})
        self.assertEqual(r.get_json(), {"id": "p1"})
        self.tracker.create_project.assert_called_once_with(
            name="", category="", sale_price=0, platform="")

    def test_project_create_full(self):
        self.tracker.create_project.return_value = {}
        self.client.post("/finance/project", json={
            "name": "ORBIT", "category": "saas",
            "sale_price": 9999, "platform": "acquire"})
        self.tracker.create_project.assert_called_once_with(
            name="ORBIT", category="saas", sale_price=9999,
            platform="acquire")

    def test_project_create_exception_500(self):
        self.tracker.create_project.side_effect = RuntimeError("pc")
        r = self.client.post("/finance/project", json={})
        self.assert500(r)

    def test_projects_defaults(self):
        self.tracker.list_projects.return_value = ["p1"]
        r = self.client.get("/finance/projects")
        self.assertEqual(r.get_json(), ["p1"])
        self.tracker.list_projects.assert_called_once_with("", 20)

    def test_projects_filter_args(self):
        self.tracker.list_projects.return_value = []
        self.client.get("/finance/projects?status=active&limit=5")
        self.tracker.list_projects.assert_called_once_with("active", 5)

    def test_projects_exception_500(self):
        self.tracker.list_projects.side_effect = RuntimeError("lp")
        r = self.client.get("/finance/projects")
        self.assert500(r)


class TestOrchestrate(FinancialBase):
    def test_classify_success(self):
        self.orch.classify.return_value = {"kind": "coding"}
        r = self.client.post("/orchestrate/classify",
                             json={"task": "write tests"})
        self.assertEqual(r.get_json(), {"kind": "coding"})
        self.orch.classify.assert_called_once_with("write tests")

    def test_classify_missing_task_400(self):
        r = self.client.post("/orchestrate/classify", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"error": "task required"})
        self.orch.classify.assert_not_called()

    def test_classify_no_body_400(self):
        r = self.client.post("/orchestrate/classify")
        self.assertEqual(r.status_code, 400)

    def test_classify_exception_500(self):
        self.orch.classify.side_effect = RuntimeError("cl")
        r = self.client.post("/orchestrate/classify",
                             json={"task": "t"})
        self.assert500(r)

    def test_rankings(self):
        self.orch.get_model_rankings.return_value = [{"m": "a"}]
        r = self.client.get("/orchestrate/rankings")
        self.assertEqual(r.get_json(), [{"m": "a"}])

    def test_rankings_exception_500(self):
        self.orch.get_model_rankings.side_effect = RuntimeError("rk")
        r = self.client.get("/orchestrate/rankings")
        self.assert500(r)

    def test_stats(self):
        self.orch.get_stats.return_value = {"classified": 9}
        r = self.client.get("/orchestrate/stats")
        self.assertEqual(r.get_json(), {"classified": 9})

    def test_stats_exception_500(self):
        self.orch.get_stats.side_effect = RuntimeError("os")
        r = self.client.get("/orchestrate/stats")
        self.assert500(r)


class TestImprove(FinancialBase):
    def test_benchmark_defaults(self):
        self.improver.benchmark_model.return_value = {"score": 0.8}
        r = self.client.post("/improve/benchmark", json={})
        self.assertEqual(r.get_json(), {"score": 0.8})
        self.improver.benchmark_model.assert_called_once_with(
            "qwen2.5:14b", None)

    def test_benchmark_full_fields(self):
        self.improver.benchmark_model.return_value = {}
        self.client.post("/improve/benchmark", json={
            "model": "llama3", "prompts": ["p1", "p2"]})
        self.improver.benchmark_model.assert_called_once_with(
            "llama3", ["p1", "p2"])

    def test_benchmark_no_body(self):
        self.improver.benchmark_model.return_value = {"score": 0.0}
        r = self.client.post("/improve/benchmark")
        self.assertEqual(r.status_code, 200)

    def test_benchmark_exception_500(self):
        self.improver.benchmark_model.side_effect = RuntimeError("bm")
        r = self.client.post("/improve/benchmark", json={})
        self.assert500(r)

    def test_compare_default_models(self):
        self.improver.compare_models.return_value = {"winner": "a"}
        r = self.client.post("/improve/compare", json={})
        self.assertEqual(r.get_json(), {"winner": "a"})
        self.improver.compare_models.assert_called_once_with(
            ["qwen2.5:14b", "gpt-4o-mini"])

    def test_compare_custom_models(self):
        self.improver.compare_models.return_value = {}
        self.client.post("/improve/compare",
                         json={"models": ["m1", "m2"]})
        self.improver.compare_models.assert_called_once_with(
            ["m1", "m2"])

    def test_compare_exception_500(self):
        self.improver.compare_models.side_effect = RuntimeError("cm")
        r = self.client.post("/improve/compare", json={})
        self.assert500(r)

    def test_upgrades(self):
        self.improver.check_for_upgrades.return_value = ["up1"]
        r = self.client.get("/improve/upgrades")
        self.assertEqual(r.get_json(), ["up1"])

    def test_upgrades_exception_500(self):
        self.improver.check_for_upgrades.side_effect = RuntimeError("cu")
        r = self.client.get("/improve/upgrades")
        self.assert500(r)

    def test_apply_defaults(self):
        self.improver.apply_upgrade.return_value = {"ok": True}
        r = self.client.post("/improve/apply", json={})
        self.assertEqual(r.get_json(), {"ok": True})
        self.improver.apply_upgrade.assert_called_once_with(
            "chat", "")

    def test_apply_full_fields(self):
        self.improver.apply_upgrade.return_value = {}
        self.client.post("/improve/apply", json={
            "task_type": "code", "model": "deepseek"})
        self.improver.apply_upgrade.assert_called_once_with(
            "code", "deepseek")

    def test_apply_exception_500(self):
        self.improver.apply_upgrade.side_effect = RuntimeError("au")
        r = self.client.post("/improve/apply", json={})
        self.assert500(r)

    def test_rollback_default(self):
        self.improver.rollback.return_value = {"rolled": True}
        r = self.client.post("/improve/rollback", json={})
        self.assertEqual(r.get_json(), {"rolled": True})
        self.improver.rollback.assert_called_once_with("chat")

    def test_rollback_custom(self):
        self.improver.rollback.return_value = {}
        self.client.post("/improve/rollback",
                         json={"task_type": "code"})
        self.improver.rollback.assert_called_once_with("code")

    def test_rollback_exception_500(self):
        self.improver.rollback.side_effect = RuntimeError("rb")
        r = self.client.post("/improve/rollback", json={})
        self.assert500(r)

    def test_stats(self):
        self.improver.get_stats.return_value = {"upgrades": 3}
        r = self.client.get("/improve/stats")
        self.assertEqual(r.get_json(), {"upgrades": 3})

    def test_stats_exception_500(self):
        self.improver.get_stats.side_effect = RuntimeError("is")
        r = self.client.get("/improve/stats")
        self.assert500(r)

    def test_models(self):
        self.improver.get_current_models.return_value = {"chat": "a"}
        r = self.client.get("/improve/models")
        self.assertEqual(r.get_json(), {"chat": "a"})

    def test_models_exception_500(self):
        self.improver.get_current_models.side_effect = RuntimeError("gm")
        r = self.client.get("/improve/models")
        self.assert500(r)


class TestCoordinate(FinancialBase):
    def test_workflow_create_no_execute(self):
        self.coord.create_workflow.return_value = {"id": "w1"}
        r = self.client.post("/coordinate/workflow", json={
            "name": "build", "description": "d", "tasks": ["t1"]})
        self.assertEqual(r.get_json(), {"id": "w1"})
        self.coord.create_workflow.assert_called_once_with(
            name="build", description="d", tasks=["t1"])
        self.coord.execute_workflow.assert_not_called()

    def test_workflow_create_defaults(self):
        self.coord.create_workflow.return_value = {"id": "w2"}
        r = self.client.post("/coordinate/workflow", json={})
        self.assertEqual(r.get_json(), {"id": "w2"})
        self.coord.create_workflow.assert_called_once_with(
            name="unnamed", description="", tasks=[])

    def test_workflow_create_and_execute(self):
        self.coord.create_workflow.return_value = {"id": "w3"}
        self.coord.execute_workflow.return_value = {"status": "done"}
        r = self.client.post("/coordinate/workflow", json={
            "name": "n", "execute": True})
        body = r.get_json()
        self.assertEqual(body["execution"], {"status": "done"})
        self.coord.execute_workflow.assert_called_once_with("w3")

    def test_execute_flag_but_no_id_skips_execution(self):
        # execute=True but result lacks "id" -> no execute call
        self.coord.create_workflow.return_value = {"error": "dup"}
        r = self.client.post("/coordinate/workflow",
                             json={"execute": True})
        self.assertNotIn("execution", r.get_json())
        self.coord.execute_workflow.assert_not_called()

    def test_workflow_exception_500(self):
        self.coord.create_workflow.side_effect = RuntimeError("cw")
        r = self.client.post("/coordinate/workflow", json={})
        self.assert500(r)

    def test_execute_by_id(self):
        self.coord.execute_workflow.return_value = {"status": "ok"}
        r = self.client.post("/coordinate/execute/w1")
        self.assertEqual(r.get_json(), {"status": "ok"})
        self.coord.execute_workflow.assert_called_once_with("w1")

    def test_execute_exception_500(self):
        self.coord.execute_workflow.side_effect = RuntimeError("ex")
        r = self.client.post("/coordinate/execute/w1")
        self.assert500(r)

    def test_parallel_default_tasks(self):
        self.coord.run_parallel.return_value = {"done": 0}
        r = self.client.post("/coordinate/parallel", json={})
        self.assertEqual(r.get_json(), {"done": 0})
        self.coord.run_parallel.assert_called_once_with([])

    def test_parallel_with_tasks(self):
        self.coord.run_parallel.return_value = {}
        self.client.post("/coordinate/parallel",
                         json={"tasks": ["a", "b"]})
        self.coord.run_parallel.assert_called_once_with(["a", "b"])

    def test_parallel_exception_500(self):
        self.coord.run_parallel.side_effect = RuntimeError("pr")
        r = self.client.post("/coordinate/parallel", json={})
        self.assert500(r)

    def test_get_workflow(self):
        self.coord.get_workflow.return_value = {"id": "w1"}
        r = self.client.get("/coordinate/workflow/w1")
        self.assertEqual(r.get_json(), {"id": "w1"})
        self.coord.get_workflow.assert_called_once_with("w1")

    def test_get_workflow_exception_500(self):
        self.coord.get_workflow.side_effect = RuntimeError("gw")
        r = self.client.get("/coordinate/workflow/w1")
        self.assert500(r)

    def test_workflows_default_limit(self):
        self.coord.list_workflows.return_value = ["w1"]
        r = self.client.get("/coordinate/workflows")
        self.assertEqual(r.get_json(), ["w1"])
        self.coord.list_workflows.assert_called_once_with(10)

    def test_workflows_custom_limit(self):
        self.coord.list_workflows.return_value = []
        self.client.get("/coordinate/workflows?limit=2")
        self.coord.list_workflows.assert_called_once_with(2)

    def test_workflows_exception_500(self):
        self.coord.list_workflows.side_effect = RuntimeError("lw")
        r = self.client.get("/coordinate/workflows")
        self.assert500(r)

    def test_stats(self):
        self.coord.get_stats.return_value = {"workflows": 6}
        r = self.client.get("/coordinate/stats")
        self.assertEqual(r.get_json(), {"workflows": 6})

    def test_stats_exception_500(self):
        self.coord.get_stats.side_effect = RuntimeError("cs")
        r = self.client.get("/coordinate/stats")
        self.assert500(r)


class TestLazyImportFailure(FinancialBase):
    """Getter raising ImportError -> generic 500 + logged exception."""

    def test_cost_getter_raises(self):
        with patch(COST, side_effect=ImportError("no cost")):
            with self.assertLogs("orbit.core.financial_api_bp",
                                 level="ERROR"):
                r = self.client.get("/cost/stats")
        self.assert500(r)

    def test_tracker_getter_raises(self):
        with patch(TRACKER, side_effect=ImportError("no tracker")):
            r = self.client.get("/finance/stats")
        self.assert500(r)

    def test_orch_getter_raises(self):
        with patch(ORCH, side_effect=ImportError("no orch")):
            r = self.client.get("/orchestrate/stats")
        self.assert500(r)

    def test_improver_getter_raises(self):
        with patch(IMPROVER, side_effect=ImportError("no improver")):
            r = self.client.get("/improve/stats")
        self.assert500(r)

    def test_coord_getter_raises(self):
        with patch(COORD, side_effect=ImportError("no coord")):
            r = self.client.get("/coordinate/stats")
        self.assert500(r)


if __name__ == "__main__":
    unittest.main()
