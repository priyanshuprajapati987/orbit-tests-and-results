"""Unit tests for orbit/orbit/core/_error_handler.py (json_error_handler)."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask, jsonify

from orbit.core._error_handler import json_error_handler


class TestJsonErrorHandlerPassthrough(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_returns_plain_value(self):
        @json_error_handler
        def ok():
            return "hello"

        self.assertEqual(ok(), "hello")

    def test_returns_tuple_response(self):
        @json_error_handler
        def view():
            return {"a": 1}, 201

        self.assertEqual(view(), ({"a": 1}, 201))

    def test_kwargs_passthrough(self):
        @json_error_handler
        def add(a, b=0):
            return a + b

        self.assertEqual(add(1, b=2), 3)

    def test_args_passthrough(self):
        @json_error_handler
        def first(*args):
            return args[0]

        self.assertEqual(first("x", "y"), "x")

    def test_returns_callable(self):
        def f():
            return 1

        wrapped = json_error_handler(f)
        self.assertTrue(callable(wrapped))

    def test_preserves_function_name(self):
        @json_error_handler
        def my_special_route():
            """Doc here."""

        self.assertEqual(my_special_route.__name__, "my_special_route")
        self.assertEqual(my_special_route.__doc__, "Doc here.")


class TestJsonErrorHandlerException(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def _call(self, fn):
        with self.app.test_request_context():
            return fn()

    def test_exception_returns_500_tuple(self):
        @json_error_handler
        def boom():
            raise ValueError("kaput")

        resp = self._call(boom)
        self.assertIsInstance(resp, tuple)
        _, status = resp
        self.assertEqual(status, 500)

    def test_json_body_shape(self):
        @json_error_handler
        def boom():
            raise ValueError("kaput")

        body, _ = self._call(boom)
        data = body.get_json()
        self.assertEqual(data["error"], "kaput")
        self.assertEqual(data["route"], "boom")
        self.assertEqual(data["type"], "ValueError")

    def test_route_is_function_name(self):
        @json_error_handler
        def some_long_route_name():
            raise RuntimeError("x")

        body, _ = self._call(some_long_route_name)
        self.assertEqual(body.get_json()["route"], "some_long_route_name")

    def test_custom_exception_type_reported(self):
        class MyWeirdError(Exception):
            pass

        @json_error_handler
        def boom():
            raise MyWeirdError("custom")

        body, _ = self._call(boom)
        data = body.get_json()
        self.assertEqual(data["type"], "MyWeirdError")
        self.assertEqual(data["error"], "custom")

    def test_keyerror_and_zero_division_caught(self):
        @json_error_handler
        def key_err():
            {}["missing"]

        @json_error_handler
        def div_err():
            1 / 0

        for fn in (key_err, div_err):
            body, status = self._call(fn)
            self.assertEqual(status, 500)
            self.assertIn("error", body.get_json())

    def test_logger_exception_called(self):
        @json_error_handler
        def boom():
            raise ValueError("logged")

        with self.assertLogs("orbit.core._error_handler",
                             level="ERROR") as cm:
            self._call(boom)
        joined = "\n".join(cm.output)
        self.assertIn("Unhandled error in boom", joined)
        self.assertIn("logged", joined)

    def test_baseexception_not_caught(self):
        @json_error_handler
        def die():
            raise SystemExit(3)

        with self.assertRaises(SystemExit):
            self._call(die)


class TestJsonErrorHandlerFlaskRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.client = self.app.test_client()

    def test_route_exception_is_json_500(self):
        @self.app.route("/boom")
        @json_error_handler
        def boom():
            raise ValueError("route exploded")

        r = self.client.get("/boom")
        self.assertEqual(r.status_code, 500)
        self.assertTrue(r.is_json)
        data = r.get_json()
        self.assertEqual(data["error"], "route exploded")
        self.assertEqual(data["route"], "boom")
        self.assertEqual(data["type"], "ValueError")

    def test_route_success_untouched(self):
        @self.app.route("/fine")
        @json_error_handler
        def fine():
            return jsonify({"ok": True}), 200

        r = self.client.get("/fine")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ok": True})

    def test_no_html_error_page(self):
        @self.app.route("/html-check")
        @json_error_handler
        def html_check():
            raise RuntimeError("no html")

        r = self.client.get("/html-check")
        self.assertNotIn(b"<html", r.data.lower())
        self.assertEqual(r.mimetype, "application/json")


if __name__ == "__main__":
    unittest.main()
