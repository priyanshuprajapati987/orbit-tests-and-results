"""Tests for Requirement Parser (System 11)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.core.requirement_parser import (
    ParsedSpec,
    RequirementParser,
    get_requirement_parser,
)


class TestCore:
    def test_singleton(self):
        p1 = get_requirement_parser()
        p2 = get_requirement_parser()
        assert p1 is p2

    def test_parse_auth_spec(self):
        parser = get_requirement_parser()
        spec = "Create user authentication API with JWT tokens and password hashing"
        result = parser.parse_specification(spec, "auth_api")
        assert result["project_name"] == "auth_api"
        assert len(result["requirements"]) > 0
        assert any(r["type"] == "route" for r in result["requirements"])

    def test_parse_empty_spec(self):
        parser = get_requirement_parser()
        result = parser.parse_specification("", "empty")
        assert result["project_name"] == "empty"
        assert len(result["requirements"]) == 0

    def test_extract_jwt_auth(self):
        parser = get_requirement_parser()
        result = parser.parse_specification(
            "API with JWT token authentication", "test_jwt"
        )
        assert "pyjwt" in result["dependencies"]
        assert "JWT authentication" in result["entities"]["features"]

    def test_extract_password_hashing(self):
        parser = get_requirement_parser()
        result = parser.parse_specification(
            "API with password hashing using bcrypt", "test_hash"
        )
        assert "Password hashing" in result["entities"]["features"]
        assert "bcrypt" in result["dependencies"]

    def test_extract_role_based_access(self):
        parser = get_requirement_parser()
        result = parser.parse_specification(
            "RBAC with admin and user roles", "test_rbac"
        )
        assert "Role-based access control" in result["entities"]["features"]

    def test_recommend_flask_tech_stack(self):
        parser = get_requirement_parser()
        result = parser.parse_specification("Flask REST API", "test_flask")
        assert "Flask" in result["tech_stack"]
        assert "Python" in result["tech_stack"]

    def test_recommend_postgresql(self):
        parser = get_requirement_parser()
        result = parser.parse_specification("PostgreSQL-backed REST API", "test_pg")
        assert "PostgreSQL" in result["tech_stack"]
        assert "psycopg2-binary" in result["dependencies"]

    def test_recommend_mongodb(self):
        parser = get_requirement_parser()
        result = parser.parse_specification("MongoDB NoSQL database API", "test_mongo")
        assert "MongoDB" in result["tech_stack"]
        assert "pymongo" in result["dependencies"]

    def test_find_user_model(self):
        parser = get_requirement_parser()
        result = parser.parse_specification("User management system", "test_user")
        models = result["entities"]["models"]
        assert any(m["name"] == "User" for m in models)

    def test_find_multiple_models(self):
        parser = get_requirement_parser()
        result = parser.parse_specification(
            "User and Product management system", "test_mp"
        )
        models = result["entities"]["models"]
        names = [m["name"] for m in models]
        assert "User" in names
        assert "Product" in names

    def test_find_endpoints_login_register(self):
        parser = get_requirement_parser()
        result = parser.parse_specification("login and register endpoints", "test_lr")
        endpoints = result["entities"]["endpoints"]
        paths = [e["path"] for e in endpoints]
        assert "/auth/login" in paths
        assert "/auth/register" in paths

    def test_find_database_type(self):
        parser = RequirementParser()
        assert parser._find_database_type("postgresql database") == "postgresql"
        assert parser._find_database_type("mongo nosql") == "mongodb"
        assert parser._find_database_type("sqlite") == "sqlite"
        assert parser._find_database_type("default") == "sqlite"

    def test_find_auth_type(self):
        parser = RequirementParser()
        assert parser._find_auth_type("jwt token") == "jwt"
        assert parser._find_auth_type("oauth2") == "oauth"
        assert parser._find_auth_type("session cookie") == "session"
        assert parser._find_auth_type("no auth") == "none"

    def test_get_tech_stack_recommendation(self):
        parser = get_requirement_parser()
        result = parser.get_tech_stack_recommendation(
            features=["JWT authentication", "Rate limiting"],
            framework="flask",
            database="postgresql",
            auth="jwt",
        )
        assert "Flask" in result["tech_stack"]
        assert "PostgreSQL" in result["tech_stack"]
        assert "PyJWT" in result["tech_stack"]
        assert "Flask-Limiter" in result["tech_stack"]

    def test_multiple_parse_calls(self):
        parser = get_requirement_parser()
        parser.parse_specification("JWT auth API", "jwt_api")
        parser.parse_specification("PostgreSQL CRUD", "crud_api")
        projects = parser.list_parsed()
        assert "jwt_api" in projects
        assert "crud_api" in projects

    def test_get_parsed_existing(self):
        parser = get_requirement_parser()
        parser.parse_specification("test spec", "get_test")
        result = parser.get_parsed("get_test")
        assert result is not None
        assert result["project_name"] == "get_test"

    def test_get_parsed_missing(self):
        parser = get_requirement_parser()
        result = parser.get_parsed("nonexistent")
        assert result is None

    def test_summarize_short(self):
        parser = RequirementParser()
        summary = parser._summarize("Hello world")
        assert "Hello world" in summary

    def test_summarize_long(self):
        parser = RequirementParser()
        long_text = "A " * 500
        summary = parser._summarize(long_text)
        assert len(summary) <= 304  # 300 + "..."

    def test_reset(self):
        parser = get_requirement_parser()
        parser.parse_specification("test spec", "reset_test")
        parser.reset()
        projects = parser.list_parsed()
        assert "reset_test" not in projects

    def test_empty_list(self):
        parser = get_requirement_parser()
        parser.reset()
        assert parser.list_parsed() == []


class TestParsedSpec:
    def test_default_parsed_at(self):
        spec = ParsedSpec(project_name="test")
        assert spec.parsed_at is not None
        assert len(spec.parsed_at) > 0

    def test_default_lists_empty(self):
        spec = ParsedSpec()
        assert spec.requirements == []
        assert spec.tech_stack == []
        assert spec.dependencies == []
