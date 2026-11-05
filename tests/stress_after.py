"""Full stress test — AFTER fixes. Inline, no external deps."""

import concurrent.futures
import os
import sys
import threading
import time

os.environ["ORBIT_SKIP_STARTUP"] = "1"
os.environ["ORBIT_API_AUTH_ENABLED"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orbit.orbit.server import create_app

app = create_app()
app.config["TESTING"] = True

SKIP = {
    "/api/pipeline/history",
    "/api/gateway/status",
    "/api/gateway/models",
    "/api/gateway/metrics",
}

# Discover all GET routes
c = app.test_client()
routes = []
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    if rule.rule.startswith("/static") or rule.rule.startswith("/<"):
        continue
    methods = rule.methods - {"OPTIONS", "HEAD"}
    if "GET" in methods and rule.rule not in SKIP:
        routes.append(rule.rule)

print(f"Discovered {len(routes)} GET endpoints")

# GET test
get_passed = []
get_failed = []
for path in routes:
    result = [None]

    def _hit(p=path):
        t0 = time.time()
        try:
            r = c.get(p)
            result[0] = (r.status_code, (time.time() - t0) * 1000)
        except Exception:
            result[0] = (0, (time.time() - t0) * 1000)

    t = threading.Thread(target=_hit)
    t.daemon = True
    t.start()
    t.join(timeout=5)
    if t.is_alive() or result[0] is None:
        get_failed.append(f"TIMEOUT {path}")
        continue
    status, ms = result[0]
    if status in (200, 201):
        get_passed.append((path, ms))
    else:
        get_failed.append(f"{status} {path} ({ms:.0f}ms)")

print(
    f"\n=== GET === {len(get_passed)}/{len(routes)} passed | {len(get_failed)} failed"
)
for f in sorted(get_failed):
    print(f"  FAIL: {f}")
slow = [(p, ms) for p, ms in get_passed if ms > 1000]
for p, ms in sorted(slow, key=lambda x: -x[1]):
    print(f"  SLOW: {ms:.0f}ms {p}")

# POST test
posts = [
    ("/api/calc", {"expression": "2+2"}),
    (
        "/api/decision/analyze",
        {"question": "test", "options": [{"name": "A"}, {"name": "B"}]},
    ),
    ("/api/bugfixer/scan", {"code": "x=1"}),
    ("/api/markdown/to-html", {"markdown": "# Hello"}),
    ("/api/multi-tier-memory/stats", {}),
    ("/api/finance/transactions", {}),
    ("/api/finance/report", {}),
    ("/api/finance/orbit-cost", {}),
]
post_passed = []
post_failed = []
for path, payload in posts:
    result = [None]

    def _hit2(p=path, pl=payload):
        t0 = time.time()
        try:
            r = app.test_client().post(p, json=pl)
            result[0] = (r.status_code, (time.time() - t0) * 1000)
        except Exception:
            result[0] = (0, (time.time() - t0) * 1000)

    t = threading.Thread(target=_hit2)
    t.daemon = True
    t.start()
    t.join(timeout=12)
    if t.is_alive() or result[0] is None:
        post_failed.append(f"TIMEOUT {path}")
        continue
    status, ms = result[0]
    if status in (200, 201):
        post_passed.append((path, ms))
    else:
        post_failed.append(f"{status} {path} ({ms:.0f}ms)")

print(
    f"\n=== POST === {len(post_passed)}/{len(posts)} passed | {len(post_failed)} failed"
)
for f in sorted(post_failed):
    print(f"  FAIL: {f}")
for p, ms in sorted(post_passed, key=lambda x: -x[1]):
    if ms > 500:
        print(f"  SLOW: {ms:.0f}ms {p}")

# Concurrent load
print("\n=== CONCURRENT ===")
concurrent_paths = routes[:50]
latencies = []
errors = []
lock = threading.Lock()


def hit_c(path):
    cc = app.test_client()
    t0 = time.time()
    try:
        r = cc.get(path)
        ms = (time.time() - t0) * 1000
        with lock:
            latencies.append(ms)
            if r.status_code not in (200, 201):
                errors.append(f"{path}->{r.status_code}")
    except:
        with lock:
            latencies.append(9999)
            errors.append(f"{path}->ERR")


t0 = time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
    list(pool.map(hit_c, concurrent_paths))
wall = (time.monotonic() - t0) * 1000
lats = sorted(latencies)
print(f"{len(concurrent_paths)} reqs, 20 workers, {wall:.0f}ms wall")
print(
    f"Avg: {sum(lats) / len(lats):.0f}ms P50: {lats[len(lats) // 2]:.0f}ms P95: {lats[int(len(lats) * 0.95)]:.0f}ms P99: {lats[int(len(lats) * 0.99)]:.0f}ms"
)
print(f"Errors: {len(errors)}")
for e in errors[:5]:
    print(f"  {e}")

# Edge cases
print("\n=== EDGE CASES ===")
cases = [
    ("404", lambda: c.get("/api/nonexistent")),
    ("405", lambda: c.delete("/api/health")),
    ("null", lambda: c.post("/api/calc", data="null", content_type="application/json")),
    ("empty", lambda: c.post("/api/calc", data="{}", content_type="application/json")),
    (
        "bad json",
        lambda: c.post("/api/calc", data="{bad", content_type="application/json"),
    ),
]
for name, fn in cases:
    try:
        r = fn()
        print(f"  OK {name} -> {r.status_code}")
    except Exception as e:
        print(f"  FAIL {name} -> {e}")
