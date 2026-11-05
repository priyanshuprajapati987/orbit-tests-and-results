"""Security regression tests for the workflow engine condition evaluator.

Verifies the AST-whitelisted condition evaluator blocks sandbox escapes while
still handling legitimate context-based comparisons.
"""

import pytest

from orbit.orbit.core.workflow_engine import WorkflowEngine


@pytest.fixture
def engine(tmp_path):
    return WorkflowEngine(storage_file=str(tmp_path / "test_wf.json"))


class TestConditionEvaluator:
    def test_simple_comparison(self, engine):
        assert engine._evaluate_condition('context["cost"] > 5', {"cost": 10}) is True

    def test_boolean_combination(self, engine):
        cond = 'context["status"] == "done" and context["count"] >= 3'
        assert engine._evaluate_condition(cond, {"status": "done", "count": 5}) is True

    def test_boolean_combination_false(self, engine):
        cond = 'context["status"] == "done" and context["count"] >= 3'
        assert engine._evaluate_condition(cond, {"status": "done", "count": 2}) is False

    def test_context_get_fallback(self, engine):
        assert engine._evaluate_condition('context.get("x", 0) > 1', {"x": 2}) is True
        assert engine._evaluate_condition('context.get("x", 0) > 1', {}) is False

    def test_literal_true(self, engine):
        assert engine._evaluate_condition("True", {}) is True

    def test_literal_comparison(self, engine):
        assert engine._evaluate_condition("3 > 2", {}) is True

    def test_negation(self, engine):
        assert (
            engine._evaluate_condition('not context["flag"]', {"flag": False}) is True
        )

    def test_blocked_object_class_escape(self, engine):
        assert (
            engine._evaluate_condition("().__class__.__mro__[1].__subclasses__()", {})
            is False
        )

    def test_blocked_context_class_escape(self, engine):
        assert (
            engine._evaluate_condition(
                "context.__class__.__mro__[1].__subclasses__()", {}
            )
            is False
        )

    def test_blocked_import(self, engine):
        assert (
            engine._evaluate_condition('__import__("os").system("echo pwned")', {})
            is False
        )

    def test_blocked_open(self, engine):
        assert engine._evaluate_condition('open("/etc/passwd").read()', {}) is False

    def test_blocked_exec(self, engine):
        assert engine._evaluate_condition('exec("x=1")', {}) is False

    def test_blocked_attribute_chain(self, engine):
        assert engine._evaluate_condition("context.foo.bar", {}) is False

    def test_blocked_unknown_name(self, engine):
        assert engine._evaluate_condition("os.system('ls')", {}) is False

    def test_blocked_builtin_name(self, engine):
        assert engine._evaluate_condition("__builtins__['os']", {}) is False

    def test_invalid_syntax(self, engine):
        assert engine._evaluate_condition("context[", {}) is False

    def test_none_value(self, engine):
        assert engine._evaluate_condition("context is None", {}) is False

    def test_arithmetic(self, engine):
        assert (
            engine._evaluate_condition(
                "context['a'] + context['b'] > 3", {"a": 2, "b": 2}
            )
            is True
        )

    def test_no_crash_on_empty(self, engine):
        assert engine._evaluate_condition("", {}) is False

    def test_in_context_branching(self, engine):
        wf_id = engine.create_workflow("test", "sec test")
        engine.add_step(wf_id, "s1", "check", action="log", config={"message": "x"})
        assert wf_id in engine.workflows
