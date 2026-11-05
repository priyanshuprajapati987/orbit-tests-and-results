"""
ORBIT Sandbox Benchmark — Performance + Quality Testing
Tests: LLM latency, agent dispatch, tool execution, API response, memory ops
"""

import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Set sandbox mode
os.environ["ORBIT_SKIP_STARTUP"] = "1"
os.environ["ORBIT_SANDBOX"] = "1"

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))


class BenchmarkRunner:
    def __init__(self):
        self.results = {}
        self.start_time = datetime.now(timezone.utc)

    def time_it(self, name, func, iterations=1):
        """Time a function call over N iterations."""
        times = []
        error = None
        for _ in range(iterations):
            try:
                start = time.perf_counter()
                func()
                elapsed = (time.perf_counter() - start) * 1000  # ms
                times.append(elapsed)
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                error = str(e)
                break

        if error:
            self.results[name] = {"status": "ERROR", "error": error}
        elif times:
            self.results[name] = {
                "status": "OK",
                "min_ms": round(min(times), 2),
                "max_ms": round(max(times), 2),
                "avg_ms": round(statistics.mean(times), 2),
                "median_ms": round(statistics.median(times), 2),
                "p95_ms": round(
                    sorted(times)[int(len(times) * 0.95)]
                    if len(times) > 1
                    else times[0],
                    2,
                ),
                "iterations": len(times),
            }
        return self.results.get(name)

    def section(self, title):
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")

    def run_all(self):
        print(f"\n{'#' * 60}")
        print("  ORBIT SANDBOX BENCHMARK")
        print(f"  Started: {self.start_time.isoformat()}")
        print(f"{'#' * 60}")

        self.benchmark_imports()
        self.benchmark_config()
        self.benchmark_memory_ops()
        self.benchmark_tools()
        self.benchmark_agents()
        self.benchmark_llm_router()
        self.benchmark_api_endpoints()
        self.benchmark_security()
        self.benchmark_context_manager()

        self.print_report()
        self.save_report()

    # ── 1. Import Speed ──────────────────────────────────────────────
    def benchmark_imports(self):
        self.section("1. IMPORT SPEED (cold start)")

        modules = [
            ("import core.config", "from orbit.orbit.core import config"),
            (
                "import core.smart_memory",
                "from orbit.orbit.core.smart_memory import SmartMemory",
            ),
            (
                "import core.calculator",
                "from orbit.orbit.core.calculator import get_calculator",
            ),
            (
                "import core.password_generator",
                "from orbit.orbit.core.password_generator import get_password_generator",
            ),
            (
                "import core.qr_generator",
                "from orbit.orbit.core.qr_generator import get_qr_generator",
            ),
            (
                "import core.weather_service",
                "from orbit.orbit.core.weather_service import get_weather_service",
            ),
            (
                "import core.markdown_converter",
                "from orbit.orbit.core.markdown_converter import get_markdown_converter",
            ),
            (
                "import core.text_similarity",
                "from orbit.orbit.core.text_similarity import get_similarity",
            ),
            (
                "import core.clipboard_manager",
                "from orbit.orbit.core.clipboard_manager import get_clipboard_manager",
            ),
            (
                "import core.unit_converter",
                "from orbit.orbit.core.unit_converter import get_converter",
            ),
            (
                "import core.json_formatter",
                "from orbit.orbit.core.json_formatter import get_json_formatter",
            ),
            (
                "import core.color_picker",
                "from orbit.orbit.core.color_picker import get_color_picker",
            ),
            (
                "import core.pomodoro",
                "from orbit.orbit.core.pomodoro import get_pomodoro",
            ),
            (
                "import core.timer_manager",
                "from orbit.orbit.core.timer_manager import get_timer",
            ),
            (
                "import core.system_info",
                "from orbit.orbit.core.system_info import get_system_info",
            ),
            (
                "import core.code_interpreter",
                "from orbit.orbit.core.code_interpreter import get_code_interpreter",
            ),
            (
                "import core.policy_engine",
                "from orbit.orbit.core.policy_engine import get_policy_engine",
            ),
        ]

        for name, import_stmt in modules:
            self.time_it(name, lambda s=import_stmt: exec(s))  # noqa: S102

    # ── 2. Config Load ───────────────────────────────────────────────
    def benchmark_config(self):
        self.section("2. CONFIG LOAD SPEED")

        from orbit.orbit.core import config

        self.time_it("config.OLLAMA_URL", lambda: config.OLLAMA_URL)
        self.time_it("config.DEFAULT_OLLAMA_MODEL", lambda: config.DEFAULT_OLLAMA_MODEL)
        self.time_it("config.TTS_VOICE", lambda: config.TTS_VOICE)
        self.time_it("config.MEMORY_FILE", lambda: config.MEMORY_FILE)

    # ── 3. Memory Operations ─────────────────────────────────────────
    def benchmark_memory_ops(self):
        self.section("3. MEMORY OPERATIONS")

        from orbit.orbit.core.smart_memory import SmartMemory

        sm = SmartMemory()

        self.time_it(
            "smart_memory.build_context",
            lambda: sm.build_personalization_context("test query"),
        )
        self.time_it("smart_memory.get_stats", lambda: sm.get_stats())
        self.time_it(
            "smart_memory.record_topic", lambda: sm.record_topic("benchmark test query")
        )

        # Calculator (pure Python, no I/O)
        from orbit.orbit.core.calculator import get_calculator

        calc = get_calculator()
        self.time_it("calc.simple_math", lambda: calc.calculate("2 + 3 * 4"))
        self.time_it(
            "calc.complex_math", lambda: calc.calculate("((2 + 3) * (7 - 2)) / 5")
        )
        self.time_it("calc.percentage", lambda: calc.percentage(240, 15))

    # ── 4. Tool Execution ────────────────────────────────────────────
    def benchmark_tools(self):
        self.section("4. TOOL EXECUTION SPEED")

        # Password Generator
        from orbit.orbit.core.password_generator import get_password_generator

        pw = get_password_generator()
        self.time_it("password.generate_16char", lambda: pw.generate(16))
        self.time_it("password.generate_32char", lambda: pw.generate(32))
        self.time_it("password.passphrase", lambda: pw.generate_passphrase(4))

        # QR Generator
        from orbit.orbit.core.qr_generator import get_qr_generator

        qr = get_qr_generator()
        self.time_it("qr.generate_text", lambda: qr.generate("Hello ORBIT"))
        self.time_it("qr.generate_url", lambda: qr.generate("https://github.com"))

        # Unit Converter
        from orbit.orbit.core.unit_converter import get_converter

        conv = get_converter()
        self.time_it("converter.km_to_mile", lambda: conv.convert(100, "km", "mile"))
        self.time_it("converter.c_to_f", lambda: conv.convert(100, "C", "F"))
        self.time_it("converter.kg_to_lb", lambda: conv.convert(70, "kg", "lb"))

        # JSON Formatter
        from orbit.orbit.core.json_formatter import get_json_formatter

        jf = get_json_formatter()
        test_json = '{"name":"ORBIT","version":"3.7.0","features":[1,2,3,4,5]}'
        self.time_it("json.format", lambda: jf.format_json(test_json))
        self.time_it("json.minify", lambda: jf.minify(test_json))
        self.time_it("json.validate", lambda: jf.validate(test_json))

        # Text Similarity
        from orbit.orbit.core.text_similarity import get_similarity

        sim = get_similarity()
        self.time_it(
            "similarity.jaccard",
            lambda: sim.compare("hello world", "hello there world"),
        )
        self.time_it(
            "similarity.levenshtein", lambda: sim._levenshtein_ratio("hello", "helo")
        )

        # Markdown Converter
        from orbit.orbit.core.markdown_converter import get_markdown_converter

        md = get_markdown_converter()
        test_md = "# Hello\n\nThis is **bold** and `code`.\n\n- item 1\n- item 2"
        self.time_it("markdown.to_html", lambda: md.to_html(test_md))

        # Code Interpreter
        from orbit.orbit.core.code_interpreter import get_code_interpreter

        ci = get_code_interpreter()
        self.time_it("code_interpreter.simple", lambda: ci.execute("print(2 + 3)"))
        self.time_it("code_interpreter.string", lambda: ci.execute("print('hello')"))
        self.time_it(
            "code_interpreter.loop", lambda: ci.execute("for i in range(100): pass")
        )

    # ── 5. Agent Dispatch ────────────────────────────────────────────
    def benchmark_agents(self):
        self.section("5. AGENT DISPATCH SPEED")

        try:
            from orbit.orbit.agents.specialized import (
                CodeAgent,
                MeetingAgent,
                MemoryAgent,
                ResearchAgent,
                SecurityAgent,
                TaskAgent,
                WritingAgent,
            )

            agents = [
                ("TaskAgent", TaskAgent),
                ("CodeAgent", CodeAgent),
                ("ResearchAgent", ResearchAgent),
                ("WritingAgent", WritingAgent),
                ("SecurityAgent", SecurityAgent),
                ("MemoryAgent", MemoryAgent),
                ("MeetingAgent", MeetingAgent),
            ]

            for name, AgentClass in agents:
                self.time_it(f"agent.{name}.init", lambda a=AgentClass: a())
                agent = AgentClass()
                self.time_it(
                    f"agent.{name}.can_handle",
                    lambda a=agent: a.can_handle("test query"),
                )
                self.time_it(
                    f"agent.{name}.get_metrics", lambda a=agent: a.get_metrics()
                )

        except Exception as e:  # noqa: BLE001  # noqa: BLE001
            self.results["agents"] = {"status": "ERROR", "error": str(e)}

    # ── 6. LLM Router ───────────────────────────────────────────────
    def benchmark_llm_router(self):
        self.section("6. LLM ROUTER SPEED")

        try:
            from orbit.orbit.core.llm.router import get_router

            router = get_router()
            self.time_it("router.get_status", lambda: router.get_status())
            self.time_it("router.provider_stats", lambda: router.provider_stats)
        except Exception as e:  # noqa: BLE001
            self.results["llm_router"] = {"status": "ERROR", "error": str(e)}

    # ── 7. API Endpoints ─────────────────────────────────────────────
    def benchmark_api_endpoints(self):
        self.section("7. API ENDPOINT RESPONSE TIME")

        try:
            from orbit.orbit.server import create_app

            app = create_app()
            client = app.test_client()

            endpoints = [
                ("GET /api/health", "/api/health"),
                ("GET /api/chat/models", "/api/chat/models"),
                ("GET /api/chat/engine-status", "/api/chat/engine-status"),
                ("GET /api/providers/status", "/api/providers/status"),
                ("GET /api/system-info", "/api/system-info"),
                ("GET /api/wifi/status", "/api/wifi/status"),
                ("GET /api/pomodoro/status", "/api/pomodoro/status"),
                ("GET /api/timer/list", "/api/timer/list"),
                ("GET /api/clipboard/history", "/api/clipboard/history"),
                ("GET /api/converter/categories", "/api/converter/categories"),
            ]

            for name, path in endpoints:
                self.time_it(f"api.{name}", lambda p=path: client.get(p).status_code)

            # POST endpoints
            post_endpoints = [
                ("POST /api/calc", "/api/calc", {"expression": "2+3"}),
                (
                    "POST /api/password/generate",
                    "/api/password/generate",
                    {"length": 16},
                ),
                ("POST /api/json/validate", "/api/json/validate", {"json": '{"a":1}'}),
                (
                    "POST /api/converter/convert",
                    "/api/converter/convert",
                    {"value": 100, "from": "km", "to": "mile"},
                ),
                (
                    "POST /api/similarity/compare",
                    "/api/similarity/compare",
                    {"text1": "hello", "text2": "world"},
                ),
                (
                    "POST /api/markdown/to-html",
                    "/api/markdown/to-html",
                    {"markdown": "# Test"},
                ),
            ]

            for name, path, data in post_endpoints:
                self.time_it(
                    f"api.{name}",
                    lambda p=path, d=data: client.post(p, json=d).status_code,
                )

        except Exception as e:  # noqa: BLE001
            self.results["api_endpoints"] = {"status": "ERROR", "error": str(e)}

    # ── 8. Security ──────────────────────────────────────────────────
    def benchmark_security(self):
        self.section("8. SECURITY CHECKS")

        from orbit.orbit.core.policy_engine import get_policy_engine

        pe = get_policy_engine()

        self.time_it(
            "policy.check_read", lambda: pe.check("test", "file.read", mutate=False)
        )
        self.time_it(
            "policy.check_write", lambda: pe.check("test", "file.write", mutate=True)
        )
        self.time_it(
            "policy.check_system",
            lambda: pe.check("test", "system.command", mutate=True),
        )
        self.time_it("policy.stats", lambda: pe.stats())

        from orbit.orbit.core.code_interpreter import get_code_interpreter

        ci = get_code_interpreter()
        self.time_it("sandbox.block_import_os", lambda: ci.execute("import os"))
        self.time_it(
            "sandbox.block_subprocess", lambda: ci.execute("import subprocess")
        )
        self.time_it(
            "sandbox.block_eval", lambda: ci.execute("eval('__import__(\"os\")')")
        )

    # ── 9. Context Manager ───────────────────────────────────────────
    def benchmark_context_manager(self):
        self.section("9. CONTEXT MANAGER")

        try:
            from orbit.orbit.core.context_manager import ContextManager

            cm = ContextManager()
            self.time_it(
                "context.build_history", lambda: cm.build_history("test query")
            )
            self.time_it("context.get_stats", lambda: cm.get_stats())
        except Exception as e:  # noqa: BLE001
            self.results["context_manager"] = {"status": "ERROR", "error": str(e)}

    # ── Report ────────────────────────────────────────────────────────
    def print_report(self):
        print(f"\n{'#' * 60}")
        print("  BENCHMARK REPORT")
        print(f"{'#' * 60}")

        total = len(self.results)
        ok = sum(1 for r in self.results.values() if r.get("status") == "OK")
        errors = sum(1 for r in self.results.values() if r.get("status") == "ERROR")

        print(f"\n  Total Tests: {total}")
        print(f"  Passed: {ok}")
        print(f"  Errors: {errors}")

        # Top 10 slowest
        timed = [(k, v) for k, v in self.results.items() if v.get("status") == "OK"]
        if timed:
            print(f"\n  {'-' * 50}")
            print("  TOP 10 SLOWEST OPERATIONS:")
            print(f"  {'-' * 50}")
            sorted_results = sorted(timed, key=lambda x: x[1]["avg_ms"], reverse=True)
            for name, data in sorted_results[:10]:
                print(f"  {name:45s} {data['avg_ms']:8.2f} ms")

            # Top 10 fastest
            print("\n  TOP 10 FASTEST OPERATIONS:")
            print(f"  {'-' * 50}")
            sorted_results_fast = sorted(timed, key=lambda x: x[1]["avg_ms"])
            for name, data in sorted_results_fast[:10]:
                print(f"  {name:45s} {data['avg_ms']:8.2f} ms")

            # Summary stats
            all_avgs = [v["avg_ms"] for _, v in timed]
            print(f"\n  {'-' * 50}")
            print("  SUMMARY:")
            print(f"  {'-' * 50}")
            print(f"  Average latency: {statistics.mean(all_avgs):.2f} ms")
            print(f"  Median latency:  {statistics.median(all_avgs):.2f} ms")
            print(f"  Min latency:     {min(all_avgs):.2f} ms")
            print(f"  Max latency:     {max(all_avgs):.2f} ms")

        if errors:
            print("\n  ERRORS:")
            for name, data in self.results.items():
                if data.get("status") == "ERROR":
                    print(f"  X {name}: {data.get('error', 'unknown')}")

        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        print(f"\n  Total benchmark time: {elapsed:.2f}s")
        print(f"{'#' * 60}\n")

    def save_report(self):
        report_path = Path("orbit_data/benchmark_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "timestamp": self.start_time.isoformat(),
            "duration_seconds": (
                datetime.now(timezone.utc) - self.start_time
            ).total_seconds(),
            "total_tests": len(self.results),
            "passed": sum(1 for r in self.results.values() if r.get("status") == "OK"),
            "errors": sum(
                1 for r in self.results.values() if r.get("status") == "ERROR"
            ),
            "results": self.results,
        }

        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    runner = BenchmarkRunner()
    runner.run_all()
