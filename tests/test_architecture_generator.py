"""Tests for Architecture Generator (System 12)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.core.architecture_generator import (
    ArchitecturePlan,
    _deep_merge_tree,
    _generate_model_files,
    _generate_routes_tree,
    get_architecture_generator,
)

FLASK_SPEC = {
    "project_name": "auth_api",
    "description": "User authentication API with JWT",
    "tech_stack": ["Python", "Flask", "SQLAlchemy", "PostgreSQL", "PyJWT", "pytest"],
    "dependencies": ["flask", "sqlalchemy", "psycopg2-binary", "pyjwt", "pytest"],
    "entities": {
        "endpoints": [
            {"method": "POST", "path": "/auth/login", "purpose": "User login"},
            {
                "method": "POST",
                "path": "/auth/register",
                "purpose": "User registration",
            },
        ],
        "models": [
            {
                "name": "User",
                "fields": [
                    {"name": "id", "type": "int", "primary_key": True},
                    {"name": "email", "type": "string", "unique": True},
                    {"name": "password_hash", "type": "string"},
                ],
            },
        ],
        "features": ["JWT authentication", "Password hashing", "Rate limiting"],
        "auth_type": "jwt",
        "database": "postgresql",
        "framework": "flask",
    },
    "parsed_at": "2026-07-30T10:00:00",
}

FASTAPI_SPEC = {
    "project_name": "fastapi_crud",
    "description": "FastAPI CRUD API",
    "tech_stack": ["Python", "FastAPI", "PostgreSQL", "SQLAlchemy", "pytest"],
    "dependencies": ["fastapi", "uvicorn", "sqlalchemy", "psycopg2-binary", "pytest"],
    "entities": {
        "endpoints": [
            {"method": "POST", "path": "/api/products", "purpose": "Create product"},
            {"method": "GET", "path": "/api/products", "purpose": "List products"},
        ],
        "models": [
            {
                "name": "Product",
                "fields": [
                    {"name": "id", "type": "int", "primary_key": True},
                    {"name": "name", "type": "string"},
                    {"name": "price", "type": "float"},
                ],
            },
        ],
        "features": ["RESTful API", "Pagination support"],
        "auth_type": "none",
        "database": "postgresql",
        "framework": "fastapi",
    },
    "parsed_at": "2026-07-30T10:00:00",
}


class TestArchitectureGenerator:
    def test_singleton(self):
        g1 = get_architecture_generator()
        g2 = get_architecture_generator()
        assert g1 is g2

    def test_generate_flask_basic(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        assert result["project_name"] == "auth_api"
        assert result["pattern_name"] == "MVC Layered"
        assert len(result["components"]) > 0
        assert result["directory_tree"] is not None

    def test_generate_fastapi(self):
        gen = get_architecture_generator()
        result = gen.generate(FASTAPI_SPEC)
        assert result["project_name"] == "fastapi_crud"
        assert result["pattern_name"] == "REST Layered"
        assert len(result["components"]) > 0

    def test_generated_components_include_auth(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        names = [c["name"] for c in result["components"]]
        assert "AuthMiddleware" in names
        assert "UserModel" in names

    def test_generated_components_include_test_suite(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        names = [c["name"] for c in result["components"]]
        assert "TestSuite" in names

    def test_data_flow_has_steps(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        assert len(result["data_flow"]) >= 3
        steps = [f["step"] for f in result["data_flow"]]
        assert sorted(steps) == steps

    def test_data_flow_includes_auth(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        auth_steps = [
            f
            for f in result["data_flow"]
            if "auth" in str(f).lower() or "token" in str(f).lower()
        ]
        assert len(auth_steps) > 0

    def test_design_decisions_not_empty(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        assert len(result["design_decisions"]) > 0

    def test_design_decisions_include_framework(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        combined = " ".join(result["design_decisions"]).lower()
        assert "flask" in combined

    def test_directory_tree_has_src(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        tree = result["directory_tree"]
        assert "src/" in tree or "app/" in tree

    def test_directory_tree_for_fastapi_has_app(self):
        gen = get_architecture_generator()
        result = gen.generate(FASTAPI_SPEC)
        assert "app/" in result["directory_tree"]

    def test_module_dependencies_not_empty(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        assert len(result["module_dependencies"]) > 0

    def test_module_dependencies_structured(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        for dep in result["module_dependencies"]:
            assert "from" in dep
            assert "to" in dep
            assert "type" in dep

    def test_generated_at_present(self):
        gen = get_architecture_generator()
        result = gen.generate(FLASK_SPEC)
        assert "generated_at" in result
        assert len(result["generated_at"]) > 0

    def test_get_plan_existing(self):
        gen = get_architecture_generator()
        gen.generate(
            FLASK_SPEC,
        )
        plan = gen.get_plan("auth_api")
        assert plan is not None
        assert plan["project_name"] == "auth_api"

    def test_get_plan_missing(self):
        gen = get_architecture_generator()
        plan = gen.get_plan("nonexistent")
        assert plan is None

    def test_list_plans(self):
        gen = get_architecture_generator()
        gen.reset()
        gen.generate(FLASK_SPEC)
        gen.generate(FASTAPI_SPEC)
        plans = gen.list_plans()
        assert "auth_api" in plans
        assert "fastapi_crud" in plans

    def test_reset(self):
        gen = get_architecture_generator()
        gen.generate(FLASK_SPEC)
        gen.reset()
        assert gen.list_plans() == []

    def test_empty_list(self):
        gen = get_architecture_generator()
        gen.reset()
        assert gen.list_plans() == []


class TestDeepMergeTree:
    def test_merge_additions(self):
        base = {"src/": {"type": "dir", "children": {"main.py": {"type": "file"}}}}
        additions = {
            "src/": {"type": "dir", "children": {"extra.py": {"type": "file"}}}
        }
        merged = _deep_merge_tree(base, additions)
        assert "main.py" in merged["src/"]["children"]
        assert "extra.py" in merged["src/"]["children"]

    def test_merge_with_override(self):
        base = {"old.py": {"type": "file", "desc": "old"}}
        additions = {"new.py": {"type": "file", "desc": "new"}}
        merged = _deep_merge_tree(base, additions)
        assert "old.py" in merged
        assert "new.py" in merged

    def test_merge_desc_preserved(self):
        base = {"dir/": {"type": "dir", "children": {}, "desc": "base desc"}}
        additions = {"dir/": {"type": "dir", "children": {"f.py": {"type": "file"}}}}
        merged = _deep_merge_tree(base, additions)
        assert merged["dir/"]["desc"] == "base desc"
        assert "f.py" in merged["dir/"]["children"]


class TestGenerateRoutesTree:
    def test_flask_routes(self):
        endpoints = [{"method": "POST", "path": "/auth/login", "purpose": "Login"}]
        result = _generate_routes_tree(endpoints, "flask")
        assert any("routes/" in k for k in result)

    def test_fastapi_routes(self):
        endpoints = [{"method": "GET", "path": "/api/products", "purpose": "List"}]
        result = _generate_routes_tree(endpoints, "fastapi")
        assert any("app/api/v1/" in k for k in result)

    def test_empty_endpoints(self):
        result = _generate_routes_tree([], "flask")
        assert result == {}


class TestGenerateModelFiles:
    def test_flask_models(self):
        models = [{"name": "User", "fields": [{"name": "id", "type": "int"}]}]
        result = _generate_model_files(models, "flask")
        assert any("models/user.py" in k for k in result)

    def test_fastapi_models(self):
        models = [{"name": "Product", "fields": [{"name": "id", "type": "int"}]}]
        result = _generate_model_files(models, "fastapi")
        assert any("app/models/product.py" in k for k in result)
        assert any("app/schemas/product.py" in k for k in result)

    def test_django_models(self):
        models = [{"name": "User", "fields": [{"name": "id", "type": "int"}]}]
        result = _generate_model_files(models, "django")
        assert any("apps/user/" in k for k in result)

    def test_empty_models(self):
        result = _generate_model_files([], "flask")
        assert result == {}


class TestArchitecturePlan:
    def test_default_fields(self):
        plan = ArchitecturePlan(project_name="test")
        assert plan.project_name == "test"
        assert plan.components == []
        assert plan.data_flow == []
        assert plan.design_decisions == []
        assert plan.module_dependencies == []
        assert plan.generated_at is not None

    def test_default_pattern(self):
        plan = ArchitecturePlan()
        assert plan.pattern_name == ""
        assert plan.pattern_desc == ""
