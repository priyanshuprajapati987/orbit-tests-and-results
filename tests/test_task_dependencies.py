"""
Unit tests for orbit.orbit.core.task_dependencies (previously 0% covered).

Covers dependency wiring, ready-task computation, topological ordering,
cycle detection, chains and status summaries.
"""

import pytest

from orbit.orbit.core import task_dependencies as td
from orbit.orbit.core.task_dependencies import (
    DependencyType,
    TaskDependencyManager,
    TaskNode,
)


@pytest.fixture
def manager():
    return TaskDependencyManager()


@pytest.fixture
def chain(manager):
    """a -> b -> c (c depends on b, b depends on a)."""
    for task_id in ("a", "b", "c"):
        manager.add_task(task_id, f"task {task_id}", "coder")
    manager.add_dependency("b", "a")
    manager.add_dependency("c", "b")
    return manager


class TestTaskNode:
    def test_defaults(self):
        node = TaskNode("t1", "build", "coder")
        assert node.status == "pending"
        assert node.dependencies == []
        assert node.dependents == []
        assert node.result is None
        assert node.started_at is None
        assert node.completed_at is None


class TestAddTask:
    def test_add_task_returns_node(self, manager):
        node = manager.add_task("t1", "build", "coder")
        assert node.task_id == "t1"
        assert node.agent_type == "coder"
        assert manager.tasks["t1"] is node

    def test_duplicate_add_returns_existing_node(self, manager):
        first = manager.add_task("t1", "build", "coder")
        second = manager.add_task("t1", "other", "tester")
        assert second is first
        assert len(manager.tasks) == 1


class TestAddDependency:
    def test_dependency_links_both_directions(self, manager):
        manager.add_task("a", "a", "coder")
        manager.add_task("b", "b", "coder")
        assert manager.add_dependency("b", "a") is True
        assert manager.tasks["b"].dependencies == [("a", DependencyType.FINISH_TO_START)]
        assert manager.tasks["a"].dependents == ["b"]

    def test_custom_dependency_type(self, manager):
        manager.add_task("a", "a", "coder")
        manager.add_task("b", "b", "coder")
        manager.add_dependency("b", "a", DependencyType.START_TO_START)
        assert manager.tasks["b"].dependencies[0][1] is DependencyType.START_TO_START

    def test_unknown_task_rejected(self, manager):
        manager.add_task("a", "a", "coder")
        assert manager.add_dependency("ghost", "a") is False

    def test_unknown_dependency_rejected(self, manager):
        manager.add_task("a", "a", "coder")
        assert manager.add_dependency("a", "ghost") is False

    def test_self_dependency_rejected(self, manager):
        manager.add_task("a", "a", "coder")
        assert manager.add_dependency("a", "a") is False
        assert manager.tasks["a"].dependencies == []

    def test_remove_dependency_clears_both_directions(self, chain):
        chain.remove_dependency("b", "a")
        assert chain.tasks["b"].dependencies == []
        assert chain.tasks["a"].dependents == []

    def test_remove_unknown_dependency_is_noop(self, chain):
        chain.remove_dependency("ghost", "a")
        chain.remove_dependency("b", "ghost")
        assert chain.tasks["b"].dependencies == [("a", DependencyType.FINISH_TO_START)]


class TestReadyTasks:
    def test_only_root_is_ready_initially(self, chain):
        assert chain.get_ready_tasks() == ["a"]

    def test_dependent_becomes_ready_after_completion(self, chain):
        chain.execute_task("a", result="done")
        assert chain.get_ready_tasks() == ["b"]

    def test_failed_dependency_blocks_dependents(self, chain):
        chain.execute_task("a", error="boom")
        assert chain.get_ready_tasks() == []

    def test_running_task_is_not_ready(self, chain):
        chain.execute_task("a")
        assert chain.get_ready_tasks() == []

    def test_independent_tasks_are_all_ready(self, manager):
        manager.add_task("a", "a", "coder")
        manager.add_task("b", "b", "coder")
        assert sorted(manager.get_ready_tasks()) == ["a", "b"]

    def test_missing_dependency_blocks_task(self, manager):
        manager.add_task("a", "a", "coder")
        manager.add_task("b", "b", "coder")
        manager.add_dependency("b", "a")
        del manager.tasks["a"]
        assert manager.get_ready_tasks() == []


class TestExecuteTask:
    def test_execute_without_result_marks_running(self, chain):
        chain.execute_task("a")
        assert chain.tasks["a"].status == "running"
        assert chain.tasks["a"].started_at is not None

    def test_execute_with_result_marks_completed(self, chain):
        chain.execute_task("a", result={"ok": True})
        node = chain.tasks["a"]
        assert node.status == "completed"
        assert node.result == {"ok": True}
        assert node.completed_at is not None

    def test_execute_with_error_marks_failed(self, chain):
        chain.execute_task("a", error="boom")
        node = chain.tasks["a"]
        assert node.status == "failed"
        assert node.result == {"error": "boom"}

    def test_error_takes_precedence_over_result(self, chain):
        chain.execute_task("a", result="ok", error="boom")
        assert chain.tasks["a"].status == "failed"

    def test_execute_unknown_task_is_noop(self, manager):
        manager.execute_task("ghost", result="x")
        assert manager.tasks == {}


class TestExecutionOrder:
    def test_dependencies_come_first(self, chain):
        assert chain.get_execution_order() == ["a", "b", "c"]

    def test_diamond_order_is_valid(self, manager):
        for task_id in ("a", "b", "c", "d"):
            manager.add_task(task_id, task_id, "coder")
        manager.add_dependency("b", "a")
        manager.add_dependency("c", "a")
        manager.add_dependency("d", "b")
        manager.add_dependency("d", "c")
        order = manager.get_execution_order()
        assert order.index("a") < order.index("b") < order.index("d")
        assert order.index("a") < order.index("c") < order.index("d")

    def test_order_includes_every_task_once(self, manager):
        for task_id in ("a", "b", "c"):
            manager.add_task(task_id, task_id, "coder")
        assert sorted(manager.get_execution_order()) == ["a", "b", "c"]

    def test_order_is_stable_across_calls(self, chain):
        assert chain.get_execution_order() == chain.get_execution_order()

    def test_cycle_does_not_hang_ordering(self, manager):
        manager.add_task("a", "a", "coder")
        manager.add_task("b", "b", "coder")
        manager.add_dependency("b", "a")
        manager.add_dependency("a", "b")
        assert sorted(manager.get_execution_order()) == ["a", "b"]


class TestCycleDetection:
    def test_no_cycles_in_dag(self, chain):
        assert chain.detect_cycles() == []

    def test_two_task_cycle_detected(self, manager):
        manager.add_task("a", "a", "coder")
        manager.add_task("b", "b", "coder")
        manager.add_dependency("b", "a")
        manager.add_dependency("a", "b")
        cycles = manager.detect_cycles()
        assert cycles
        assert set(cycles[0]) == {"a", "b"}

    def test_three_task_cycle_detected(self, manager):
        for task_id in ("a", "b", "c"):
            manager.add_task(task_id, task_id, "coder")
        manager.add_dependency("b", "a")
        manager.add_dependency("c", "b")
        manager.add_dependency("a", "c")
        assert manager.detect_cycles()

    def test_empty_manager_has_no_cycles(self, manager):
        assert manager.detect_cycles() == []


class TestChainsAndGroups:
    def test_chain_lists_dependencies_before_task(self, chain):
        assert chain.get_task_chain("c") == ["a", "b", "c"]

    def test_chain_of_root_task(self, chain):
        assert chain.get_task_chain("a") == ["a"]

    def test_chain_of_unknown_task(self, manager):
        assert manager.get_task_chain("ghost") == ["ghost"]

    def test_independent_tasks_grouped_together(self, manager):
        manager.add_task("a", "a", "coder")
        manager.add_task("b", "b", "coder")
        assert manager.get_parallel_groups() == [["a", "b"]]

    def test_dependent_task_gets_own_group(self, chain):
        groups = chain.get_parallel_groups()
        assert groups[0] == ["a"]
        assert ["b"] in groups
        assert ["c"] in groups

    def test_no_tasks_yields_no_groups(self, manager):
        assert manager.get_parallel_groups() == []


class TestStatusSummary:
    def test_summary_of_fresh_chain(self, chain):
        summary = chain.get_status_summary()
        assert summary["total_tasks"] == 3
        assert summary["status_counts"]["pending"] == 3
        assert summary["ready_tasks"] == ["a"]
        assert summary["has_cycles"] is False

    def test_summary_tracks_mixed_statuses(self, chain):
        chain.execute_task("a", result="ok")
        chain.execute_task("b", error="boom")
        counts = chain.get_status_summary()["status_counts"]
        assert counts["completed"] == 1
        assert counts["failed"] == 1
        assert counts["pending"] == 1

    def test_summary_flags_cycles(self, manager):
        manager.add_task("a", "a", "coder")
        manager.add_task("b", "b", "coder")
        manager.add_dependency("b", "a")
        manager.add_dependency("a", "b")
        assert manager.get_status_summary()["has_cycles"] is True


class TestModuleLevelApi:
    @pytest.fixture(autouse=True)
    def _isolated_singleton(self, monkeypatch):
        monkeypatch.setattr(td, "_task_dep_manager", TaskDependencyManager())

    def test_get_manager_is_singleton(self):
        assert td.get_task_dependency_manager() is td.get_task_dependency_manager()

    def test_add_task_and_dependency(self):
        td.add_task("a", "a", "coder")
        td.add_task("b", "b", "coder")
        assert td.add_dependency("b", "a") is True
        assert td.get_ready_tasks() == ["a"]

    def test_execute_and_order(self):
        td.add_task("a", "a", "coder")
        td.add_task("b", "b", "coder")
        td.add_dependency("b", "a")
        td.execute_task("a", result="ok")
        assert td.get_execution_order() == ["a", "b"]
        assert td.get_status_summary()["ready_tasks"] == ["b"]
