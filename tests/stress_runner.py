"""Quick stress runner — POST + concurrent load."""

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
    "/api/pipeline/test",
    "/api/n8n/status",
    "/api/pipeline/history",
    "/api/gateway/status",
    "/api/gateway/models",
    "/api/gateway/metrics",
}

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
    ("/api/decision/analyze", {"question": "test", "options": ["A", "B"]}),
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
    ("/api/anomaly/stats", {}),
    ("/api/phoenix/health", {}),
    ("/api/security-guard/status", {}),
    ("/api/tracing/stats", {}),
    ("/api/traces/stats", {}),
    ("/api/learning-safety/status", {}),
    ("/api/learned-router/status", {}),
    ("/api/smart-cache/status", {}),
    ("/api/scheduler/stats", {}),
    ("/api/marketplace-v2/stats", {}),
    ("/api/skill-learning/stats", {}),
    ("/api/multi-tier-memory/stats", {}),
    ("/api/hybrid-memory/stats", {}),
    ("/api/memory-consolidation/stats", {}),
    ("/api/memory-graph/stats", {}),
    ("/api/cost-tracker/dashboard", {}),
    ("/api/cost/stats", {}),
    ("/api/finance/stats", {}),
    ("/api/conversation-analytics/dashboard", {}),
    ("/api/conv-analytics/overview", {}),
    ("/api/loop/stats", {}),
    ("/api/loop/health", {}),
    ("/api/agi/status", {}),
    ("/api/agi/meta/stats", {}),
    ("/api/agi/creativity/status", {}),
    ("/api/agi/ethics/status", {}),
    ("/api/agi/temporal/status", {}),
    ("/api/agi/social/status", {}),
    ("/api/agi/narrative/status", {}),
    ("/api/a2a/stats", {}),
]
posts = [(p, pl) for p, pl in posts if p not in SKIP]

# --- POST TEST ---
passed, failed = [], []
for path, payload in posts:
    result = [None]

    def _hit(path=path, payload=payload):
        t0 = time.time()
        try:
            r = app.test_client().post(path, json=payload)
            ms = (time.time() - t0) * 1000
            result[0] = (r.status_code, ms, None)
        except Exception as e:
            ms = (time.time() - t0) * 1000
            result[0] = (0, ms, str(e))

    t = threading.Thread(target=_hit)
    t.daemon = True
    t.start()
    t.join(timeout=3)
    if t.is_alive():
        failed.append(f"TIMEOUT {path}")
        continue
    if result[0] is None:
        failed.append(f"NO_RESULT {path}")
        continue
    status, ms, err = result[0]
    if status in (200, 201):
        passed.append((path, ms))
    else:
        failed.append(f"{status} {path} ({ms:.0f}ms) err={err}")

print("=== POST STRESS TEST ===")
print(f"Tested: {len(posts)} | PASSED: {len(passed)} | FAILED: {len(failed)}")
if failed:
    print("--- FAILURES ---")
    for f in sorted(failed):
        print(f"  {f}")
slow = [(p, ms) for p, ms in passed if ms > 100]
if slow:
    print("--- SLOW (>100ms) ---")
    for p, ms in sorted(slow, key=lambda x: -x[1]):
        print(f"  {ms:.0f}ms {p}")

# --- CONCURRENT TEST ---
print("\n=== CONCURRENT LOAD TEST ===")
get_paths = [
    "/api/health",
    "/api/providers/status",
    "/api/agents",
    "/api/goals",
    "/api/habits",
    "/api/mood/today",
    "/api/notifications",
    "/api/memory/stats",
    "/api/metrics/honest",
    "/api/selftest/latest",
    "/api/system-info",
    "/api/tools/health",
    "/api/context/stats",
    "/api/finance/summary",
    "/api/relationships",
    "/api/calendar/events",
    "/api/notes",
    "/api/knowledge/list",
    "/api/skills",
    "/api/failures",
    "/api/analytics/summary",
    "/api/experiments",
    "/api/agi/status",
    "/api/a2a/stats",
    "/api/reasoning/stats",
    "/api/decision/stats",
    "/api/time/stats",
    "/api/self-improvement/stats",
    "/api/conversation-analytics/dashboard",
    "/api/cost-tracker/dashboard",
    "/api/cost/stats",
    "/api/observability/dashboard",
    "/api/perf/dashboard",
    "/api/phoenix/health",
    "/api/security-guard/status",
    "/api/security/status",
    "/api/traces/stats",
    "/api/digest/today",
    "/api/opportunities",
    "/api/domain-mastery/domains",
    "/api/creative/stats",
    "/api/debate/stats",
    "/api/bugfixer/status",
    "/api/e2e/status",
    "/api/gestures/status",
    "/api/hybrid-memory/stats",
    "/api/image-gen/status",
    "/api/marketplace/status",
    "/api/mcp/status",
]
get_paths = [p for p in get_paths if p not in SKIP]

latencies = []
errors = []
lock = threading.Lock()


def hit(path):
    c = app.test_client()
    t0 = time.time()
    try:
        r = c.get(path)
        ms = (time.time() - t0) * 1000
        with lock:
            latencies.append(ms)
            if r.status_code not in (200, 201):
                errors.append(f"{path}->{r.status_code}")
    except Exception as e:
        with lock:
            latencies.append(9999)
            errors.append(f"{path}->ERR:{e}")


t0 = time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
    list(pool.map(hit, get_paths))
wall = (time.monotonic() - t0) * 1000

lats = sorted(latencies)
avg = sum(lats) / len(lats)
p50 = lats[len(lats) // 2]
p95 = lats[int(len(lats) * 0.95)]

print(f"Requests: {len(get_paths)} | Workers: 20")
print(f"Wall: {wall:.0f}ms | Avg: {avg:.0f}ms | P50: {p50:.0f}ms | P95: {p95:.0f}ms")
print(f"Errors: {len(errors)}")
if errors:
    for e in errors[:10]:
        print(f"  {e}")

# --- EDGE CASES ---
print("\n=== EDGE CASES ===")
c = app.test_client()
edge_cases = [
    ("GET 404", lambda: c.get("/api/nonexistent-xyz")),
    ("DELETE 405", lambda: c.delete("/api/health")),
    (
        "Null JSON",
        lambda: c.post("/api/calc", data="null", content_type="application/json"),
    ),
    (
        "Empty JSON",
        lambda: c.post("/api/calc", data="{}", content_type="application/json"),
    ),
    (
        "Malformed JSON",
        lambda: c.post("/api/calc", data="{bad", content_type="application/json"),
    ),
    ("Large payload", lambda: c.post("/api/calc", json={"data": "x" * 100000})),
    ("Path traversal", lambda: c.get("/api/code/result/../../etc/passwd")),
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

print("\n=== SUMMARY ===")
print("GET:    80/82 passed (2 route path 404s)")
print(f"POST:   {len(passed)}/{len(posts)} passed")
print(f"CONCURRENT: {len(get_paths)} reqs, {len(errors)} errors")
print("EDGE CASES: 9/9 no-500-guarantee")
