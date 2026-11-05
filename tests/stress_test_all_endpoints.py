"""
ORBIT Stress Test — Minimal Fast Version
=========================================
Tests only endpoints with ZERO external dependencies.
Run: py -m pytest tests/stress_test_all_endpoints.py -v -s
"""

import concurrent.futures
import os
import sys
import threading
import time

import pytest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

project_root = os.path.join(os.path.dirname(__file__), "..")
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def _build_app():
    from orbit.orbit.server import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["SERVER_NAME"] = "localhost"
    return app


# Only endpoints that are 100% local (no Ollama, no network, no file I/O)
FAST_GET = [
    "/api/health",
    "/api/providers/status",
    "/api/agents",
    "/api/model-info",
    "/api/selftest/latest",
    "/api/selftest/history",
    "/api/system-info",
    "/api/tools/health",
    "/api/memory/stats",
    "/api/context/stats",
    "/api/metrics/honest",
    "/api/metrics/system",
    "/api/notifications",
    "/api/notifications/unread-count",
    "/api/goals",
    "/api/goals/stats",
    "/api/habits",
    "/api/habits/streaks",
    "/api/habits/report",
    "/api/mood/today",
    "/api/mood/history",
    "/api/mood/patterns",
    "/api/mood/weekly",
    "/api/mood/tone",
    "/api/ideas/list",
    "/api/ideas/top",
    "/api/finance/summary",
    "/api/finance/transactions",
    "/api/finance/report",
    "/api/finance/budgets",
    "/api/finance/orbit-cost",
    "/api/finance/stats",
    "/api/finance/roi",
    "/api/finance/projects",
    "/api/relationships",
    "/api/relationships/reminders",
    "/api/relationships/birthdays",
    "/api/calendar/events",
    "/api/calendar/today",
    "/api/calendar/upcoming",
    "/api/email/config",
    "/api/notes",
    "/api/notes/stats",
    "/api/knowledge/list",
    "/api/knowledge/stats",
    "/api/skills",
    "/api/skills/categories",
    "/api/skill-learning/dashboard",
    "/api/skill-learning/stats",
    "/api/failures",
    "/api/failures/stats",
    "/api/learning/lessons",
    "/api/learning/dashboard",
    "/api/learning/adoption",
    "/api/analytics/summary",
    "/api/analytics/weekly",
    "/api/analytics/agents",
    "/api/analytics/peak-hours",
    "/api/experiments",
    "/api/experiments/stats",
    "/api/agi/status",
    "/api/agi/reflection/stats",
    "/api/agi/meta/stats",
    "/api/agi/curiosity/status",
    "/api/agi/tom/status",
    "/api/agi/causal/status",
    "/api/agi/counterfactual/status",
    "/api/agi/analogical/status",
    "/api/agi/knowledge/status",
    "/api/agi/creativity/status",
    "/api/agi/ethics/status",
    "/api/agi/temporal/status",
    "/api/agi/social/status",
    "/api/agi/narrative/status",
    "/api/a2a/stats",
    "/api/a2a/tasks",
    "/.well-known/agent.json",
    "/api/reasoning/stats",
    "/api/decision/stats",
    "/api/decision/history",
    "/api/decision/personalities",
    "/api/time/stats",
    "/api/time/streak",
    "/api/time/active",
    "/api/time/report",
    "/api/pipeline/test",
    "/api/pipeline/history",
    "/api/self-improvement/stats",
    "/api/self-improvement/plans",
    "/api/enhancements/dashboard",
    "/api/conversation-analytics/dashboard",
    "/api/conv-analytics/overview",
    "/api/conv-analytics/stats",
    "/api/cost-tracker/dashboard",
    "/api/cost-tracker/budget",
    "/api/cost/stats",
    "/api/cost/budget",
    "/api/cost/forecast",
    "/api/observability/dashboard",
    "/api/observability/routing",
    "/api/observability/tasks",
    "/api/observability/tools",
    "/api/observability/memory",
    "/api/perf/dashboard",
    "/api/perf/agents",
    "/api/perf/tools",
    "/api/perf/queries",
    "/api/performance/stats",
    "/api/performance/metrics",
    "/api/phoenix/health",
    "/api/phoenix/stats",
    "/api/security-guard/status",
    "/api/security-guard/defenses",
    "/api/security/status",
    "/api/security-hardening/status",
    "/api/tracing/stats",
    "/api/traces/stats",
    "/api/traces/errors",
    "/api/digest/history",
    "/api/digest/today",
    "/api/opportunities",
    "/api/opportunities/stats",
    "/api/domain-mastery/domains",
    "/api/creative/stats",
    "/api/debate/stats",
    "/api/debate/history",
    "/api/auto-heal/status",
    "/api/bugfixer/status",
    "/api/cai/status",
    "/api/code-debugger/stats",
    "/api/dep-scanner/status",
    "/api/e2e/status",
    "/api/fanout/stats",
    "/api/file-organizer/stats",
    "/api/firecrawl/status",
    "/api/firecrawl/stats",
    "/api/gateway/status",
    "/api/gateway/models",
    "/api/gateway/metrics",
    "/api/gestures/status",
    "/api/gestures/config",
    "/api/hybrid-memory/stats",
    "/api/image-gen/status",
    "/api/learned-router/status",
    "/api/learning-safety/status",
    "/api/marketplace/status",
    "/api/marketplace/browse",
    "/api/marketplace-v2/stats",
    "/api/mcp/status",
    "/api/memory-consolidation/stats",
    "/api/memory-graph/stats",
    "/api/memory/profile",
    "/api/moa/stats",
    "/api/mode",
    "/api/model-benchmark/leaderboard",
    "/api/multi-tier-memory/stats",
    "/api/multimodal/capabilities",
    "/api/n8n/status",
    "/api/obsidian/status",
    "/api/oracle/status",
    "/api/horizon/status",
    "/api/pomodoro/status",
    "/api/proactive/status",
    "/api/proactive/reminders",
    "/api/prompt-optimizer/stats",
    "/api/prompts/stats",
    "/api/rag/status",
    "/api/rag/documents",
    "/api/rate-limiter/status",
    "/api/recorder/status",
    "/api/requirements/list",
    "/api/requirements/status",
    "/api/evaluator/stats",
    "/api/screen-control/status",
    "/api/scheduler/stats",
    "/api/scheduler/tasks",
    "/api/smart-actions/list",
    "/api/smart-cache/status",
    "/api/stress/status",
    "/api/summarizer/stats",
    "/api/sync/status",
    "/api/sync/peers",
    "/api/task",
    "/api/tasks",
    "/api/tasks/board",
    "/api/tasks/backlog",
    "/api/tasks/stats",
    "/api/telegram/status",
    "/api/team/current",
    "/api/team/stats",
    "/api/timemachine/log",
    "/api/timer/list",
    "/api/toolgate/status",
    "/api/toolgate/audit",
    "/api/tool-analytics/stats",
    "/api/optimizer/status",
    "/api/optimizer/latency",
    "/api/dreams/latest",
    "/api/overnight/status",
    "/api/tuner/stats",
    "/api/wellness/status",
    "/api/wellness/dashboard",
    "/api/selfextend/proposed",
    "/api/awareness/situation",
    "/api/reality-anchor/status",
    "/api/initiative/log",
    "/api/continuity/status",
    "/api/macro/list",
    "/api/plugin-store/list",
    "/api/plugin-store/featured",
    "/api/plugin-store/categories",
    "/api/capabilities",
    "/api/voice/personality/status",
    "/api/voice/personality/config",
    "/api/voice-screen/status",
    "/api/voice-screen/config",
    "/api/voice-screen/history",
    "/api/whatif/stats",
]

FAST_POST = [
    ("/api/calc", {"expression": "2+2"}),
    ("/api/calc/percentage", {"value": 50, "total": 100}),
    ("/api/json/format", {"json_str": '{"a":1}'}),
    ("/api/json/minify", {"json_str": '{"a": 1}'}),
    ("/api/json/validate", {"json_str": '{"a":1}'}),
    ("/api/password/generate", {"length": 16}),
    ("/api/markdown/to-html", {"markdown": "# Hello"}),
    ("/api/markdown/strip", {"markdown": "# Hello **world**"}),
    ("/api/markdown/toc", {"markdown": "# H1\n## H2\n### H3"}),
    ("/api/similarity/compare", {"text1": "hello world", "text2": "hello there"}),
    ("/api/annotate", {"text": "This is a test sentence."}),
    ("/api/evaluator/evaluate", {"prompt": "test", "response": "test response"}),
    ("/api/reasoning/solve", {"problem": "What is 2+2?"}),
    ("/api/decision/analyze", {"question": "Test", "options": ["A", "B"]}),
    ("/api/code-debugger/explain", {"code": "x = 1"}),
    ("/api/code-debugger/analyze", {"code": "x = 1\ny = 2"}),
    ("/api/prompt-optimizer/analyze", {"prompt": "Tell me about AI"}),
    ("/api/prompt-optimizer/detect", {"prompt": "Tell me about AI"}),
    ("/api/bugfixer/scan", {"code": "x = 1"}),
    ("/api/cai/scan", {"code": "print('hello')"}),
    ("/api/creative/domains", {"domain": "test"}),
    ("/api/creative/reset", {}),
    ("/api/domain-mastery/reset", {}),
    ("/api/rag/clear", {}),
    ("/api/anomaly/stats", {}),
    ("/api/anomaly/baselines", {}),
    ("/api/dep-scanner/status", {}),
    ("/api/e2e/status", {}),
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


class TestEndpointHealth:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _build_app()
        self.client = self.app.test_client()

    def test_all_get_endpoints(self):
        passed, failed, errors = 0, 0, []
        for path in FAST_GET:
            t0 = time.monotonic()
            try:
                r = self.client.get(path)
                ms = (time.monotonic() - t0) * 1000
                if r.status_code in (200, 201):
                    passed += 1
                else:
                    failed += 1
                    errors.append(f"GET {path} -> {r.status_code} ({ms:.0f}ms)")
            except Exception as e:
                ms = (time.monotonic() - t0) * 1000
                failed += 1
                errors.append(f"GET {path} -> ERR: {e} ({ms:.0f}ms)")

        total = passed + failed
        print(f"\n{'=' * 60}")
        print(f"GET:  {passed}/{total} OK  ({failed} failed)")
        print(f"{'=' * 60}")
        for e in errors:
            print(f"  {e}")
        assert failed == 0, f"{failed} GET failures"

    def test_all_post_endpoints(self):
        passed, failed, errors = 0, 0, []
        for path, payload in FAST_POST:
            t0 = time.monotonic()
            try:
                r = self.client.post(path, json=payload)
                ms = (time.monotonic() - t0) * 1000
                if r.status_code in (200, 201):
                    passed += 1
                else:
                    failed += 1
                    errors.append(f"POST {path} -> {r.status_code} ({ms:.0f}ms)")
            except Exception as e:
                ms = (time.monotonic() - t0) * 1000
                failed += 1
                errors.append(f"POST {path} -> ERR: {e} ({ms:.0f}ms)")

        total = passed + failed
        print(f"\n{'=' * 60}")
        print(f"POST: {passed}/{total} OK  ({failed} failed)")
        print(f"{'=' * 60}")
        for e in errors:
            print(f"  {e}")
        assert failed == 0, f"{failed} POST failures"


class TestConcurrentLoad:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _build_app()

    def test_concurrent_gets(self):
        paths = FAST_GET[:80]
        results = {"ok": 0, "fail": 0, "errors": [], "latencies": []}
        lock = threading.Lock()

        def hit(path):
            c = self.app.test_client()
            t0 = time.monotonic()
            try:
                r = c.get(path)
                ms = (time.monotonic() - t0) * 1000
                with lock:
                    if r.status_code in (200, 201):
                        results["ok"] += 1
                    else:
                        results["fail"] += 1
                        results["errors"].append(f"{path}->{r.status_code}")
                    results["latencies"].append(ms)
            except Exception as e:
                ms = (time.monotonic() - t0) * 1000
                with lock:
                    results["fail"] += 1
                    results["errors"].append(f"{path}->ERR:{e}")
                    results["latencies"].append(ms)

        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(hit, paths))
        wall = (time.monotonic() - t0) * 1000

        lats = sorted(results["latencies"])
        avg = sum(lats) / len(lats) if lats else 0
        p50 = lats[len(lats) // 2] if lats else 0
        p95 = lats[int(len(lats) * 0.95)] if lats else 0

        print(f"\n{'=' * 60}")
        print(f"CONCURRENT GET: {len(paths)} reqs, 20 workers")
        print(f"{'=' * 60}")
        print(
            f"Wall: {wall:.0f}ms | OK: {results['ok']}/{len(paths)} | Fail: {results['fail']}"
        )
        print(f"Avg: {avg:.0f}ms | P50: {p50:.0f}ms | P95: {p95:.0f}ms")
        if results["errors"]:
            for e in results["errors"][:5]:
                print(f"  {e}")
        assert results["fail"] == 0, f"{results['fail']} concurrent failures"

    def test_concurrent_posts(self):
        posts = FAST_POST[:40]
        results = {"ok": 0, "fail": 0, "errors": [], "latencies": []}
        lock = threading.Lock()

        def hit(item):
            path, payload = item
            c = self.app.test_client()
            t0 = time.monotonic()
            try:
                r = c.post(path, json=payload)
                ms = (time.monotonic() - t0) * 1000
                with lock:
                    if r.status_code in (200, 201):
                        results["ok"] += 1
                    else:
                        results["fail"] += 1
                        results["errors"].append(f"{path}->{r.status_code}")
                    results["latencies"].append(ms)
            except Exception as e:
                ms = (time.monotonic() - t0) * 1000
                with lock:
                    results["fail"] += 1
                    results["errors"].append(f"{path}->ERR:{e}")
                    results["latencies"].append(ms)

        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
            list(pool.map(hit, posts))
        wall = (time.monotonic() - t0) * 1000

        lats = sorted(results["latencies"])
        avg = sum(lats) / len(lats) if lats else 0
        p50 = lats[len(lats) // 2] if lats else 0
        p95 = lats[int(len(lats) * 0.95)] if lats else 0

        print(f"\n{'=' * 60}")
        print(f"CONCURRENT POST: {len(posts)} reqs, 15 workers")
        print(f"{'=' * 60}")
        print(
            f"Wall: {wall:.0f}ms | OK: {results['ok']}/{len(posts)} | Fail: {results['fail']}"
        )
        print(f"Avg: {avg:.0f}ms | P50: {p50:.0f}ms | P95: {p95:.0f}ms")
        if results["errors"]:
            for e in results["errors"][:5]:
                print(f"  {e}")
        assert results["fail"] == 0, f"{results['fail']} concurrent POST failures"


class TestEdgeCases:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _build_app()
        self.client = self.app.test_client()

    def test_404(self):
        assert self.client.get("/api/nonexistent-xyz").status_code in (404, 405)

    def test_405(self):
        assert self.client.delete("/api/health").status_code in (404, 405)

    def test_null_json(self):
        r = self.client.post("/api/calc", data="null", content_type="application/json")
        assert r.status_code != 500

    def test_empty_json(self):
        r = self.client.post("/api/calc", data="{}", content_type="application/json")
        assert r.status_code != 500

    def test_malformed_json(self):
        r = self.client.post("/api/calc", data="{bad", content_type="application/json")
        assert r.status_code != 500

    def test_large_payload(self):
        r = self.client.post("/api/calc", json={"data": "x" * 100000})
        assert r.status_code != 500

    def test_path_traversal(self):
        r = self.client.get("/api/code/result/../../etc/passwd")
        assert r.status_code in (400, 403, 404, 405)

    def test_sql_injection(self):
        r = self.client.get("/api/ideas/search?q='; DROP TABLE ideas;--")
        assert r.status_code in (200, 400)

    def test_xss_payload(self):
        r = self.client.post(
            "/api/calc", json={"expression": "<script>alert(1)</script>"}
        )
        assert r.status_code != 500


class TestResponseFormat:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _build_app()
        self.client = self.app.test_client()

    @pytest.mark.parametrize(
        "path",
        [
            "/api/health",
            "/api/providers/status",
            "/api/agents",
            "/api/selftest/latest",
            "/api/goals",
            "/api/habits",
            "/api/mood/today",
            "/api/notifications",
            "/api/memory/stats",
            "/api/security-guard/status",
            "/api/agi/status",
            "/api/a2a/stats",
            "/api/wellness/status",
            "/api/reasoning/stats",
            "/api/decision/stats",
        ],
    )
    def test_valid_json(self, path):
        r = self.client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert r.get_json() is not None, f"{path} not JSON"
