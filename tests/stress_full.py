"""Full endpoint stress test — fresh run."""

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

c = app.test_client()

# ── Discover real GET endpoints (skip parametrized <xxx> routes) ──
routes = []
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    if rule.rule.startswith("/static") or rule.rule.startswith("/<"):
        continue
    if "<" in rule.rule:
        continue  # skip parametrized - need real IDs
    methods = rule.methods - {"OPTIONS", "HEAD"}
    if "GET" in methods and rule.rule not in SKIP:
        routes.append(rule.rule)

print(f"Discovered {len(routes)} testable GET endpoints")

# ── GET test ──
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
    t.join(timeout=10)
    if t.is_alive() or result[0] is None:
        get_failed.append(("TIMEOUT", path, 0))
        continue
    status, ms = result[0]
    if status in (200, 201):
        get_passed.append((path, ms))
    else:
        get_failed.append((str(status), path, ms))

print("\n=== GET ENDPOINTS ===")
print(f"Total: {len(routes)} | PASSED: {len(get_passed)} | FAILED: {len(get_failed)}")
if get_failed:
    print("--- FAILURES ---")
    for code, path, ms in sorted(get_failed, key=lambda x: x[2]):
        print(f"  {code} {path} ({ms:.0f}ms)")

# Latency breakdown
fast = sum(1 for _, ms in get_passed if ms < 100)
mid = sum(1 for _, ms in get_passed if 100 <= ms < 500)
slow = sum(1 for _, ms in get_passed if 500 <= ms < 1000)
vslow = sum(1 for _, ms in get_passed if ms >= 1000)
print(f"Latency: <100ms={fast} | 100-500ms={mid} | 500ms-1s={slow} | >1s={vslow}")

slow_endpoints = [(p, ms) for p, ms in get_passed if ms >= 1000]
if slow_endpoints:
    print("--- SLOW ENDPOINTS (>1s) ---")
    for p, ms in sorted(slow_endpoints, key=lambda x: -x[1]):
        print(f"  {ms:.0f}ms {p}")

# ── POST test ──
posts = [
    ("/api/calc", {"expression": "2+2"}),
    ("/api/calc/percentage", {"value": 50, "total": 100}),
    ("/api/json/format", {"json_str": '{"a":1}'}),
    ("/api/json/validate", {"json_str": '{"a":1}'}),
    ("/api/markdown/to-html", {"markdown": "# Hello"}),
    ("/api/markdown/strip", {"markdown": "# Hello **world**"}),
    ("/api/similarity/compare", {"text1": "hello", "text2": "world"}),
    ("/api/annotate", {"text": "test sentence"}),
    ("/api/evaluator/evaluate", {"prompt": "test", "response": "ok"}),
    ("/api/reasoning/solve", {"problem": "2+2?"}),
    (
        "/api/decision/analyze",
        {"question": "test", "options": [{"name": "A"}, {"name": "B"}]},
    ),
    ("/api/code-debugger/explain", {"code": "x=1"}),
    ("/api/code-debugger/analyze", {"code": "x=1"}),
    ("/api/prompt-optimizer/analyze", {"prompt": "Tell me about AI"}),
    ("/api/prompt-optimizer/detect", {"prompt": "Tell me about AI"}),
    ("/api/bugfixer/scan", {"code": "x=1"}),
    ("/api/cai/scan", {"code": "print(1)"}),
    ("/api/creative/domains", {"domain": "test"}),
    ("/api/creative/reset", {}),
    ("/api/domain-mastery/reset", {}),
    ("/api/rag/clear", {}),
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
    t.join(timeout=15)
    if t.is_alive() or result[0] is None:
        post_failed.append(("TIMEOUT", path, 0))
        continue
    status, ms = result[0]
    if status in (200, 201):
        post_passed.append((path, ms))
    else:
        post_failed.append((str(status), path, ms))

print("\n=== POST ENDPOINTS ===")
print(f"Total: {len(posts)} | PASSED: {len(post_passed)} | FAILED: {len(post_failed)}")
if post_failed:
    print("--- FAILURES ---")
    for code, path, ms in sorted(post_failed, key=lambda x: x[2]):
        print(f"  {code} {path} ({ms:.0f}ms)")
for p, ms in sorted(post_passed, key=lambda x: -x[1]):
    if ms > 500:
        print(f"  SLOW: {ms:.0f}ms {p}")

# ── Concurrent load ──
print("\n=== CONCURRENT LOAD ===")
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
    list(pool.map(hit_c, routes[:50]))
wall = (time.monotonic() - t0) * 1000
lats = sorted(latencies)
print(f"{min(50, len(routes))} reqs | 20 workers | Wall: {wall:.0f}ms")
print(
    f"Avg: {sum(lats) / len(lats):.0f}ms | P50: {lats[len(lats) // 2]:.0f}ms | P95: {lats[int(len(lats) * 0.95)]:.0f}ms | P99: {lats[int(len(lats) * 0.99)]:.0f}ms"
)
print(f"Errors: {len(errors)} (404s on parametrized routes = expected)")
for e in errors[:5]:
    print(f"  {e}")

# ── Edge cases ──
print("\n=== EDGE CASES ===")
edge_cases = [
    ("404 GET", lambda: c.get("/api/nonexistent-xyz")),
    ("405 DELETE", lambda: c.delete("/api/health")),
    (
        "Null JSON POST",
        lambda: c.post("/api/calc", data="null", content_type="application/json"),
    ),
    (
        "Empty JSON POST",
        lambda: c.post("/api/calc", data="{}", content_type="application/json"),
    ),
    (
        "Malformed JSON",
        lambda: c.post("/api/calc", data="{bad", content_type="application/json"),
    ),
    ("Large payload", lambda: c.post("/api/calc", json={"data": "x" * 50000})),
    (
        "String options",
        lambda: c.post(
            "/api/decision/analyze", json={"question": "x", "options": ["A", "B"]}
        ),
    ),
    ("SQL injection", lambda: c.get("/api/ideas/search?q='; DROP TABLE ideas;--")),
    (
        "XSS payload",
        lambda: c.post("/api/calc", json={"expression": "<script>alert(1)</script>"}),
    ),
]
for name, fn in edge_cases:
    try:
        r = fn()
        ok = r.status_code != 500
        print(f"  {'OK' if ok else 'FAIL'} {name} -> {r.status_code}")
    except Exception as e:
        print(f"  FAIL {name} -> EXCEPTION: {e}")

# ── Key fixes verification ──
print("\n=== FIX VERIFICATION ===")
fixes = [
    (
        "decision/analyze 500 fix",
        lambda: c.post(
            "/api/decision/analyze", json={"question": "x", "options": ["A"]}
        ),
        400,
    ),
    (
        "decision/analyze valid",
        lambda: c.post(
            "/api/decision/analyze", json={"question": "x", "options": [{"name": "A"}]}
        ),
        200,
    ),
    ("finance/transactions", lambda: c.get("/api/finance/transactions"), 200),
    ("finance/report", lambda: c.get("/api/finance/report"), 200),
    ("finance/orbit-cost", lambda: c.get("/api/finance/orbit-cost"), 200),
    ("multi-tier-memory/stats", lambda: c.get("/api/multi-tier-memory/stats"), 200),
    ("whatif/stats", lambda: c.get("/api/whatif/stats"), 200),
]
for name, fn, expected in fixes:
    t0 = time.time()
    r = fn()
    ms = (time.time() - t0) * 1000
    status = "PASS" if r.status_code == expected else "FAIL"
    print(f"  {status} {name} -> {r.status_code} ({expected}) [{ms:.0f}ms]")

print("\n=== ALL DONE ===")
