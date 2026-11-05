"""ORBIT Load Test Runner â€” starts server, runs tests, stops server."""

import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

API_KEY = os.environ.get("ORBIT_API_KEY", "")
BASE = "http://127.0.0.1:5000"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

ENDPOINTS_GET = [
    ("GET", "/api/health"),
    ("GET", "/api/health/dashboard"),
    ("GET", "/api/providers/status"),
    ("GET", "/api/agents/status"),
    ("GET", "/api/boot/latest"),
    ("GET", "/api/context/status"),
    ("GET", "/api/benchmark/status"),
    ("GET", "/api/security-guard/status"),
    ("GET", "/api/image-gen/status"),
    ("GET", "/api/telegram/status"),
    ("GET", "/api/discord/status"),
    ("GET", "/api/rag/status"),
    ("GET", "/api/marketplace/status"),
    ("GET", "/api/scheduler/status"),
    ("GET", "/api/voice-screen/status"),
    ("GET", "/api/a2a/stats"),
    ("GET", "/api/mcp/status"),
]

ENDPOINTS_POST = [
    ("POST", "/api/chat", {"message": "hello", "agent": "queen"}),
    ("POST", "/api/rag/query", {"query": "test document"}),
    ("POST", "/api/marketplace/browse", {}),
]


def make_request(method, path, body=None, timeout=30):
    """Make a single request and return (status_code, latency_ms, error)."""
    url = f"{BASE}{path}"
    start = time.monotonic()
    try:
        if method == "GET":
            r = requests.get(url, headers=HEADERS, timeout=timeout)
        else:
            r = requests.post(url, headers=HEADERS, json=body or {}, timeout=timeout)
        latency = (time.monotonic() - start) * 1000
        return r.status_code, latency, None
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return 0, latency, str(e)


def run_endpoint_test(method, path, body=None, concurrent=50, label=None):
    """Test a single endpoint with concurrent requests."""
    label = label or f"{method} {path}"
    latencies = []
    errors = 0
    status_codes = {}

    with ThreadPoolExecutor(max_workers=concurrent) as pool:
        futures = []
        for _ in range(concurrent):
            futures.append(pool.submit(make_request, method, path, body))
        for f in as_completed(futures):
            code, lat, err = f.result()
            latencies.append(lat)
            if err:
                errors += 1
            else:
                status_codes[code] = status_codes.get(code, 0) + 1

    if not latencies:
        return {"label": label, "requests": 0, "errors": concurrent, "error_rate": 100}

    latencies.sort()
    return {
        "label": label,
        "requests": concurrent,
        "errors": errors,
        "error_rate": round(errors / concurrent * 100, 1),
        "avg_ms": round(statistics.mean(latencies), 1),
        "p50_ms": round(latencies[len(latencies) // 2], 1),
        "p95_ms": round(latencies[int(len(latencies) * 0.95)], 1),
        "p99_ms": round(latencies[int(len(latencies) * 0.99)], 1),
        "min_ms": round(min(latencies), 1),
        "max_ms": round(max(latencies), 1),
        "statuses": status_codes,
    }


def wait_for_server(timeout=60):
    """Wait for server to be ready."""
    print("  Waiting for server...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{BASE}/api/health", headers=HEADERS, timeout=3)
            if r.status_code == 200:
                print(f" READY ({r.json().get('status', '?')})")
                return True
        except:
            pass
        time.sleep(1)
        print(".", end="", flush=True)
    print(" TIMEOUT")
    return False


def main():
    concurrent = 50

    print(f"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘           ORBIT Load Test â€” {datetime.now():%Y-%m-%d %H:%M}              â•‘
â•‘           Concurrent: {concurrent} per endpoint                      â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
""")

    # Start server
    print("[1/4] Starting ORBIT server...")
    server_proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from orbit.orbit.server import create_app; app=create_app(); app.run(host='127.0.0.1',port=5000,debug=False,threaded=True)",
        ],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(5)

    if not wait_for_server(60):
        print("Server failed to start!")
        server_proc.kill()
        return 1

    # Run tests
    results = []
    total_start = time.time()

    print(f"\n[2/4] Testing {len(ENDPOINTS_GET)} GET endpoints ({concurrent} each)...")
    for method, path in ENDPOINTS_GET:
        r = run_endpoint_test(method, path, concurrent=concurrent)
        results.append(r)
        status = "âœ“" if r["error_rate"] < 10 else "âœ—"
        print(
            f"  {status} {r['label']}: avg={r.get('avg_ms', 0):.0f}ms p95={r.get('p95_ms', 0):.0f}ms err={r['error_rate']}%"
        )

    print(
        f"\n[3/4] Testing {len(ENDPOINTS_POST)} POST endpoints ({concurrent} each)..."
    )
    for method, path, body in ENDPOINTS_POST:
        r = run_endpoint_test(method, path, body=body, concurrent=concurrent)
        results.append(r)
        status = "âœ“" if r["error_rate"] < 10 else "âœ—"
        print(
            f"  {status} {r['label']}: avg={r.get('avg_ms', 0):.0f}ms p95={r.get('p95_ms', 0):.0f}ms err={r['error_rate']}%"
        )

    total_time = time.time() - total_start

    # Summary
    print("\n[4/4] Summary...")
    print(f"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘                     LOAD TEST RESULTS                       â•‘
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘  Total endpoints tested: {len(results):<35}â•‘
â•‘  Concurrent per endpoint: {concurrent:<34}â•‘
â•‘  Total requests sent: {len(results) * concurrent:<36}â•‘
â•‘  Total test time: {total_time:.1f}s{" " * (38 - len(f"{total_time:.1f}s"))}â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
""")

    # Grade
    total_errors = sum(r["errors"] for r in results)
    total_requests = sum(r["requests"] for r in results)
    error_rate = total_errors / total_requests * 100 if total_requests else 0
    avg_latency = statistics.mean(
        [r.get("avg_ms", 0) for r in results if r.get("avg_ms")]
    )

    if error_rate < 1 and avg_latency < 200:
        grade = "A+"
    elif error_rate < 2 and avg_latency < 500:
        grade = "A"
    elif error_rate < 5 and avg_latency < 1000:
        grade = "B"
    elif error_rate < 10:
        grade = "C"
    else:
        grade = "D"

    print(f"  Overall Grade: {grade}")
    print(f"  Error Rate: {error_rate:.1f}%")
    print(f"  Avg Latency: {avg_latency:.0f}ms")
    print(f"  Total Requests: {total_requests}")
    print(f"  Failed Requests: {total_errors}")

    # Save results
    with open("tests/load_test_results.json", "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "grade": grade,
                "results": results,
            },
            f,
            indent=2,
        )
    print("\n  Results saved to tests/load_test_results.json")

    # Stop server
    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except:
        server_proc.kill()
    print("  Server stopped.")

    return 0 if grade in ("A+", "A", "B") else 1


if __name__ == "__main__":
    sys.exit(main())
