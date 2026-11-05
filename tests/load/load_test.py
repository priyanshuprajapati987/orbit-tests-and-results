#!/usr/bin/env python3
"""Load / stress runner for ORBIT's HTTP API.

Drives real HTTP requests against a running ORBIT server with a fixed
concurrency level for a fixed wall-clock duration and prints a single JSON
document with throughput and latency percentiles.

Examples
--------
Load run (60s @ 50 concurrent clients):

    python tests/load/load_test.py --url http://127.0.0.1:5000 \
        --endpoint /api/health --concurrency 50 --duration 60

Stress ramp (10 -> 50 -> 100 -> 200 -> 400):

    python tests/load/load_test.py --url http://127.0.0.1:5000 \
        --endpoint /api/health --ramp 10,50,100,200,400 --duration 30

Authentication: pass --api-key (sent as X-API-Key) for protected endpoints.
Public paths (/api/health) work without a key.

No network beyond the target URL; no files written.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except ImportError:  # pragma: no cover - dependency is part of requirements
    print(json.dumps({"error": "requests is required"}), file=sys.stderr)
    raise SystemExit(2) from None


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile on an already-sorted non-empty list."""
    if not sorted_values:
        return 0.0
    rank = max(1, int(round((pct / 100.0) * len(sorted_values))))
    return sorted_values[min(rank, len(sorted_values)) - 1]


class _RateGate:
    """Global pacing gate: workers serialise on it so the aggregate attempt
    rate never exceeds ``rps``. Needed because ORBIT's per-IP token buckets
    (60 rps global, 30 rps /api/health) shed unpaced load as 429, which would
    otherwise make every run measure the limiter instead of the app."""

    def __init__(self, rps: float):
        self._interval = 1.0 / rps if rps and rps > 0 else 0.0
        self._next = time.perf_counter()
        self._lock = threading.Lock()

    def wait(self) -> None:
        if not self._interval:
            return
        with self._lock:
            now = time.perf_counter()
            if self._next < now:
                self._next = now
            slot = self._next
            self._next += self._interval
        delay = slot - time.perf_counter()
        if delay > 0:
            time.sleep(delay)


def run_load(
    url: str,
    endpoint: str,
    concurrency: int,
    duration: float,
    api_key: str | None = None,
    method: str = "GET",
    timeout: float = 10.0,
    body: str | None = None,
    max_rps: float = 0.0,
) -> dict:
    """Run one load phase and return the metrics document."""
    url = url.rstrip("/") + "/" + endpoint.lstrip("/")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    if body:
        headers["Content-Type"] = "application/json"

    lock = threading.Lock()
    latencies: list[float] = []
    status_counts: Counter = Counter()
    error_types: Counter = Counter()
    error_samples: list[str] = []
    seen_samples: set = set()
    transport_errors = 0
    total = 0

    start_at = time.perf_counter()
    deadline = start_at + duration
    barrier = threading.Barrier(concurrency, timeout=30)
    gate = _RateGate(max_rps)

    def one() -> None:
        nonlocal transport_errors, total
        # One pooled Session per worker: keep-alive. Without it every request
        # opens a fresh socket, which exhausts Windows ephemeral ports under
        # load and the run measures the CLIENT instead of the server.
        from requests.adapters import HTTPAdapter

        session = requests.Session()
        session.mount("http://", HTTPAdapter(pool_maxsize=32))
        # Align all workers so concurrency is real, not ramp-up shaped.
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            session.close()
            return
        try:
            while time.perf_counter() < deadline:
                gate.wait()
                t0 = time.perf_counter()
                try:
                    if method.upper() == "POST":
                        resp = session.post(
                            url, headers=headers, data=body, timeout=timeout
                        )
                    else:
                        resp = session.get(url, headers=headers, timeout=timeout)
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    with lock:
                        latencies.append(elapsed)
                        status_counts[resp.status_code] += 1
                        total += 1
                except Exception as exc:
                    with lock:
                        transport_errors += 1
                        error_types[type(exc).__name__] += 1
                        if len(error_samples) < 5:
                            sample = f"{type(exc).__name__}: {str(exc)[:120]}"
                            if sample not in seen_samples:
                                seen_samples.add(sample)
                                error_samples.append(sample)
                        total += 1
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one) for _ in range(concurrency)]
        for fut in futures:
            fut.result()

    wall = max(time.perf_counter() - start_at, 1e-9)
    finished = sorted(latencies)
    errors = transport_errors + sum(
        n for code, n in status_counts.items() if code >= 400
    )

    return {
        "url": url,
        "endpoint": endpoint,
        "method": method.upper(),
        "concurrency": concurrency,
        "pacing_rps": max_rps or None,
        "duration_s": round(wall, 3),
        "requests": total,
        "requests_ok": len(latencies),
        "http_2xx": sum(n for c, n in status_counts.items() if 200 <= c < 300),
        "http_429": status_counts.get(429, 0),
        "errors": errors,
        "error_rate": round(errors / total, 6) if total else 0.0,
        "error_types": dict(error_types.most_common()),
        "error_samples": error_samples,
        "rps": round(total / wall, 2),
        "p50_ms": round(_percentile(finished, 50), 2),
        "p95_ms": round(_percentile(finished, 95), 2),
        "p99_ms": round(_percentile(finished, 99), 2),
        "max_ms": round(finished[-1], 2) if finished else 0.0,
        "status_counts": {str(k): v for k, v in sorted(status_counts.items())},
    }


def parse_ramp(value: str) -> list[int]:
    levels = [int(v) for v in value.replace(";", ",").split(",") if v.strip()]
    if not levels:
        raise argparse.ArgumentTypeError("ramp needs at least one concurrency level")
    if any(v < 1 for v in levels):
        raise argparse.ArgumentTypeError("concurrency levels must be >= 1")
    return levels


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="load_test", description="ORBIT HTTP load / stress runner"
    )
    p.add_argument("--url", default="http://127.0.0.1:5000", help="base URL")
    p.add_argument("--endpoint", default="/api/health", help="path to hit")
    p.add_argument("--concurrency", type=int, default=25, help="parallel clients")
    p.add_argument(
        "--ramp",
        type=parse_ramp,
        default=None,
        help="comma list, e.g. 10,50,100,200,400 (overrides --concurrency)",
    )
    p.add_argument("--duration", type=float, default=30.0, help="seconds per level")
    p.add_argument("--api-key", default=None, help="X-API-Key header value")
    p.add_argument("--method", default="GET", choices=["GET", "POST"])
    p.add_argument("--data", default=None, help="JSON body for POST")
    p.add_argument("--timeout", type=float, default=10.0, help="per-request timeout")
    p.add_argument(
        "--max-rps",
        type=float,
        default=0.0,
        help="pace the aggregate attempt rate (0 = unpaced); keeps runs under "
        "ORBIT's per-IP token buckets so results measure the app, not the limiter",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    levels = args.ramp or [args.concurrency]

    doc: dict = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target": args.url.rstrip("/") + "/" + args.endpoint.lstrip("/"),
        "duration_s_per_level": args.duration,
        "levels": len(levels),
    }

    results = []
    for level in levels:
        m = run_load(
            url=args.url,
            endpoint=args.endpoint,
            concurrency=level,
            duration=args.duration,
            api_key=args.api_key,
            method=args.method,
            timeout=args.timeout,
            body=args.data,
            max_rps=args.max_rps,
        )
        results.append(m)
        print(
            f"[load] concurrency={level:4d} rps={m['rps']:8.2f} "
            f"p50={m['p50_ms']:8.2f}ms p95={m['p95_ms']:9.2f}ms "
            f"p99={m['p99_ms']:9.2f}ms errors={m['errors']} "
            f"status={m['status_counts']}",
            file=sys.stderr,
        )

    if len(results) == 1:
        doc.update(results[0])
    else:
        doc["ramp"] = results
        baseline = results[0]["rps"]
        for r in results:
            r["rps_vs_first"] = round(r["rps"] / baseline, 3) if baseline else None
        doc["summary"] = {
            "peak_rps": max(r["rps"] for r in results),
            "worst_p95_ms": max(r["p95_ms"] for r in results),
            "total_requests": sum(r["requests"] for r in results),
            "total_errors": sum(r["errors"] for r in results),
            "first_error_level": next(
                (r["concurrency"] for r in results if r["errors"]), None
            ),
        }

    print(json.dumps(doc, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
