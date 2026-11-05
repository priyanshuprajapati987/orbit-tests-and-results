"""Tests for Code Generator (System 13)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.core.code_generator import (
    CodeGenerationResult,
    GeneratedFile,
    _camel,
    _model_fields_to_pydantic,
    _model_fields_to_sql,
    _snake,
    _template_config,
    _template_model,
    get_code_generator,
)

FLASK_ARCH = {
    "project_name": "auth_api",
    "pattern_name": "MVC Layered",
    "directory_tree": {},
    "components": [],
    "data_flow": [],
    "design_decisions": [],
    "module_dependencies": [],
}

FLASK_SPEC = {
    "project_name": "auth_api",
    "entities": {
        "framework": "flask",
        "database": "postgresql",
        "auth_type": "jwt",
        "models": [
            {
                "name": "User",
                "fields": [
                    {"name": "id", "type": "int", "primary_key": True},
                    {
                        "name": "email",
                        "type": "string",
                        "unique": True,
                        "required": True,
                    },
                    {"name": "password_hash", "type": "string", "required": True},
                ],
            },
        ],
        "endpoints": [
            {
                "method": "POST",
                "path": "/auth/login",
                "purpose": "User login",
                "requires_auth": False,
            },
            {
                "method": "POST",
                "path": "/auth/register",
                "purpose": "User registration",
                "requires_auth": False,
            },
        ],
        "features": ["JWT authentication"],
    },
    "dependencies": ["flask", "sqlalchemy", "psycopg2-binary", "pyjwt"],
}

FASTAPI_ARCH = {
    "project_name": "fastapi_crud",
    "pattern_name": "REST Layered",
    "directory_tree": {},
    "components": [],
    "data_flow": [],
    "design_decisions": [],
    "module_dependencies": [],
}

FASTAPI_SPEC = {
    "project_name": "fastapi_crud",
    "entities": {
        "framework": "fastapi",
        "database": "postgresql",
        "auth_type": "none",
        "models": [
            {
                "name": "Product",
                "fields": [
                    {"name": "id", "type": "int", "primary_key": True},
                    {"name": "name", "type": "string", "required": True},
                    {"name": "price", "type": "float", "required": True},
                ],
            },
        ],
        "endpoints": [
            {"method": "GET", "path": "/api/products", "purpose": "List products"},
            {"method": "POST", "path": "/api/products", "purpose": "Create product"},
        ],
        "features": [],
    },
    "dependencies": ["fastapi", "uvicorn", "sqlalchemy"],
}


class TestCodeGenerator:
    def test_singleton(self):
        g1 = get_code_generator()
        g2 = get_code_generator()
        assert g1 is g2

    def test_generate_flask(self):
        gen = get_code_generator()
        result = gen.generate(FLASK_ARCH, FLASK_SPEC)
        assert result["project_name"] == "auth_api"
        assert len(result["files"]) > 0
        assert result["lines_of_code"] > 0

    def test_generate_fastapi(self):
        gen = get_code_generator()
        result = gen.generate(FASTAPI_ARCH, FASTAPI_SPEC)
        assert result["project_name"] == "fastapi_crud"
        assert len(result["files"]) > 0

    def test_flask_has_config(self):
        gen = get_code_generator()
        result = gen.generate(FLASK_ARCH, FLASK_SPEC)
        paths = [f["path"] for f in result["files"]]
        assert "src/config.py" in paths
        assert "src/__init__.py" in paths

    def test_flask_has_model(self):
        gen = get_code_generator()
        result = gen.generate(FLASK_ARCH, FLASK_SPEC)
        paths = [f["path"] for f in result["files"]]
        assert any("models/user.py" in p for p in paths)

    def test_flask_has_routes(self):
        gen = get_code_generator()
        result = gen.generate(FLASK_ARCH, FLASK_SPEC)
        paths = [f["path"] for f in result["files"]]
        assert any("routes/" in p for p in paths)

    def test_flask_has_tests(self):
        gen = get_code_generator()
        result = gen.generate(FLASK_ARCH, FLASK_SPEC)
        paths = [f["path"] for f in result["files"]]
        assert any("tests/" in p for p in paths)

    def test_fastapi_has_main(self):
        gen = get_code_generator()
        result = gen.generate(FASTAPI_ARCH, FASTAPI_SPEC)
        paths = [f["path"] for f in result["files"]]
        assert "app/main.py" in paths
        assert "app/config.py" in paths

    def test_fastapi_has_schemas(self):
        gen = get_code_generator()
        result = gen.generate(FASTAPI_ARCH, FASTAPI_SPEC)
        paths = [f["path"] for f in result["files"]]
        assert any("models/product.py" in p for p in paths)

    def test_generated_code_contains_imports(self):
        gen = get_code_generator()
        result = gen.generate(FLASK_ARCH, FLASK_SPEC)
        content = result["files"][0]["content"]
        assert "import" in content

    def test_get_result_existing(self):
        gen = get_code_generator()
        gen.generate(FLASK_ARCH, FLASK_SPEC)
        res = gen.get_result("auth_api")
        assert res is not None
        assert res["project_name"] == "auth_api"

    def test_get_result_missing(self):
        gen = get_code_generator()
        res = gen.get_result("nonexistent")
        assert res is None

    def test_list_results(self):
        gen = get_code_generator()
        gen.reset()
        gen.generate(FLASK_ARCH, FLASK_SPEC)
        gen.generate(FASTAPI_ARCH, FASTAPI_SPEC)
        results = gen.list_results()
        assert "auth_api" in results
        assert "fastapi_crud" in results

    def test_reset(self):
        gen = get_code_generator()
        gen.generate(FLASK_ARCH, FLASK_SPEC)
        gen.reset()
        assert gen.list_results() == []

    def test_empty_list(self):
        gen = get_code_generator()
        gen.reset()
        assert gen.list_results() == []


class TestCodeGenerationResult:
    def test_default_fields(self):
        r = CodeGenerationResult(project_name="test")
        assert r.project_name == "test"
        assert r.files == []
        assert r.lines_of_code == 0
        assert r.error is None


class TestGeneratedFile:
    def test_default_language(self):
        f = GeneratedFile(path="test.py", content="x = 1")
        assert f.language == "python"

    def test_custom_language(self):
        f = GeneratedFile(path="test.js", content="x = 1", language="javascript")
        assert f.language == "javascript"


class TestHelpers:
    def test_camel(self):
        assert _camel("user") == "User"
        assert _camel("user_profile") == "UserProfile"
        assert _camel("user-profile") == "UserProfile"

    def test_snake(self):
        assert _snake("User") == "user"
        assert _snake("UserProfile") == "userprofile"
        assert _snake("my var Name") == "my_var_name"

    def test_model_fields_to_sql(self):
        fields = [
            {"name": "id", "type": "int", "primary_key": True},
            {"name": "email", "type": "string", "unique": True},
        ]
        sql = _model_fields_to_sql(fields)
        assert "id" in sql
        assert "primary_key=True" in sql
        assert "Integer" in sql
        assert "unique=True" in sql

    def test_model_fields_to_pydantic(self):
        fields = [
            {"name": "name", "type": "string", "required": True},
            {"name": "price", "type": "float"},
        ]
        pd = _model_fields_to_pydantic(fields)
        assert "name: str" in pd
        assert "price: float" in pd or "price: float | None = None" in pd

    def test_template_config_flask(self):
        config = _template_config("flask", "postgresql", "jwt", [])
        assert "SECRET_KEY" in config
        assert "DATABASE_URL" in config

    def test_template_model_contains_class(self):
        model = {
            "name": "User",
            "fields": [{"name": "id", "type": "int", "primary_key": True}],
        }
        tmpl = _template_model("flask", model)
        assert "class User(" in tmpl
