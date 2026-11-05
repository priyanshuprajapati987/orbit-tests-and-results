"""
ORBIT API Load Test
===================
Comprehensive load test for all major ORBIT Flask API endpoints.
Tests 50 concurrent requests per endpoint, measures latency distribution,
throughput, and error rates.

Usage: py tests/load_test.py [--url http://127.0.0.1:5000] [--concurrent 50]
"""

import argparse
import json
import os
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime
from statistics import mean
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# â”€â”€â”€ Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

DEFAULT_BASE_URL = "http://127.0.0.1:5000"
API_KEY = os.environ.get("ORBIT_API_KEY", "")
DEFAULT_CONCURRENT = 50
REQUEST_TIMEOUT = 30

# â”€â”€â”€ ANSI Colors â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    BG_RED = "\033[41m"
    BG_GRN = "\033[42m"
    BG_YLW = "\033[43m"


# â”€â”€â”€ Endpoint Definitions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

GET_ENDPOINTS = [
    "/api/health",
    "/api/health/dashboard",
    "/api/providers/status",
    "/api/agents/status",
    "/api/boot/latest",
    "/api/context/status",
    "/api/benchmark/status",
    "/api/benchmark/ground-truth/status",
    "/api/security-guard/status",
    "/api/image-gen/status",
    "/api/telegram/status",
    "/api/discord/status",
    "/api/rag/status",
    "/api/marketplace/status",
    "/api/scheduler/status",
    "/api/voice-screen/status",
    "/api/a2a/stats",
    "/api/mcp/status",
]

POST_ENDPOINTS = [
    {
        "path": "/api/chat",
        "body": {"message": "hello", "agent": "queen"},
    },
    {
        "path": "/api/rag/query",
        "body": {"query": "test"},
    },
    {
        "path": "/api/marketplace/browse",
        "body": {},
    },
    {
        "path": "/api/image-gen/generate",
        "body": {"prompt": "test", "model": "dall-e-3"},
    },
]

# â”€â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_stop_event = threading.Event()


def _banner():
    print(f"""
{C.CYAN}{C.BOLD}â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘            ORBIT API Load Test â€” {datetime.now():%Y-%m-%d %H:%M}            â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•{C.RESET}
""")


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def _color_latency(ms):
    if ms < 200:
        return f"{C.GREEN}{ms:>8.1f}ms{C.RESET}"
    elif ms < 1000:
        return f"{C.YELLOW}{ms:>8.1f}ms{C.RESET}"
    else:
        return f"{C.RED}{ms:>8.1f}ms{C.RESET}"


def _color_rate(rate):
    if rate == 0:
        return f"{C.GREEN}{rate:>5.1f}%{C.RESET}"
    elif rate < 5:
        return f"{C.YELLOW}{rate:>5.1f}%{C.RESET}"
    else:
        return f"{C.RED}{rate:>5.1f}%{C.RESET}"


def _bar(value, max_val, width=20):
    if max_val == 0:
        filled = 0
    else:
        filled = int((value / max_val) * width)
    filled = min(filled, width)
    return f"{C.CYAN}{'â–ˆ' * filled}{'â–‘' * (width - filled)}{C.RESET}"


# â”€â”€â”€ Request Workers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _make_request(base_url, method, path, body=None):
    """Execute a single HTTP request. Returns (status_code, latency_ms, error)."""
    url = f"{base_url}{path}"
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None

    start = time.perf_counter()
    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            _ = resp.read()
            latency = (time.perf_counter() - start) * 1000
            return resp.status, latency, None
    except HTTPError as e:
        latency = (time.perf_counter() - start) * 1000
        return e.code, latency, str(e)
    except URLError as e:
        latency = (time.perf_counter() - start) * 1000
        return 0, latency, str(e.reason)
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return 0, latency, str(e)


def _worker(base_url, method, path, body, results, idx):
    """Thread worker that fires one request and records the result."""
    if _stop_event.is_set():
        return
    status, latency, error = _make_request(base_url, method, path, body)
    results[idx] = (status, latency, error)


def _run_endpoint_test(base_url, method, path, body, concurrent):
    """Run concurrent requests against a single endpoint. Returns stats dict."""
    results = [None] * concurrent
    threads = []

    wall_start = time.perf_counter()
    for i in range(concurrent):
        t = threading.Thread(
            target=_worker, args=(base_url, method, path, body, results, i)
        )
        t.daemon = True
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=REQUEST_TIMEOUT + 5)
    wall_ms = (time.perf_counter() - wall_start) * 1000

    latencies = []
    errors = 0
    status_codes = defaultdict(int)

    for r in results:
        if r is None:
            errors += 1
            status_codes["timeout"] += 1
            continue
        status, lat, err = r
        latencies.append(lat)
        status_codes[status] += 1
        if err or status >= 400:
            errors += 1

    latencies.sort()
    error_rate = (errors / concurrent) * 100 if concurrent > 0 else 0

    return {
        "method": method,
        "path": path,
        "total": concurrent,
        "success": concurrent - errors,
        "errors": errors,
        "error_rate": error_rate,
        "wall_ms": wall_ms,
        "latencies": latencies,
        "avg_ms": mean(latencies) if latencies else 0,
        "min_ms": latencies[0] if latencies else 0,
        "max_ms": latencies[-1] if latencies else 0,
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
        "rps": (concurrent / (wall_ms / 1000)) if wall_ms > 0 else 0,
        "status_codes": dict(status_codes),
    }


# â”€â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def main():
    parser = argparse.ArgumentParser(description="ORBIT API Load Test")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Base URL")
    parser.add_argument(
        "--concurrent",
        type=int,
        default=DEFAULT_CONCURRENT,
        help="Concurrent requests per endpoint",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    concurrent = args.concurrent

    _banner()

    # Verify connectivity
    print(f"{C.DIM}  Connecting to {base_url}...{C.RESET}", end=" ", flush=True)
    try:
        status, lat, err = _make_request(base_url, "GET", "/api/health")
        if err and status == 0:
            print(f"{C.RED}FAILED{C.RESET} â€” {err}")
            print(f"\n{C.RED}  Cannot reach ORBIT server. Is it running?{C.RESET}")
            sys.exit(1)
        print(f"{C.GREEN}OK{C.RESET} ({status}, {lat:.0f}ms)")
    except Exception as e:
        print(f"{C.RED}FAILED{C.RESET} â€” {e}")
        sys.exit(1)

    print(f"  Concurrent requests per endpoint: {C.BOLD}{concurrent}{C.RESET}")
    print(f"  Request timeout: {REQUEST_TIMEOUT}s")
    print(f"  Total endpoints: {len(GET_ENDPOINTS) + len(POST_ENDPOINTS)}")
    print()

    all_results = []
    total_start = time.perf_counter()
    endpoint_idx = 0
    total_endpoints = len(GET_ENDPOINTS) + len(POST_ENDPOINTS)

    try:
        # â”€â”€ GET Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        print(
            f"{C.BOLD}{C.CYAN}  â”Œâ”€ GET Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”{C.RESET}"
        )
        for path in GET_ENDPOINTS:
            endpoint_idx += 1
            label = f"GET  {path}"
            progress = f"[{endpoint_idx}/{total_endpoints}]"
            print(f"  {C.DIM}{progress}{C.RESET} {label:<45} ", end="", flush=True)

            stats = _run_endpoint_test(base_url, "GET", path, None, concurrent)
            all_results.append(stats)

            err_str = _color_rate(stats["error_rate"])
            lat_str = _color_latency(stats["p95_ms"])
            print(f"p95={lat_str}  err={err_str}  rps={stats['rps']:.0f}")

        # â”€â”€ POST Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        print(f"{C.RESET}")
        print(
            f"{C.BOLD}{C.CYAN}  â”Œâ”€ POST Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”{C.RESET}"
        )
        for ep in POST_ENDPOINTS:
            endpoint_idx += 1
            path = ep["path"]
            body = ep["body"]
            label = f"POST {path}"
            progress = f"[{endpoint_idx}/{total_endpoints}]"
            print(f"  {C.DIM}{progress}{C.RESET} {label:<45} ", end="", flush=True)

            stats = _run_endpoint_test(base_url, "POST", path, body, concurrent)
            all_results.append(stats)

            err_str = _color_rate(stats["error_rate"])
            lat_str = _color_latency(stats["p95_ms"])
            print(f"p95={lat_str}  err={err_str}  rps={stats['rps']:.0f}")

    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}  âš¡ Interrupted by user{C.RESET}")
        _stop_event.set()

    total_ms = (time.perf_counter() - total_start) * 1000

    # â”€â”€ Results Table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n{C.BOLD}{C.WHITE}{'â•' * 80}{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}  RESULTS SUMMARY{C.RESET}")
    print(f"{C.BOLD}{C.WHITE}{'â•' * 80}{C.RESET}\n")

    # Header
    hdr = f"  {'Endpoint':<42} {'Reqs':>5} {'Errs':>5} {'Err%':>6} {'Avg':>9} {'P50':>9} {'P95':>9} {'P99':>9} {'RPS':>6}"
    print(f"{C.BOLD}{hdr}{C.RESET}")
    print(f"  {'â”€' * 100}")

    for s in all_results:
        name = f"{s['method']:>4} {s['path']}"
        if len(name) > 40:
            name = name[:37] + "..."
        err_s = _color_rate(s["error_rate"])
        a_s = _color_latency(s["avg_ms"])
        p50_s = _color_latency(s["p50_ms"])
        p95_s = _color_latency(s["p95_ms"])
        p99_s = _color_latency(s["p99_ms"])
        print(
            f"  {name:<42} {s['total']:>5} {s['errors']:>5} {err_s} {a_s} {p50_s} {p95_s} {p99_s} {s['rps']:>6.0f}"
        )

    # Aggregate
    all_lats = []
    total_reqs = 0
    total_errs = 0
    for s in all_results:
        all_lats.extend(s["latencies"])
        total_reqs += s["total"]
        total_errs += s["errors"]

    all_lats.sort()
    agg_rps = (total_reqs / (total_ms / 1000)) if total_ms > 0 else 0

    print(f"  {'â”€' * 100}")
    agg_err = (total_errs / total_reqs * 100) if total_reqs > 0 else 0
    agg_err_s = _color_rate(agg_err)
    agg_a = _color_latency(mean(all_lats) if all_lats else 0)
    agg_p50 = _color_latency(_percentile(all_lats, 50))
    agg_p95 = _color_latency(_percentile(all_lats, 95))
    agg_p99 = _color_latency(_percentile(all_lats, 99))
    print(
        f"  {C.BOLD}{'AGGREGATE':<42} {total_reqs:>5} {total_errs:>5} {agg_err_s} {agg_a} {agg_p50} {agg_p95} {agg_p99} {agg_rps:>6.0f}{C.RESET}"
    )

    # â”€â”€ Verdict â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n{C.BOLD}{C.WHITE}{'â•' * 80}{C.RESET}")
    print(f"{C.BOLD}  VERDICT{C.RESET}")
    print(f"{'â”€' * 80}")
    print(f"  Total requests:    {C.BOLD}{total_reqs}{C.RESET}")
    print(f"  Total errors:      {C.BOLD}{total_errs}{C.RESET}")
    print(f"  Error rate:        {agg_err_s}")
    print(f"  Overall RPS:       {C.BOLD}{agg_rps:.0f}{C.RESET}")
    print(f"  Wall time:         {C.BOLD}{total_ms / 1000:.1f}s{C.RESET}")
    print(f"  Avg latency:       {agg_a}")
    print(f"  P95 latency:       {agg_p95}")
    print(f"  P99 latency:       {agg_p99}")

    if agg_err == 0 and _percentile(all_lats, 95) < 1000:
        grade = f"{C.GREEN}{C.BOLD}A â€” Excellent{C.RESET}"
    elif agg_err < 2 and _percentile(all_lats, 95) < 3000:
        grade = f"{C.YELLOW}{C.BOLD}B â€” Good{C.RESET}"
    elif agg_err < 10:
        grade = f"{C.YELLOW}{C.BOLD}C â€” Acceptable{C.RESET}"
    else:
        grade = f"{C.RED}{C.BOLD}F â€” Needs attention{C.RESET}"

    print(f"  Grade:             {grade}")
    print(f"{'â•' * 80}\n")

    return 0 if agg_err < 10 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}  Interrupted.{C.RESET}")
        sys.exit(130)
