"""
ORBIT API Stress Test
=====================
Ramps from 10 to 200 concurrent users, each making repeated requests.
Finds the breaking point where error rate > 10% or P95 > 5000ms.

Usage: py tests/stress_test.py [--url http://127.0.0.1:5000]
"""

import argparse
import json
import os
import random
import sys
import threading
import time
from datetime import datetime
from statistics import mean
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:5000"
API_KEY = os.environ.get("ORBIT_API_KEY", "")
REQUEST_TIMEOUT = 15
STEP_USERS = 10
STEP_DURATION = 10
MAX_USERS = 200
BREAK_ERROR_PCT = 10.0
BREAK_P95_MS = 5000.0

GET_PATHS = [
    "/api/health",
    "/api/providers/status",
    "/api/agents/status",
    "/api/benchmark/status",
    "/api/context/status",
    "/api/health/dashboard",
]

POST_PAYLOADS = [
    ("/api/chat", {"message": "hello", "agent": "queen"}),
    ("/api/rag/query", {"query": "test"}),
]


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"


_stop = threading.Event()
_step_results = []
_step_lock = threading.Lock()


def _banner():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print()
    print(
        C.CYAN
        + C.BOLD
        + "  ================================================================",
        C.RESET,
    )
    print(C.CYAN + C.BOLD + "    ORBIT API Stress Test  |  " + ts, C.RESET)
    print(C.CYAN + C.BOLD + "    Ramp: 10 users every 10s -> 200 max", C.RESET)
    print(
        C.CYAN
        + C.BOLD
        + "  ================================================================",
        C.RESET,
    )
    print()


def _http(base_url, method, path, body=None):
    url = base_url + path
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    t0 = time.perf_counter()
    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            _ = resp.read()
            lat = (time.perf_counter() - t0) * 1000
            return resp.status, lat, None
    except HTTPError as e:
        lat = (time.perf_counter() - t0) * 1000
        return e.code, lat, str(e)
    except URLError as e:
        lat = (time.perf_counter() - t0) * 1000
        return 0, lat, str(e.reason)
    except Exception as e:
        lat = (time.perf_counter() - t0) * 1000
        return 0, lat, str(e)


def _user_loop(base_url, user_id, results_bag, duration_sec):
    end_time = time.perf_counter() + duration_sec
    while time.perf_counter() < end_time and not _stop.is_set():
        if random.random() < 0.7:
            path = random.choice(GET_PATHS)
            status, lat, err = _http(base_url, "GET", path)
        else:
            path, body = random.choice(POST_PAYLOADS)
            status, lat, err = _http(base_url, "POST", path, body)
        results_bag.append((status, lat, err))
        time.sleep(random.uniform(0.01, 0.05))


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def _color_ms(ms):
    if ms < 500:
        return C.GREEN + "%8.1fms" % ms + C.RESET
    elif ms < 2000:
        return C.YELLOW + "%8.1fms" % ms + C.RESET
    else:
        return C.RED + "%8.1fms" % ms + C.RESET


def _color_err(rate):
    if rate == 0:
        return C.GREEN + "%5.1f%%" % rate + C.RESET
    elif rate < 5 or rate < 10:
        return C.YELLOW + "%5.1f%%" % rate + C.RESET
    else:
        return C.RED + "%5.1f%%" % rate + C.RESET


def main():
    parser = argparse.ArgumentParser(description="ORBIT API Stress Test")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Base URL")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    _banner()

    # Connectivity check
    sys.stdout.write("  Connecting to %s... " % base_url)
    sys.stdout.flush()
    try:
        status, lat, err = _http(base_url, "GET", "/api/health")
        if err and status == 0:
            print(C.RED + "FAILED" + C.RESET + " -- " + err)
            print()
            print(C.RED + "  Cannot reach ORBIT server. Is it running?" + C.RESET)
            sys.exit(1)
        print(C.GREEN + "OK" + C.RESET + " (%d, %.0fms)" % (status, lat))
    except Exception as e:
        print(C.RED + "FAILED" + C.RESET + " -- " + str(e))
        sys.exit(1)

    print("  Ramp: %d users every %ds, max %d" % (STEP_USERS, STEP_DURATION, MAX_USERS))
    print(
        "  Breaking point: error>%.0f%% or P95>%.0fms" % (BREAK_ERROR_PCT, BREAK_P95_MS)
    )
    print()

    hdr = "  %6s %6s %6s %6s %7s %9s %9s %9s %8s" % (
        "Users",
        "Reqs",
        "Errors",
        "Err%",
        "RPS",
        "Avg",
        "P50",
        "P95",
        "Status",
    )
    print(C.BOLD + hdr + C.RESET)
    print("  " + "-" * 82)

    breaking_users = None
    max_sustainable = 0
    all_steps = []
    total_start = time.perf_counter()

    try:
        for users in range(STEP_USERS, MAX_USERS + 1, STEP_USERS):
            step_start = time.perf_counter()
            results = []
            threads = []

            for uid in range(users):
                t = threading.Thread(
                    target=_user_loop,
                    args=(base_url, uid, results, STEP_DURATION),
                    daemon=True,
                )
                t.start()
                threads.append(t)

            for t in threads:
                t.join(timeout=STEP_DURATION + 10)

            step_ms = (time.perf_counter() - step_start) * 1000

            # Analyze step
            lats = [r[1] for r in results]
            lats.sort()
            errors = sum(1 for r in results if r[2] is not None or r[0] >= 400)
            total_reqs = len(results)
            error_rate = (errors / total_reqs * 100) if total_reqs > 0 else 0
            rps = (total_reqs / (step_ms / 1000)) if step_ms > 0 else 0
            avg_lat = mean(lats) if lats else 0
            p50 = _percentile(lats, 50)
            p95 = _percentile(lats, 95)

            step_data = {
                "users": users,
                "total_reqs": total_reqs,
                "errors": errors,
                "error_rate": error_rate,
                "rps": rps,
                "avg_ms": avg_lat,
                "p50_ms": p50,
                "p95_ms": p95,
            }
            all_steps.append(step_data)

            # Determine status
            broken = error_rate > BREAK_ERROR_PCT or p95 > BREAK_P95_MS
            if broken:
                status_str = C.RED + "BREAKING" + C.RESET
                if breaking_users is None:
                    breaking_users = users
            else:
                status_str = C.GREEN + "OK" + C.RESET
                max_sustainable = users

            # Print row
            row = "  %6d %6d %6d %s %7.1f %s %s %s %s" % (
                users,
                total_reqs,
                errors,
                _color_err(error_rate),
                rps,
                _color_ms(avg_lat),
                _color_ms(p50),
                _color_ms(p95),
                status_str,
            )
            print(row)

            if breaking_users and users >= breaking_users + STEP_USERS:
                # Continue a bit more to confirm
                if breaking_users and users > breaking_users + STEP_USERS:
                    break

    except KeyboardInterrupt:
        print()
        print(C.YELLOW + "  Interrupted by user" + C.RESET)

    total_ms = (time.perf_counter() - total_start) * 1000

    # â”€â”€ Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print()
    print(
        C.BOLD
        + C.WHITE
        + "  ================================================================"
        + C.RESET
    )
    print(C.BOLD + "  STRESS TEST SUMMARY" + C.RESET)
    print("  " + "=" * 62)
    print()

    if all_steps:
        best_rps = max(s["rps"] for s in all_steps)
        best_step = [s for s in all_steps if s["rps"] == best_rps][0]

        print(
            "  Max sustainable users:  "
            + C.GREEN
            + C.BOLD
            + str(max_sustainable)
            + C.RESET
        )
        if breaking_users:
            print(
                "  Breaking point:         "
                + C.RED
                + C.BOLD
                + str(breaking_users)
                + " users"
                + C.RESET
            )
        else:
            print(
                "  Breaking point:         "
                + C.GREEN
                + "Not reached (all %d users OK)" % MAX_USERS
                + C.RESET
            )
        print(
            "  Peak RPS:               "
            + C.CYAN
            + "%.1f" % best_rps
            + C.RESET
            + " at %d users" % best_step["users"]
        )
        print("  Total test duration:    " + "%.1fs" % (total_ms / 1000))
        print("  Total requests:         %d" % sum(s["total_reqs"] for s in all_steps))
        print("  Total errors:           %d" % sum(s["errors"] for s in all_steps))
        print()

        # Recommendations
        print(C.BOLD + "  RECOMMENDATIONS:" + C.RESET)
        print("  " + "-" * 62)
        if breaking_users is None:
            print(
                "  "
                + C.GREEN
                + "  Server handled all %d users without breaking." % MAX_USERS
                + C.RESET
            )
            print("  " + C.GREEN + "  Consider testing with higher limits." + C.RESET)
        else:
            if breaking_users <= 30:
                print(
                    "  "
                    + C.RED
                    + "  [!] Low breaking point -- investigate thread/connection limits"
                    + C.RESET
                )
                print(
                    "  "
                    + C.RED
                    + "  [!] Check Flask threaded mode, connection pool, and rate limiting"
                    + C.RESET
                )
            elif breaking_users <= 80:
                print(
                    "  "
                    + C.YELLOW
                    + "  [~] Moderate capacity -- good for development/light production"
                    + C.RESET
                )
                print(
                    "  "
                    + C.YELLOW
                    + "  [~] Consider gunicorn with multiple workers for production"
                    + C.RESET
                )
            else:
                print(
                    "  " + C.GREEN + "  [+] Good capacity for production use" + C.RESET
                )

            # Latency at sustainable level
            sus_step = [s for s in all_steps if s["users"] == max_sustainable]
            if sus_step:
                s = sus_step[0]
                print("  " + "    P95 at max sustainable: %.0fms" % s["p95_ms"])
                print("  " + "    RPS at max sustainable: %.1f" % s["rps"])

        print()
        print("  " + "=" * 62)
        print()

    return 0 if breaking_users is None or breaking_users > 50 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(C.YELLOW + "\n  Interrupted." + C.RESET)
        sys.exit(130)
