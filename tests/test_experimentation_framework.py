import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.core.experimentation_framework import (
    get_experimentation_framework,
)


@pytest.fixture(autouse=True)
def reset_framework():
    get_experimentation_framework().reset()
    yield


def _ef():
    return get_experimentation_framework()


# --- Core Engine Tests ---


class TestExperimentationFrameworkEngine:
    def test_create_experiment(self):
        exp = _ef().create_experiment("Test", "general", "base prompt", 10)
        assert exp["name"] == "Test"
        assert exp["task_type"] == "general"
        assert exp["base_prompt"] == "base prompt"
        assert exp["traffic_pct"] == 10
        assert exp["status"] == "draft"
        assert "id" in exp
        assert exp["control_score"] == 0.0
        assert len(exp["variants"]) == 0

    def test_create_experiment_minimal(self):
        exp = _ef().create_experiment("Min", "chat", "hello")
        assert exp["name"] == "Min"
        assert exp["task_type"] == "chat"
        assert exp["traffic_pct"] == 10

    def test_get_experiments_all(self):
        _ef().create_experiment("A", "g", "p", 10)
        _ef().create_experiment("B", "g", "p", 20)
        exps = _ef().get_experiments()
        assert len(exps) == 2

    def test_get_experiments_by_status(self):
        _ef().create_experiment("A", "g", "p", 10)
        exp2 = _ef().create_experiment("B", "g", "p", 20)
        _ef().add_variant(exp2["id"], "v", "v1")
        _ef().activate_experiment(exp2["id"])
        assert len(_ef().get_experiments("active")) == 1
        assert len(_ef().get_experiments("draft")) == 1

    def test_get_experiment_by_id(self):
        exp = _ef().create_experiment("X", "g", "p", 10)
        found = _ef().get_experiment(exp["id"])
        assert found is not None
        assert found["id"] == exp["id"]

    def test_get_experiment_not_found(self):
        assert _ef().get_experiment("nonexistent") is None

    def test_add_variant(self):
        exp = _ef().create_experiment("V", "g", "base", 10)
        var = _ef().add_variant(exp["id"], "variant prompt", "v1")
        assert var is not None
        assert var["prompt"] == "variant prompt"
        assert var["label"] == "v1"
        updated = _ef().get_experiment(exp["id"])
        assert len(updated["variants"]) == 1

    def test_add_variant_auto_label(self):
        exp = _ef().create_experiment("V", "g", "base", 10)
        var = _ef().add_variant(exp["id"], "variant prompt")
        assert var["label"] == "Variant 1"
        var2 = _ef().add_variant(exp["id"], "another")
        assert var2["label"] == "Variant 2"

    def test_add_variant_no_exp(self):
        assert _ef().add_variant("badid", "p") is None

    def test_activate_experiment(self):
        exp = _ef().create_experiment("A", "g", "p", 10)
        _ef().add_variant(exp["id"], "v", "v1")
        assert _ef().activate_experiment(exp["id"]) is True
        updated = _ef().get_experiment(exp["id"])
        assert updated["status"] == "active"

    def test_activate_no_variants(self):
        exp = _ef().create_experiment("A", "g", "p", 10)
        assert _ef().activate_experiment(exp["id"]) is False

    def test_activate_not_found(self):
        assert _ef().activate_experiment("badid") is False

    def test_pause_experiment(self):
        exp = _ef().create_experiment("A", "g", "p", 10)
        _ef().add_variant(exp["id"], "v", "v1")
        _ef().activate_experiment(exp["id"])
        assert _ef().pause_experiment(exp["id"]) is True
        assert _ef().get_experiment(exp["id"])["status"] == "paused"

    def test_pause_not_found(self):
        assert _ef().pause_experiment("badid") is False

    def test_route_prompt_no_active(self):
        prompt, exp_id, var_id = _ef().route_prompt("general", "hello")
        assert prompt == "hello"
        assert exp_id is None
        assert var_id is None

    def test_route_prompt_no_match(self):
        _ef().create_experiment("A", "research", "base", 10)
        prompt, exp_id, _var_id = _ef().route_prompt("general", "hello")
        assert prompt == "hello"
        assert exp_id is None

    def test_route_prompt_hit(self):
        exp = _ef().create_experiment("A", "general", "base", 100)
        _ef().add_variant(exp["id"], "variant a", "a")
        _ef().activate_experiment(exp["id"])
        prompt, exp_id, var_id = _ef().route_prompt("general", "hello")
        assert exp_id == exp["id"]
        assert var_id is not None
        assert var_id != "control"  # 100% traffic should always get variant
        assert prompt.startswith("variant a")  # variant prompt returned

    def test_record_result(self):
        exp = _ef().create_experiment("A", "general", "base", 10)
        var = _ef().add_variant(exp["id"], "variant a", "a")
        ok = _ef().record_result(exp["id"], var["id"], 0.85, 100, True)
        assert ok is True
        updated = _ef().get_experiment(exp["id"])
        v = next(v for v in updated["variants"] if v["id"] == var["id"])
        assert v["trials"] == 1
        assert v["avg_score"] == 0.85
        assert v["avg_latency"] == 100.0

    def test_record_result_multiple(self):
        exp = _ef().create_experiment("A", "general", "base", 10)
        var = _ef().add_variant(exp["id"], "variant a", "a")
        for score in [0.8, 0.9, 0.85]:
            _ef().record_result(exp["id"], var["id"], score, 100, True)
        updated = _ef().get_experiment(exp["id"])
        v = next(v for v in updated["variants"] if v["id"] == var["id"])
        assert v["trials"] == 3
        assert abs(v["avg_score"] - 0.85) < 0.01

    def test_record_result_no_exp(self):
        assert _ef().record_result("bad", "v", 0.5, 0, True) is False

    def test_record_control(self):
        exp = _ef().create_experiment("A", "general", "base", 10)
        ok = _ef().record_result(exp["id"], "control", 0.7, 200, True)
        assert ok is True
        updated = _ef().get_experiment(exp["id"])
        assert updated["control_trials"] == 1
        assert updated["control_score"] == 0.7

    def test_auto_promotion(self):
        exp = _ef().create_experiment("A", "general", "base", 10)
        var = _ef().add_variant(exp["id"], "variant a", "a")
        _ef().activate_experiment(exp["id"])
        # Record control as bad (20 trials to meet MIN_TRIALS_FOR_PROMOTION)
        for _ in range(20):
            _ef().record_result(exp["id"], "control", 0.3, 200, True)
        # Record variant as good (20 trials)
        for _ in range(20):
            _ef().record_result(exp["id"], var["id"], 0.9, 100, True)
        updated = _ef().get_experiment(exp["id"])
        assert updated["winner"] == var["id"]
        assert updated["status"] == "promoted"

    def test_get_stats(self):
        _ef().create_experiment("A", "g", "p", 10)
        exp2 = _ef().create_experiment("B", "g", "p", 10)
        _ef().add_variant(exp2["id"], "v", "v1")
        _ef().activate_experiment(exp2["id"])
        _ef().record_result(exp2["id"], "control", 0.5, 100, True)
        stats = _ef().get_stats()
        assert stats["total_experiments"] >= 2
        assert stats["active_experiments"] >= 1
        assert stats["total_trials"] == 1

    def test_delete_experiment(self):
        exp = _ef().create_experiment("A", "g", "p", 10)
        assert _ef().delete_experiment(exp["id"]) is True
        assert _ef().get_experiment(exp["id"]) is None
        assert len(_ef().get_experiments()) == 0

    def test_delete_not_found(self):
        assert _ef().delete_experiment("badid") is False

    def test_reset(self):
        _ef().create_experiment("A", "g", "p", 10)
        _ef().reset()
        assert len(_ef().get_experiments()) == 0


# --- Flask API Tests ---


@pytest.fixture
def client():
    from flask import Flask

    from orbit.orbit.core.experimentation_framework_bp import (
        experimentation_framework_bp,
    )

    app = Flask(__name__)
    app.register_blueprint(experimentation_framework_bp)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestExperimentationFrameworkAPI:
    def test_list_empty(self, client):
        resp = client.get("/api/experiments")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["experiments"] == []

    def test_create(self, client):
        resp = client.post(
            "/api/experiments",
            json={
                "name": "Test",
                "task_type": "general",
                "base_prompt": "base",
                "traffic_pct": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Test"
        assert data["status"] == "draft"

    def test_create_with_variants(self, client):
        resp = client.post(
            "/api/experiments",
            json={
                "name": "Test",
                "task_type": "general",
                "base_prompt": "base",
                "traffic_pct": 10,
                "variants": [{"prompt": "var1", "label": "v1"}],
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["variants"]) == 1

    def test_detail(self, client):
        exp = _ef().create_experiment("X", "g", "p", 10)
        resp = client.get(f"/api/experiments/{exp['id']}")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "X"

    def test_detail_not_found(self, client):
        resp = client.get("/api/experiments/nonexistent")
        assert resp.status_code == 404

    def test_activate(self, client):
        exp = _ef().create_experiment("X", "g", "p", 10)
        _ef().add_variant(exp["id"], "var", "v1")
        resp = client.post(f"/api/experiments/{exp['id']}/activate")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_pause(self, client):
        exp = _ef().create_experiment("X", "g", "p", 10)
        _ef().add_variant(exp["id"], "v", "v1")
        _ef().activate_experiment(exp["id"])
        resp = client.post(f"/api/experiments/{exp['id']}/pause")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_add_variant_api(self, client):
        exp = _ef().create_experiment("X", "g", "p", 10)
        resp = client.post(
            f"/api/experiments/{exp['id']}/variants",
            json={"prompt": "var", "label": "v1"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["label"] == "v1"

    def test_add_variant_api_not_found(self, client):
        resp = client.post("/api/experiments/bad/variants", json={"prompt": "var"})
        assert resp.status_code == 404

    def test_generate_variants(self, client):
        exp = _ef().create_experiment("X", "general", "base prompt", 10)
        resp = client.post(
            f"/api/experiments/{exp['id']}/generate-variants", json={"count": 2}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["variants"]) == 2

    def test_route(self, client):
        exp = _ef().create_experiment("X", "general", "base", 100)
        _ef().add_variant(exp["id"], "var a", "a")
        _ef().activate_experiment(exp["id"])
        resp = client.post(
            "/api/experiments/route", json={"task_type": "general", "prompt": "hello"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["experiment_id"] == exp["id"]

    def test_route_no_match(self, client):
        resp = client.post(
            "/api/experiments/route", json={"task_type": "general", "prompt": "hello"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["experiment_id"] is None
        assert data["prompt"] == "hello"

    def test_record(self, client):
        exp = _ef().create_experiment("X", "g", "p", 10)
        var = _ef().add_variant(exp["id"], "var", "v1")
        resp = client.post(
            "/api/experiments/record",
            json={
                "experiment_id": exp["id"],
                "variant_id": var["id"],
                "score": 0.9,
                "latency_ms": 50,
                "success": True,
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_stats(self, client):
        resp = client.get("/api/experiments/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_experiments" in data

    def test_delete(self, client):
        exp = _ef().create_experiment("X", "g", "p", 10)
        resp = client.delete(f"/api/experiments/{exp['id']}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_reset(self, client):
        _ef().create_experiment("X", "g", "p", 10)
        resp = client.post("/api/experiments/reset")
        assert resp.status_code == 200
        assert len(_ef().get_experiments()) == 0

    def test_list_filter_status(self, client):
        exp = _ef().create_experiment("X", "g", "p", 10)
        _ef().add_variant(exp["id"], "v", "v1")
        _ef().activate_experiment(exp["id"])
        resp = client.get("/api/experiments?status=active")
        assert resp.status_code == 200
        assert len(resp.get_json()["experiments"]) == 1


class TestExperimentationFrameworkIntegration:
    def test_full_workflow(self, client):
        # Create
        resp = client.post(
            "/api/experiments",
            json={
                "name": "Integration Test",
                "task_type": "research",
                "base_prompt": "Research the following topic:",
                "traffic_pct": 100,
            },
        )
        exp = resp.get_json()
        eid = exp["id"]
        assert exp["status"] == "draft"

        # Add variant
        resp = client.post(
            f"/api/experiments/{eid}/variants",
            json={
                "prompt": "Investigate the following topic thoroughly:",
                "label": "detailed",
            },
        )
        assert resp.status_code == 200

        # Activate
        resp = client.post(f"/api/experiments/{eid}/activate")
        assert resp.get_json()["success"] is True

        # Route (100% traffic for deterministic test)
        resp = client.post(
            "/api/experiments/route",
            json={
                "task_type": "research",
                "prompt": "AI safety",
            },
        )
        route_data = resp.get_json()
        assert route_data["experiment_id"] == eid
        assert route_data["variant_id"] is not None
        assert route_data["variant_id"] != "control"

        # Record results
        for _ in range(3):
            client.post(
                "/api/experiments/record",
                json={
                    "experiment_id": eid,
                    "variant_id": route_data["variant_id"],
                    "score": 0.85,
                    "latency_ms": 120,
                    "success": True,
                },
            )
        client.post(
            "/api/experiments/record",
            json={
                "experiment_id": eid,
                "variant_id": "control",
                "score": 0.5,
                "latency_ms": 200,
                "success": True,
            },
        )

        # Stats
        resp = client.get("/api/experiments/stats")
        stats = resp.get_json()
        assert stats["total_trials"] >= 4

        # Detail
        resp = client.get(f"/api/experiments/{eid}")
        detail = resp.get_json()
        v = detail["variants"][0]
        assert v["trials"] >= 3
        assert v["avg_score"] > 0.8
