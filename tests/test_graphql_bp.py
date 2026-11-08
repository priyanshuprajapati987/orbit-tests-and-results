"""Unit tests for orbit/orbit/core/graphql_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.graphql_bp import create_graphql_bp, get_graphql_bp


class TestGraphqlBp(unittest.TestCase):
    def test_no_graphene(self):
        with patch.dict(sys.modules, {"graphene": None}):
            r = create_graphql_bp()
        self.assertIsNone(r)

    def test_with_graphene(self):
        # Build a fake graphene module
        graphene = MagicMock()

        class FakeObjectType:
            pass

        class FakeString:
            def __init__(self, *a, **k):
                pass

        class FakeSchema:
            def __init__(self, query=None):
                self.query = query

            def execute(self, q):
                res = MagicMock()
                res.data = {"hello": "Hello world!"}
                res.errors = None
                return res

        graphene.ObjectType = FakeObjectType
        graphene.String = FakeString
        graphene.Schema = FakeSchema

        # Need ObjectType subclassing to work: Query(graphene.ObjectType)
        # Since FakeObjectType is a class, subclassing works.
        with patch.dict(sys.modules, {"graphene": graphene}):
            # flask must be importable (it is)
            bp = create_graphql_bp()
        self.assertIsNotNone(bp)

    def test_singleton_none_cached(self):
        import orbit.core.graphql_bp as g
        g._bp = None
        with patch.dict(sys.modules, {"graphene": None}):
            a = get_graphql_bp()
            b = get_graphql_bp()
        self.assertIs(a, b)
        self.assertIsNone(a)
        g._bp = None

    def test_singleton_created(self):
        graphene = MagicMock()

        class FakeObjectType:
            pass

        class FakeString:
            def __init__(self, *a, **k):
                pass

        class FakeSchema:
            def __init__(self, query=None):
                self.query = query

            def execute(self, q):
                res = MagicMock()
                res.data = {"hello": "Hello!"}
                res.errors = None
                return res

        graphene.ObjectType = FakeObjectType
        graphene.String = FakeString
        graphene.Schema = FakeSchema
        import orbit.core.graphql_bp as g
        g._bp = None
        with patch.dict(sys.modules, {"graphene": graphene}):
            a = get_graphql_bp()
            b = get_graphql_bp()
        self.assertIs(a, b)
        self.assertIsNotNone(a)
        g._bp = None


if __name__ == "__main__":
    unittest.main()
