"""ORBIT New Features Stress Test â€” 6 features, 20 concurrent each."""

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
CONCURRENT = 20


def req(method, path, body=None, timeout=30):
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


def stress_feature(name, method, path, body=None, count=CONCURRENT):
    """Stress a single feature endpoint."""
    latencies = []
    errors = 0
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(req, method, path, body) for _ in range(count)]
        for f in as_completed(futures):
            code, lat, err = f.result()
            latencies.append(lat)
            if err or code >= 400:
                errors += 1
    latencies.sort()
    return {
        "name": name,
        "requests": count,
        "errors": errors,
        "error_rate": round(errors / count * 100, 1),
        "avg_ms": round(statistics.mean(latencies), 1),
        "p50_ms": round(latencies[len(latencies) // 2], 1),
        "p95_ms": round(latencies[int(len(latencies) * 0.95)], 1),
        "p99_ms": round(latencies[int(len(latencies) * 0.99)], 1),
        "min_ms": round(min(latencies), 1),
        "max_ms": round(max(latencies), 1),
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
    print(f"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘        New Features Stress Test â€” {datetime.now():%Y-%m-%d %H:%M}           â•‘
â•‘        {CONCURRENT} concurrent requests per feature                   â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
""")

    # Start server
    print("[1/2] Starting ORBIT server...")
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

    # Test all 6 features
    tests = [
        ("Image Generator", "GET", "/api/image-gen/status", None),
        (
            "Image Gen Generate",
            "POST",
            "/api/image-gen/generate",
            {"prompt": "a cat", "model": "dall-e-3"},
        ),
        ("Telegram Bot", "GET", "/api/telegram/status", None),
        (
            "Telegram Send",
            "POST",
            "/api/telegram/send",
            {"chat_id": "123", "message": "test"},
        ),
        ("Discord Bot", "GET", "/api/discord/status", None),
        (
            "Discord Send",
            "POST",
            "/api/discord/send",
            {"channel_id": "123", "message": "test"},
        ),
        ("RAG Status", "GET", "/api/rag/status", None),
        (
            "RAG Ingest",
            "POST",
            "/api/rag/ingest",
            {"text": "test document for stress test", "source": "stress_test"},
        ),
        ("RAG Query", "POST", "/api/rag/query", {"query": "test document"}),
        ("Marketplace", "GET", "/api/marketplace/status", None),
        ("Marketplace Browse", "POST", "/api/marketplace/browse", {}),
        ("Cron Scheduler", "GET", "/api/scheduler/status", None),
        ("Voice-Screen", "GET", "/api/voice-screen/status", None),
    ]

    results = []
    for name, method, path, body in tests:
        print(f"  Testing {name}...", end=" ", flush=True)
        r = stress_feature(name, method, path, body)
        results.append(r)
        status = "OK" if r["error_rate"] < 10 else "FAIL"
        print(
            f"{status} avg={r['avg_ms']}ms p95={r['p95_ms']}ms err={r['error_rate']}%"
        )

    # Summary
    print(f"\n{'=' * 70}")
    print(
        f"{'Feature':<25} {'Reqs':>6} {'Avg(ms)':>8} {'P50(ms)':>8} {'P95(ms)':>8} {'Err%':>6} {'Grade':>6}"
    )
    print(f"{'-' * 70}")

    for r in results:
        if r["error_rate"] < 1:
            grade = "A+"
        elif r["error_rate"] < 5:
            grade = "A"
        elif r["error_rate"] < 10:
            grade = "B"
        elif r["error_rate"] < 25:
            grade = "C"
        else:
            grade = "D"
        print(
            f"{r['name']:<25} {r['requests']:>6} {r['avg_ms']:>8} {r['p50_ms']:>8} {r['p95_ms']:>8} {r['error_rate']:>5}% {grade:>6}"
        )

    total = sum(r["requests"] for r in results)
    total_err = sum(r["errors"] for r in results)
    overall_err = total_err / total * 100 if total else 0
    overall_avg = statistics.mean([r["avg_ms"] for r in results])

    print(f"{'-' * 70}")
    print(
        f"{'TOTAL':<25} {total:>6} {overall_avg:>8.0f} {'':>8} {'':>8} {overall_err:>5.1f}%"
    )

    with open("tests/new_features_stress_results.json", "w") as f:
        json.dump(
            {"timestamp": datetime.now().isoformat(), "results": results}, f, indent=2
        )
    print("\n  Results saved to tests/new_features_stress_results.json")

    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except:
        server_proc.kill()
    print("  Server stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
