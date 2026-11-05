"""Optional-blueprint failure visibility (review P2).

``server.py`` swallowed every optional-blueprint ImportError at DEBUG level —
no surface anywhere ("92 of 198 registrations fail silently"). Failures are
now aggregated in ``server._optional_failures`` (deduped by name) and exposed
via ``GET /api/health`` plus a one-line startup summary.
"""

import pytest

import orbit.orbit.server as server


@pytest.fixture
def snapshot():
    saved_failures = list(server._optional_failures)
    saved_blueprints = list(server._optional_blueprints)
    yield server._optional_failures
    server._optional_failures[:] = saved_failures
    server._optional_blueprints[:] = saved_blueprints


def test_record_missing_dedupes_by_name(snapshot):
    server._record_missing("foo_bp", ImportError("first"))
    server._record_missing("foo_bp", ImportError("second"))
    entries = [f for f in snapshot if f["name"] == "foo_bp"]
    assert len(entries) == 1
    assert "second" in entries[0]["error"]


def test_record_missing_keeps_distinct_names(snapshot):
    server._record_missing("a_bp", ImportError("a"))
    server._record_missing("b_bp", RuntimeError("b"))
    names = {f["name"] for f in snapshot}
    assert {"a_bp", "b_bp"} <= names


def test_try_import_failure_is_recorded(snapshot):
    def _boom():
        raise ImportError("no module named 'nope'")

    server._try_import(_boom, "fake_missing_bp")
    entry = next(f for f in snapshot if f["name"] == "fake_missing_bp")
    assert "no module named" in entry["error"]
    assert entry["error"].startswith("ImportError:")


def test_try_import_success_not_recorded_and_appended(snapshot):
    sentinel = object()
    server._try_import(lambda: sentinel, "fake_ok_bp")
    assert not any(f["name"] == "fake_ok_bp" for f in snapshot)
    assert sentinel in server._optional_blueprints


def test_health_exposes_blueprint_visibility():
    from orbit.orbit.server import create_app

    client = create_app().test_client()
    r = client.get("/api/health")
    assert r.status_code == 200
    bp = r.get_json()["blueprints"]
    assert bp["registered"] >= 100
    assert bp["optional_missing"] == len(bp["missing"])
    assert isinstance(bp["missing"], list)


def test_health_lists_simulated_missing_name(snapshot):
    from orbit.orbit.server import create_app

    server._record_missing("definitely_missing_bp", ImportError("simulated"))
    client = create_app().test_client()
    bp = client.get("/api/health").get_json()["blueprints"]
    assert "definitely_missing_bp" in bp["missing"]
    assert bp["optional_missing"] >= 1
