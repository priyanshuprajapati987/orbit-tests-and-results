"""ORBIT Stress Test â€” ramp from 10 to 200 concurrent users."""

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

# Mix of fast and slow endpoints
TEST_ENDPOINTS = [
    ("GET", "/api/health", None),
    ("GET", "/api/agents/status", None),
    ("GET", "/api/providers/status", None),
    ("GET", "/api/benchmark/status", None),
    ("GET", "/api/image-gen/status", None),
    ("GET", "/api/rag/status", None),
    ("GET", "/api/marketplace/status", None),
    ("POST", "/api/chat", {"message": "hi", "agent": "queen"}),
    ("POST", "/api/rag/query", {"query": "test"}),
    ("POST", "/api/marketplace/browse", {}),
]


def single_request(method, path, body=None, timeout=30):
    url = f"{BASE}{path}"
    start = time.monotonic()
    try:
        if method == "GET":
            r = requests.get(url, headers=HEADERS, timeout=timeout)
        else:
            r = requests.post(url, headers=HEADERS, json=body or {}, timeout=timeout)
        return r.status_code, (time.monotonic() - start) * 1000, None
    except Exception as e:
        return 0, (time.monotonic() - start) * 1000, str(e)


def run_concurrent_batch(n_users, duration_sec=10):
    """Run n_users concurrent requests for duration_sec, return stats."""
    latencies = []
    errors = 0
    total_requests = 0
    stop_time = time.time() + duration_sec

    def worker():
        nonlocal errors, total_requests
        local_lats = []
        while time.time() < stop_time:
            ep = TEST_ENDPOINTS[total_requests % len(TEST_ENDPOINTS)]
            code, lat, err = single_request(ep[0], ep[1], ep[2])
            local_lats.append(lat)
            total_requests += 1
            if err:
                errors += 1
        return local_lats

    with ThreadPoolExecutor(max_workers=n_users) as pool:
        futures = [pool.submit(worker) for _ in range(n_users)]
        for f in as_completed(futures):
            latencies.extend(f.result())

    if not latencies:
        return {"users": n_users, "rps": 0, "error_rate": 100, "p95_ms": 0}

    latencies.sort()
    elapsed = duration_sec
    return {
        "users": n_users,
        "total_requests": total_requests,
        "rps": round(total_requests / elapsed, 1),
        "errors": errors,
        "error_rate": round(errors / total_requests * 100, 1) if total_requests else 0,
        "avg_ms": round(statistics.mean(latencies), 1),
        "p50_ms": round(latencies[len(latencies) // 2], 1),
        "p95_ms": round(latencies[int(len(latencies) * 0.95)], 1),
        "p99_ms": round(latencies[int(len(latencies) * 0.99)], 1),
    }


def wait_for_server(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{BASE}/api/health", headers=HEADERS, timeout=3)
            if r.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False


def main():
    max_users = 200
    step = 20
    duration = 10

    print(f"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘          ORBIT Stress Test â€” {datetime.now():%Y-%m-%d %H:%M}              â•‘
â•‘          Ramp: 10 â†’ {max_users} users, {duration}s each                  â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
""")

    # Start server
    print("[1/3] Starting ORBIT server...")
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
        print("Server failed!")
        server_proc.kill()
        return 1
    print("  Server ready.\n")

    # Ramp test
    results = []
    breaking_point = None
    total_start = time.time()

    print(
        f"{'Users':>6} {'RPS':>8} {'Avg(ms)':>8} {'P50(ms)':>8} {'P95(ms)':>8} {'P99(ms)':>8} {'Err%':>6} {'Status':>8}"
    )
    print("-" * 70)

    for n in range(10, max_users + 1, step):
        r = run_concurrent_batch(n, duration_sec=duration)
        results.append(r)

        status = "OK"
        if r["error_rate"] > 10:
            status = "BROKEN"
            if not breaking_point:
                breaking_point = n
        elif r["error_rate"] > 5:
            status = "DEGRADED"
        elif r["p95_ms"] > 5000:
            status = "SLOW"

        color = (
            "\033[92m"
            if status == "OK"
            else ("\033[93m" if status in ("DEGRADED", "SLOW") else "\033[91m")
        )
        reset = "\033[0m"

        print(
            f"{color}{n:>6} {r['rps']:>8} {r['avg_ms']:>8} {r['p50_ms']:>8} {r['p95_ms']:>8} {r['p99_ms']:>8} {r['error_rate']:>5}% {status:>8}{reset}"
        )

        if breaking_point:
            print(f"\n  BREAKING POINT at {breaking_point} concurrent users!")
            break

    total_time = time.time() - total_start

    # Summary
    max_rps = max(r["rps"] for r in results)
    best_concurrent = max(r["users"] for r in results if r["error_rate"] < 5)

    print(f"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘                  STRESS TEST RESULTS                        â•‘
â• â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•£
â•‘  Breaking Point: {breaking_point or "NOT FOUND (survived all)"!s:<41}â•‘
â•‘  Max Sustainable Users: {best_concurrent:<35}â•‘
â•‘  Max RPS: {max_rps:<48}â•‘
â•‘  Total Test Time: {total_time:.1f}s{" " * (39 - len(f"{total_time:.1f}s"))}â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
""")

    with open("tests/stress_test_results.json", "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "breaking_point": breaking_point,
                "max_rps": max_rps,
                "results": results,
            },
            f,
            indent=2,
        )
    print("  Results saved to tests/stress_test_results.json")

    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except:
        server_proc.kill()
    print("  Server stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
