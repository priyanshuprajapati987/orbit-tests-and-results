"""Tests for the load / stress runner in tests/load/load_test.py.

Hermetic: spins a throwaway ThreadingHTTPServer on 127.0.0.1 (ephemeral
port) instead of touching the real ORBIT server, then drives real HTTP
through run_load(). No external network, no user data.
"""

import importlib.util
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

# NOTE: tests/load_test.py already exists in this repo, so plain
# `import load_test` would resolve to THAT file once pytest puts tests/ on
# sys.path. Load our runner by absolute path instead.
_LOAD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "load", "load_test.py")
_spec = importlib.util.spec_from_file_location("orbit_load_runner", _LOAD_PATH)
load_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load_tool)

_percentile = load_tool._percentile
build_parser = load_tool.build_parser
parse_ramp = load_tool.parse_ramp
run_load = load_tool.run_load


class _Handler(BaseHTTPRequestHandler):
    hits = 0
    # HTTP/1.1 + keep-alive: otherwise the server spawns one thread per
    # request and the throwaway server itself becomes the bottleneck.
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        type(self).hits += 1
        if self.path == "/boom":
            body = b'{"error":"boom"}'
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        payload = json.dumps({"status": "ok", "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence
        pass


def _server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def test_percentile_nearest_rank():
    vals = [float(v) for v in range(1, 101)]
    assert _percentile([], 50) == 0.0
    assert _percentile(vals, 50) == 50.0
    assert _percentile(vals, 95) == 95.0
    assert _percentile(vals, 99) == 99.0
    assert _percentile(vals, 100) == 100.0


def test_parse_ramp_accepts_and_rejects():
    import pytest

    assert parse_ramp("10,50,100,200,400") == [10, 50, 100, 200, 400]
    assert parse_ramp(" 4 ; 8 ") == [4, 8]
    with pytest.raises(Exception, match="concurrency"):
        parse_ramp("0")


def test_run_load_success_schema():
    srv = _server()
    try:
        m = run_load(
            url=f"http://127.0.0.1:{srv.server_address[1]}",
            endpoint="/api/health",
            concurrency=4,
            duration=1.5,
            timeout=5.0,
        )
    finally:
        srv.shutdown()

    for key in (
        "rps",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "requests",
        "errors",
        "error_rate",
        "status_counts",
    ):
        assert key in m, f"missing {key}"

    assert m["requests"] > 0
    assert m["concurrency"] == 4
    assert m["errors"] == 0
    assert m["status_counts"].get("200") == m["requests_ok"]
    assert m["p50_ms"] <= m["p95_ms"] <= m["p99_ms"]
    assert m["rps"] > 0


def test_run_load_counts_5xx_as_errors():
    srv = _server()
    try:
        m = run_load(
            url=f"http://127.0.0.1:{srv.server_address[1]}",
            endpoint="/boom",
            concurrency=2,
            duration=1.0,
            timeout=5.0,
        )
    finally:
        srv.shutdown()

    assert m["errors"] == m["requests"]
    assert m["error_rate"] == 1.0
    assert m["status_counts"].get("500", 0) == m["requests"]


def test_run_load_sends_api_key_header():
    seen = {}

    class _KeyHandler(_Handler):
        def do_GET(self):  # noqa: N802
            seen["x_api_key"] = self.headers.get("X-API-Key")
            seen["authorization"] = self.headers.get("Authorization")
            super().do_GET()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _KeyHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        m = run_load(
            url=f"http://127.0.0.1:{srv.server_address[1]}",
            endpoint="/api/health",
            concurrency=1,
            duration=0.6,
            api_key="secret-key-123",
            timeout=5.0,
        )
    finally:
        srv.shutdown()

    assert m["requests"] > 0
    assert seen["x_api_key"] == "secret-key-123"
    assert seen["authorization"] == "Bearer secret-key-123"


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert args.endpoint == "/api/health"
    assert args.ramp is None
    assert args.method == "GET"
    assert args.max_rps == 0.0


def test_run_load_paces_attempt_rate():
    srv = _server()
    try:
        m = run_load(
            url=f"http://127.0.0.1:{srv.server_address[1]}",
            endpoint="/api/health",
            concurrency=16,
            duration=2.0,
            timeout=5.0,
            max_rps=50.0,
        )
    finally:
        srv.shutdown()

    # ~100 requests over 2s at 50 rps; allow generous slop for scheduling.
    assert 50 <= m["requests"] <= 140, m["requests"]
    assert m["pacing_rps"] == 50.0
    assert m["errors"] == 0
    # Without pacing 16 workers on a local socket would do thousands/sec.
    assert m["rps"] <= 80.0, m["rps"]


def test_run_load_unpaced_is_default():
    args = build_parser().parse_args(["--concurrency", "4"])
    assert args.max_rps == 0.0
