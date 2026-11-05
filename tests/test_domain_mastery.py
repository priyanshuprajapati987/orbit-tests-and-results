import json

import pytest

from orbit.orbit.core.domain_mastery import DATA_DIR, DomainMastery, get_domain_mastery

DOMAIN_NAME = "Research & Analysis"
DOMAIN_DESC = "Deep research, fact-checking, trend analysis, source synthesis"


@pytest.fixture(autouse=True)
def reset_domain():
    get_domain_mastery().reset()
    yield


class TestDomainMasteryCore:
    def test_import(self):
        assert DomainMastery is not None

    def test_singleton(self):
        a = get_domain_mastery()
        b = get_domain_mastery()
        assert a is b

    def test_register_domain(self):
        dm = get_domain_mastery()
        d = dm.register_domain(DOMAIN_NAME, DOMAIN_DESC, ["research", "analysis"])
        assert d["name"] == DOMAIN_NAME
        assert d["current_phase"] == "A"
        assert d["description"] == DOMAIN_DESC
        assert d["tags"] == ["research", "analysis"]
        assert d["id"].startswith("dm_")

    def test_register_duplicate(self):
        dm = get_domain_mastery()
        d1 = dm.register_domain(DOMAIN_NAME, "original")
        d2 = dm.register_domain(DOMAIN_NAME, "duplicate")
        assert d1["id"] == d2["id"]
        assert d2["description"] == "original"

    def test_get_domains_empty(self):
        dm = get_domain_mastery()
        assert dm.get_domains() == []

    def test_get_domains(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        assert len(dm.get_domains()) == 1

    def test_get_domain_found(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        d = dm.get_domain(DOMAIN_NAME)
        assert d is not None
        assert d["name"] == DOMAIN_NAME

    def test_get_domain_not_found(self):
        dm = get_domain_mastery()
        assert dm.get_domain("nonexistent") is None

    def test_add_knowledge(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        entry = dm.add_knowledge(
            DOMAIN_NAME,
            "Research Methods",
            "https://example.com",
            "article",
            "A guide",
            ["methodology"],
        )
        assert entry is not None
        assert entry["title"] == "Research Methods"
        assert entry["source"] == "https://example.com"
        assert entry["content_type"] == "article"
        assert entry["tags"] == ["methodology"]
        domain = dm.get_domain(DOMAIN_NAME)
        assert domain["stats"]["total_knowledge_entries"] == 1

    def test_add_knowledge_no_domain(self):
        dm = get_domain_mastery()
        assert dm.add_knowledge("nonexistent", "title", "source") is None

    def test_add_practice(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        p = dm.add_practice(DOMAIN_NAME, "Research task", 0.85, 1200, "Good results")
        assert p is not None
        assert p["task"] == "Research task"
        assert p["score"] == 0.85
        assert p["latency_ms"] == 1200
        domain = dm.get_domain(DOMAIN_NAME)
        assert domain["stats"]["total_practice_tasks"] == 1
        assert domain["stats"]["avg_accuracy"] == 0.85

    def test_add_practice_recalc(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        dm.add_practice(DOMAIN_NAME, "task1", 0.8, 1000)
        dm.add_practice(DOMAIN_NAME, "task2", 0.9, 500)
        dm.add_practice(DOMAIN_NAME, "task3", 0.7, 1500)
        domain = dm.get_domain(DOMAIN_NAME)
        assert domain["stats"]["total_practice_tasks"] == 3
        assert domain["stats"]["avg_accuracy"] == 0.8
        assert domain["stats"]["avg_latency_ms"] == 1000.0

    def test_add_practice_no_domain(self):
        dm = get_domain_mastery()
        assert dm.add_practice("nonexistent", "task", 0.5) is None

    def test_add_benchmark(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        b = dm.add_benchmark(
            DOMAIN_NAME, "Research Accuracy", 85.0, 100.0, {"precision": 0.9}
        )
        assert b is not None
        assert b["benchmark_name"] == "Research Accuracy"
        assert b["score"] == 85.0
        assert b["expert_score"] == 100.0
        assert b["gap"] == 15.0
        domain = dm.get_domain(DOMAIN_NAME)
        assert domain["stats"]["total_benchmarks"] == 1

    def test_add_benchmark_overall_score(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        dm.add_benchmark(DOMAIN_NAME, "B1", 90, 100)
        dm.add_benchmark(DOMAIN_NAME, "B2", 80, 100)
        domain = dm.get_domain(DOMAIN_NAME)
        assert domain["stats"]["overall_score"] == 0.85

    def test_add_insight(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        ins = dm.add_insight(
            DOMAIN_NAME,
            "Key Pattern",
            "Cross-referencing improves accuracy",
            "pattern",
            ["research"],
        )
        assert ins is not None
        assert ins["title"] == "Key Pattern"
        assert ins["category"] == "pattern"
        domain = dm.get_domain(DOMAIN_NAME)
        assert domain["stats"]["total_insights"] == 1

    def test_phase_advance_a_to_b(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "A"
        for i in range(9):
            dm.add_knowledge(DOMAIN_NAME, f"E{i}", "source")
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "A"
        dm.add_knowledge(DOMAIN_NAME, "E10", "source")
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "B"

    def test_phase_advance_b_to_c(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        for i in range(10):
            dm.add_knowledge(DOMAIN_NAME, f"E{i}", "source")
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "B"
        for i in range(49):
            dm.add_practice(DOMAIN_NAME, f"P{i}", 0.8, 100)
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "B"
        dm.add_practice(DOMAIN_NAME, "P50", 0.8, 100)
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "C"

    def test_phase_advance_c_to_d(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        for i in range(10):
            dm.add_knowledge(DOMAIN_NAME, f"E{i}", "source")
        for i in range(50):
            dm.add_practice(DOMAIN_NAME, f"P{i}", 0.8, 100)
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "C"
        dm.add_benchmark(DOMAIN_NAME, "B1", 85, 100)
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "C"
        dm.add_benchmark(DOMAIN_NAME, "B2", 95, 100)
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "D"

    def test_get_phase_progress(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        p = dm.get_phase_progress(DOMAIN_NAME)
        assert p is not None
        assert p["current_phase"] == "A"
        assert p["total_phases"] == 4
        assert p["progress_pct"] == 0.0

    def test_get_phase_progress_not_found(self):
        dm = get_domain_mastery()
        assert dm.get_phase_progress("nonexistent") is None

    def test_suggest_next_action_phase_a_empty(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        action = dm.suggest_next_action(DOMAIN_NAME)
        assert "10 entries" in action

    def test_suggest_next_action_phase_a_almost_ready(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        for i in range(9):
            dm.add_knowledge(DOMAIN_NAME, f"Entry {i}", "source")
        action = dm.suggest_next_action(DOMAIN_NAME)
        assert "9/10" in action

    def test_suggest_next_action_phase_b_practice_needed(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        for i in range(10):
            dm.add_knowledge(DOMAIN_NAME, f"E{i}", "source")
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "B"
        action = dm.suggest_next_action(DOMAIN_NAME)
        assert "50 tasks" in action

    def test_suggest_next_action_phase_b(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        for i in range(10):
            dm.add_knowledge(DOMAIN_NAME, f"E{i}", "source")
        assert dm.get_domain(DOMAIN_NAME)["current_phase"] == "B"
        action = dm.suggest_next_action(DOMAIN_NAME)
        assert "50 tasks" in action

    def test_suggest_next_action_phase_d_mastered(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        for i in range(10):
            dm.add_knowledge(DOMAIN_NAME, f"E{i}", "source")
        for i in range(50):
            dm.add_practice(DOMAIN_NAME, f"task{i}", 0.9, 100)
        for i in range(3):
            dm.add_insight(DOMAIN_NAME, f"I{i}", "content")
        dm.add_benchmark(DOMAIN_NAME, "B1", 95, 100)
        action = dm.suggest_next_action(DOMAIN_NAME)
        assert "mastered" in action.lower()

    def test_delete_domain(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        assert len(dm.get_domains()) == 1
        assert dm.delete_domain(DOMAIN_NAME) is True
        assert len(dm.get_domains()) == 0

    def test_delete_nonexistent(self):
        dm = get_domain_mastery()
        assert dm.delete_domain("nonexistent") is False

    def test_reset(self):
        dm = get_domain_mastery()
        dm.register_domain(DOMAIN_NAME)
        dm.add_knowledge(DOMAIN_NAME, "title", "source")
        dm.reset()
        assert dm.get_domains() == []


class TestDomainMasteryPersistence:
    @pytest.fixture(autouse=True)
    def clean_persistence(self):
        data_dir = DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(data_dir / "domains.json", "w") as f:
            json.dump([], f)
        yield

    def test_persistence(self):
        dm1 = get_domain_mastery()
        dm1.reset()
        dm1.register_domain(DOMAIN_NAME)
        dm1.add_knowledge(DOMAIN_NAME, "title", "source")
        dm1.add_practice(DOMAIN_NAME, "task", 0.85, 1000)
        dm1.add_benchmark(DOMAIN_NAME, "B1", 85, 100)
        dm1.add_insight(DOMAIN_NAME, "I1", "content")

        dm2 = get_domain_mastery()
        domains = dm2.get_domains()
        assert len(domains) == 1
        d = domains[0]
        assert d["name"] == DOMAIN_NAME
        assert len(d["knowledge_entries"]) == 1
        assert len(d["practice_tasks"]) == 1
        assert len(d["benchmarks"]) == 1
        assert len(d["insights"]) >= 1
