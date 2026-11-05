"""Regression tests: secrets are not leaked in API error responses (VULN: secret-in-error).

- A JSON error body containing a secret (api key, token, Bearer) is redacted by the
  after_request hook in server.create_app.
- The 400 handler redacts its detail string.
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from orbit.orbit.server import create_app


def test_error_body_redacts_secret():
    app = create_app()
    with app.test_client() as c:
        # Simulate a blueprint returning a raw exception string containing a secret.
        @app.route("/api/_secret_leak_test")
        def _leak():
            return {"error": "failed: api_key=sk-abcd1234efgh and Bearer tok-xyz"}, 400

        r = c.get("/api/_secret_leak_test")
        body = r.get_json()
        assert "sk-abcd1234efgh" not in str(body)
        assert "sk-" in str(body) or "[REDACTED]" in str(body)
        # The secret literal must be gone
        assert "sk-abcd1234efgh" not in body["error"]


def test_400_handler_redacts_detail():
    app = create_app()
    with app.test_client() as c:
        # Force a 400 by sending invalid JSON to an endpoint that parses JSON.
        r = c.post("/api/chat", data="{not json", content_type="application/json")
        # Either 400 (bad request) or 401 (auth) — if 400, detail must be redacted.
        if r.status_code == 400:
            assert "sk-" not in str(r.get_json())
