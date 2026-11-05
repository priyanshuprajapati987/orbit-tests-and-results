"""
ORBIT New Features Stress Test
==============================
Focused stress tests for 6 new features: Image Generator, Telegram Bot,
Discord Bot, RAG Engine, Marketplace, and Cron Scheduler.

Each feature gets 20 concurrent requests. Measures latency distribution
and error rate. Prints a comparison table.

Usage: py tests/new_features_stress.py [--url http://127.0.0.1:5000]
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

DEFAULT_BASE_URL = "http://127.0.0.1:5000"
API_KEY = os.environ.get("ORBIT_API_KEY", "")
REQUEST_TIMEOUT = 30
CONCURRENT = 20


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


def _banner():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print()
    print(
        C.CYAN
        + C.BOLD
        + "  ================================================================",
        C.RESET,
    )
    print(C.CYAN + C.BOLD + "    ORBIT New Features Stress Test  |  " + ts, C.RESET)
    print(
        C.CYAN + C.BOLD + "    %d concurrent requests per feature" % CONCURRENT, C.RESET
    )
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


def _worker(base_url, method, path, body, results, idx):
    status, lat, err = _http(base_url, method, path, body)
    results[idx] = (status, lat, err)


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
    elif rate < 10:
        return C.YELLOW + "%5.1f%%" % rate + C.RESET
    else:
        return C.RED + "%5.1f%%" % rate + C.RESET


def _run_test(base_url, name, method, path, body, concurrent):
    results = [None] * concurrent
    threads = []

    t0 = time.perf_counter()
    for i in range(concurrent):
        t = threading.Thread(
            target=_worker, args=(base_url, method, path, body, results, i)
        )
        t.daemon = True
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=REQUEST_TIMEOUT + 5)
    wall_ms = (time.perf_counter() - t0) * 1000

    lats = []
    errors = 0
    status_codes = defaultdict(int)

    for r in results:
        if r is None:
            errors += 1
            status_codes["timeout"] += 1
            continue
        status, lat, err = r
        lats.append(lat)
        status_codes[status] += 1
        if err or status >= 400:
            errors += 1

    lats.sort()
    error_rate = (errors / concurrent * 100) if concurrent > 0 else 0

    return {
        "name": name,
        "method": method,
        "path": path,
        "total": concurrent,
        "errors": errors,
        "error_rate": error_rate,
        "wall_ms": wall_ms,
        "lats": lats,
        "avg_ms": mean(lats) if lats else 0,
        "min_ms": lats[0] if lats else 0,
        "max_ms": lats[-1] if lats else 0,
        "p50_ms": _percentile(lats, 50),
        "p95_ms": _percentile(lats, 95),
        "p99_ms": _percentile(lats, 99),
        "rps": (concurrent / (wall_ms / 1000)) if wall_ms > 0 else 0,
        "status_codes": dict(status_codes),
    }


# â”€â”€â”€ Feature Definitions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

FEATURES = [
    {
        "name": "Image Generator",
        "section_label": "POST /api/image-gen/generate",
        "tests": [
            {
                "method": "POST",
                "path": "/api/image-gen/generate",
                "body": {
                    "prompt": "A futuristic cityscape at sunset",
                    "model": "dall-e-3",
                },
            },
        ],
    },
    {
        "name": "Telegram Bot",
        "section_label": "POST /api/telegram/send",
        "tests": [
            {
                "method": "POST",
                "path": "/api/telegram/send",
                "body": {"chat_id": "test", "text": "Stress test message"},
            },
        ],
    },
    {
        "name": "Discord Bot",
        "section_label": "POST /api/discord/send",
        "tests": [
            {
                "method": "POST",
                "path": "/api/discord/send",
                "body": {"channel_id": "test", "content": "Stress test message"},
            },
        ],
    },
    {
        "name": "RAG Engine",
        "section_label": "RAG ingest + query",
        "tests": [
            {
                "method": "POST",
                "path": "/api/rag/ingest",
                "body": {
                    "text": "The quick brown fox jumps over the lazy dog. This is test content for RAG indexing.",
                    "metadata": {"source": "stress_test"},
                },
            },
            {
                "method": "POST",
                "path": "/api/rag/query",
                "body": {"query": "quick brown fox", "top_k": 3},
            },
        ],
    },
    {
        "name": "Marketplace",
        "section_label": "Marketplace browse + install",
        "tests": [
            {
                "method": "POST",
                "path": "/api/marketplace/browse",
                "body": {"category": "all"},
            },
            {
                "method": "POST",
                "path": "/api/marketplace/install",
                "body": {"skill_id": "test-skill-stress"},
            },
        ],
    },
    {
        "name": "Cron Scheduler",
        "section_label": "POST /api/scheduler/add",
        "tests": [
            {
                "method": "POST",
                "path": "/api/scheduler/add",
                "body": {
                    "name": "stress-test-task",
                    "cron": "0 * * * *",
                    "command": "echo stress",
                    "enabled": True,
                },
            },
        ],
    },
]


# â”€â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def main():
    parser = argparse.ArgumentParser(description="ORBIT New Features Stress Test")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Base URL")
    parser.add_argument(
        "--concurrent",
        type=int,
        default=CONCURRENT,
        help="Concurrent requests per test",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    concurrent = args.concurrent
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

    print("  Concurrent requests per test: %d" % concurrent)
    print("  Total features: %d" % len(FEATURES))
    print()

    all_results = []
    total_start = time.perf_counter()
    test_idx = 0

    # Count total sub-tests
    total_tests = sum(len(feat["tests"]) for feat in FEATURES)

    try:
        for feat in FEATURES:
            name = feat["name"]
            print(C.BOLD + C.CYAN + "  -- %s --" % name + C.RESET)

            for sub in feat["tests"]:
                test_idx += 1
                method = sub["method"]
                path = sub["path"]
                body = sub["body"]
                label = "%s %s" % (method, path)

                progress = "[%d/%d]" % (test_idx, total_tests)
                sys.stdout.write("    %s %-35s " % (C.DIM + progress + C.RESET, label))
                sys.stdout.flush()

                stats = _run_test(base_url, name, method, path, body, concurrent)
                stats["feature"] = name
                all_results.append(stats)

                err_s = _color_err(stats["error_rate"])
                p95_s = _color_ms(stats["p95_ms"])
                rps_s = C.CYAN + "%5.1f" % stats["rps"] + C.RESET
                print("p95=%s  err=%s  rps=%s" % (p95_s, err_s, rps_s))

            print()

    except KeyboardInterrupt:
        print()
        print(C.YELLOW + "  Interrupted by user" + C.RESET)

    total_ms = (time.perf_counter() - total_start) * 1000

    # â”€â”€ Per-Feature Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(
        C.BOLD
        + C.WHITE
        + "  ================================================================"
        + C.RESET
    )
    print(C.BOLD + "  FEATURE COMPARISON TABLE" + C.RESET)
    print("  " + "=" * 62)
    print()

    hdr = "  %-18s %5s %5s %7s %9s %9s %9s %9s" % (
        "Feature",
        "Reqs",
        "Errs",
        "Err%",
        "Avg",
        "P50",
        "P95",
        "RPS",
    )
    print(C.BOLD + hdr + C.RESET)
    print("  " + "-" * 75)

    feature_totals = defaultdict(
        lambda: {"lats": [], "errors": 0, "total": 0, "wall_ms": 0}
    )
    for r in all_results:
        feat_name = r["feature"]
        feature_totals[feat_name]["lats"].extend(r["lats"])
        feature_totals[feat_name]["errors"] += r["errors"]
        feature_totals[feat_name]["total"] += r["total"]
        feature_totals[feat_name]["wall_ms"] = max(
            feature_totals[feat_name]["wall_ms"], r["wall_ms"]
        )

    for feat in FEATURES:
        name = feat["name"]
        data = feature_totals[name]
        lats = sorted(data["lats"])
        errs = data["errors"]
        total = data["total"]
        err_rate = (errs / total * 100) if total > 0 else 0
        avg = mean(lats) if lats else 0
        p50 = _percentile(lats, 50)
        p95 = _percentile(lats, 95)
        rps = (total / (data["wall_ms"] / 1000)) if data["wall_ms"] > 0 else 0

        print(
            "  %-18s %5d %5d %s %s %s %s %s"
            % (
                name,
                total,
                errs,
                _color_err(err_rate),
                _color_ms(avg),
                _color_ms(p50),
                _color_ms(p95),
                C.CYAN + "%5.1f" % rps + C.RESET,
            )
        )

    # â”€â”€ Aggregate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    all_lats = []
    total_errors = 0
    total_requests = 0
    for r in all_results:
        all_lats.extend(r["lats"])
        total_errors += r["errors"]
        total_requests += r["total"]

    all_lats.sort()
    agg_err = (total_errors / total_requests * 100) if total_requests > 0 else 0
    agg_rps = (total_requests / (total_ms / 1000)) if total_ms > 0 else 0

    print("  " + "-" * 75)
    print(
        C.BOLD
        + "  %-18s %5d %5d %s %s %s %s %s"
        % (
            "AGGREGATE",
            total_requests,
            total_errors,
            _color_err(agg_err),
            _color_ms(mean(all_lats) if all_lats else 0),
            _color_ms(_percentile(all_lats, 50)),
            _color_ms(_percentile(all_lats, 95)),
            C.CYAN + "%5.1f" % agg_rps + C.RESET,
        )
        + C.RESET
    )

    # â”€â”€ Verdict â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print()
    print(C.BOLD + "  VERDICT" + C.RESET)
    print("  " + "-" * 62)
    print("  Total requests:    %d" % total_requests)
    print("  Total errors:      %d" % total_errors)
    print("  Error rate:        %s" % _color_err(agg_err))
    print("  Overall RPS:       %.1f" % agg_rps)
    print("  Total test time:   %.1fs" % (total_ms / 1000))

    # Feature health
    print()
    print(C.BOLD + "  FEATURE HEALTH:" + C.RESET)
    all_healthy = True
    for feat in FEATURES:
        name = feat["name"]
        data = feature_totals[name]
        total = data["total"]
        errs = data["errors"]
        err_rate = (errs / total * 100) if total > 0 else 0

        if err_rate == 0:
            icon = C.GREEN + "[HEALTHY]" + C.RESET
        elif err_rate < 10:
            icon = C.YELLOW + "[DEGRADED]" + C.RESET
            all_healthy = False
        else:
            icon = C.RED + "[FAILING]" + C.RESET
            all_healthy = False

        print("    %-18s %s  (%d/%d succeeded)" % (name, icon, total - errs, total))

    print()
    if all_healthy:
        print("  " + C.GREEN + C.BOLD + "  All features passed!" + C.RESET)
    else:
        print("  " + C.YELLOW + "  Some features degraded -- check endpoints" + C.RESET)

    print()
    print("  " + "=" * 62)
    print()

    return 0 if all_healthy else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(C.YELLOW + "\n  Interrupted." + C.RESET)
        sys.exit(130)
