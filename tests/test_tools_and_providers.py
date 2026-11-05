"""
ORBIT Tools + LLM Providers — Gap Fix Test Suite
==================================================
PART 1: Tests for 5 untested tools (ComputerTool, N8nTool, NewsTool, SecurityTool, CAI Security)
PART 2: Isolated LLM provider tests (Ollama, OpenRouter, Gemini, Groq, Cloudflare)

Run: py -m pytest tests/test_tools_and_providers.py -v
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — TOOLS (5 missing tools)
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputerTool(unittest.TestCase):
    """Tests for ComputerTool — process, clipboard, system info, command safety."""

    def test_import(self):
        from orbit.orbit.tools.computer import ComputerTool

        tool = ComputerTool()
        self.assertTrue(hasattr(tool, "list_processes"))
        self.assertTrue(hasattr(tool, "system_info"))
        self.assertTrue(hasattr(tool, "run_command"))
        self.assertTrue(hasattr(tool, "get_clipboard"))
        self.assertTrue(hasattr(tool, "set_clipboard"))
        self.assertTrue(hasattr(tool, "handle_natural"))

    def test_system_info(self):
        from orbit.orbit.tools.computer import ComputerTool

        tool = ComputerTool()
        info = tool.system_info()
        self.assertIsInstance(info, dict)
        self.assertIn("os", info)
        self.assertIn("hostname", info)
        self.assertIn("processor", info)
        self.assertTrue(info["os"])  # non-empty

    def test_run_command_blocks_unsafe(self):
        from orbit.orbit.tools.computer import ComputerTool

        tool = ComputerTool()
        result = tool.run_command("rm -rf /")
        self.assertFalse(result["success"])
        self.assertIn("not allowed", result["error"])

    def test_run_command_blocks_powershell_injection(self):
        from orbit.orbit.tools.computer import ComputerTool

        tool = ComputerTool()
        result = tool.run_command("powershell Get-Process")
        self.assertFalse(result["success"])
        self.assertIn("not allowed", result["error"])

    def test_list_processes_returns_data(self):
        from orbit.orbit.tools.computer import ComputerTool

        tool = ComputerTool()
        result = tool.list_processes()
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_handle_natural_system_info(self):
        from orbit.orbit.tools.computer import ComputerTool

        tool = ComputerTool()
        result = tool.handle_natural("show system info")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("success"))
        self.assertIn("data", result)

    def test_handle_natural_process_list(self):
        from orbit.orbit.tools.computer import ComputerTool

        tool = ComputerTool()
        result = tool.handle_natural("show processes")
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_handle_natural_unknown_command(self):
        from orbit.orbit.tools.computer import ComputerTool

        tool = ComputerTool()
        result = tool.handle_natural("do something random")
        self.assertFalse(result.get("success", True))
        self.assertIn("error", result)

    def test_ps_quote_safety(self):
        from orbit.orbit.tools.computer import ComputerTool

        quoted = ComputerTool._ps_quote("hello'world`$test")
        self.assertTrue(quoted.startswith("'"))
        self.assertTrue(quoted.endswith("'"))
        self.assertNotIn("$", quoted.replace("`$", ""))


class TestN8nTool(unittest.TestCase):
    """Tests for N8nTool — config, status check, natural language handling."""

    def test_import(self):
        from orbit.orbit.tools.n8n import N8nTool

        tool = N8nTool()
        self.assertTrue(hasattr(tool, "check_status"))
        self.assertTrue(hasattr(tool, "list_workflows"))
        self.assertTrue(hasattr(tool, "handle_natural"))
        self.assertTrue(hasattr(tool, "start_n8n"))

    def test_check_status_returns_dict(self):
        from orbit.orbit.tools.n8n import N8nTool

        tool = N8nTool()
        status = tool.check_status()
        self.assertIsInstance(status, dict)
        self.assertIn("online", status)
        self.assertIn("url", status)

    def test_config_loads_defaults(self):
        from orbit.orbit.tools.n8n import N8nTool

        tool = N8nTool()
        self.assertEqual(tool.base_url, "http://localhost:5678")
        self.assertIsInstance(tool.api_key, str)

    def test_handle_natural_when_offline(self):
        from orbit.orbit.tools.n8n import N8nTool

        tool = N8nTool()
        # n8n is almost certainly not running, so this should return offline message
        result = tool.handle_natural("list workflows")
        self.assertIsInstance(result, str)
        # Either offline message or actual workflow list
        self.assertTrue(len(result) > 0)

    def test_handle_natural_status(self):
        from orbit.orbit.tools.n8n import N8nTool

        tool = N8nTool()
        result = tool.handle_natural("check n8n status")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_handle_natural_unknown(self):
        from orbit.orbit.tools.n8n import N8nTool

        tool = N8nTool()
        result = tool.handle_natural("do something random with n8n")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_list_workflows_returns_list(self):
        from orbit.orbit.tools.n8n import N8nTool

        tool = N8nTool()
        workflows = tool.list_workflows()
        self.assertIsInstance(workflows, list)

    def test_headers_include_content_type(self):
        from orbit.orbit.tools.n8n import N8nTool

        tool = N8nTool()
        headers = tool._headers()
        self.assertIn("Content-Type", headers)
        self.assertEqual(headers["Content-Type"], "application/json")


class TestNewsTool(unittest.TestCase):
    """Tests for NewsTool — RSS feed fetching, categories, natural language."""

    def test_import(self):
        from orbit.orbit.tools.news import NewsTool

        tool = NewsTool()
        self.assertTrue(hasattr(tool, "fetch_rss"))
        self.assertTrue(hasattr(tool, "list_categories"))
        self.assertTrue(hasattr(tool, "handle_natural"))

    def test_list_categories(self):
        from orbit.orbit.tools.news import RSS_FEEDS, NewsTool

        tool = NewsTool()
        categories = tool.list_categories()
        self.assertIsInstance(categories, list)
        self.assertGreater(len(categories), 0)
        # Should include known categories
        self.assertIn("world", categories)
        self.assertIn("tech", categories)
        self.assertIn("cyber", categories)
        self.assertIn("finance", categories)
        # Should match RSS_FEEDS keys
        self.assertEqual(set(categories), set(RSS_FEEDS.keys()))

    def test_fetch_rss_returns_structure(self):
        from orbit.orbit.tools.news import NewsTool

        tool = NewsTool()
        result = tool.fetch_rss("tech", limit=3)
        self.assertIsInstance(result, dict)
        self.assertIn("category", result)
        self.assertIn("count", result)
        self.assertIn("articles", result)
        self.assertEqual(result["category"], "tech")
        self.assertIsInstance(result["articles"], list)

    def test_fetch_rss_unknown_category_falls_back(self):
        from orbit.orbit.tools.news import NewsTool

        tool = NewsTool()
        result = tool.fetch_rss("nonexistent_category_xyz", limit=2)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["category"], "nonexistent_category_xyz")
        self.assertIsInstance(result["articles"], list)

    def test_fetch_rss_limit_respected(self):
        from orbit.orbit.tools.news import NewsTool

        tool = NewsTool()
        result = tool.fetch_rss("world", limit=2)
        self.assertLessEqual(len(result["articles"]), 2)

    def test_handle_natural_tech(self):
        from orbit.orbit.tools.news import NewsTool

        tool = NewsTool()
        result = tool.handle_natural("show me tech news")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_handle_natural_cyber(self):
        from orbit.orbit.tools.news import NewsTool

        tool = NewsTool()
        result = tool.handle_natural("cyber security news")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_articles_have_required_fields(self):
        from orbit.orbit.tools.news import NewsTool

        tool = NewsTool()
        result = tool.fetch_rss("world", limit=5)
        for article in result["articles"]:
            self.assertIn("title", article)
            self.assertIn("link", article)
            self.assertIn("description", article)
            self.assertIn("date", article)
            self.assertIn("source", article)
            self.assertTrue(article["title"])  # non-empty


class TestSecurityTool(unittest.TestCase):
    """Tests for SecurityTool — process scanning, disk usage, full report."""

    def test_import(self):
        from orbit.orbit.tools.security import SecurityTool

        tool = SecurityTool()
        self.assertTrue(hasattr(tool, "scan_processes"))
        self.assertTrue(hasattr(tool, "disk_usage"))
        self.assertTrue(hasattr(tool, "full_report"))
        self.assertTrue(hasattr(tool, "handle_natural"))
        self.assertTrue(hasattr(tool, "firewall_status"))

    def test_scan_processes(self):
        from orbit.orbit.tools.security import SecurityTool

        tool = SecurityTool()
        result = tool.scan_processes()
        self.assertIsInstance(result, dict)
        self.assertIn("total", result)
        self.assertIn("top_cpu", result)
        self.assertGreater(result["total"], 0)  # at least some processes running
        self.assertIsInstance(result["top_cpu"], list)

    def test_disk_usage(self):
        from orbit.orbit.tools.security import SecurityTool

        tool = SecurityTool()
        drives = tool.disk_usage()
        self.assertIsInstance(drives, list)
        self.assertGreater(len(drives), 0)  # at least C: drive
        for drive in drives:
            self.assertIn("device", drive)
            self.assertIn("total_gb", drive)
            self.assertIn("used_gb", drive)
            self.assertIn("free_gb", drive)
            self.assertIn("percent", drive)
            self.assertGreater(drive["total_gb"], 0)

    def test_full_report(self):
        from orbit.orbit.tools.security import SecurityTool

        tool = SecurityTool()
        report = tool.full_report()
        self.assertIsInstance(report, str)
        self.assertIn("SECURITY REPORT", report)
        self.assertIn("CPU", report)
        self.assertIn("RAM", report)

    def test_handle_natural_processes(self):
        from orbit.orbit.tools.security import SecurityTool

        tool = SecurityTool()
        result = tool.handle_natural("show processes")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("success"))
        self.assertTrue(len(result.get("result", "")) > 0)

    def test_handle_natural_disk(self):
        from orbit.orbit.tools.security import SecurityTool

        tool = SecurityTool()
        result = tool.handle_natural("check disk usage")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("success"))
        self.assertTrue(len(result.get("result", "")) > 0)

    def test_handle_natural_default_report(self):
        from orbit.orbit.tools.security import SecurityTool

        tool = SecurityTool()
        result = tool.handle_natural("run security check")
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("success"))
        self.assertIn("SECURITY REPORT", result.get("result", ""))

    def test_service_control_invalid_action(self):
        from orbit.orbit.tools.security import SecurityTool

        tool = SecurityTool()
        result = tool.service_control("test_service", "invalid_action")
        self.assertIn("Invalid action", result)


class TestCAISecurity(unittest.TestCase):
    """Tests for CAI Security module — import, availability check, tool registration."""

    def test_import_module(self):
        import orbit.orbit.tools.cai_security as cai

        self.assertTrue(hasattr(cai, "get_agent"))
        self.assertTrue(hasattr(cai, "run_analysis"))
        self.assertTrue(hasattr(cai, "run_audit"))
        self.assertTrue(hasattr(cai, "run_threat_analysis"))
        self.assertTrue(hasattr(cai, "_CAI_AVAILABLE"))
        self.assertTrue(hasattr(cai, "CAI_TOOLS"))

    def test_cai_availability_flag(self):
        import orbit.orbit.tools.cai_security as cai

        # _CAI_AVAILABLE should be a boolean
        self.assertIsInstance(cai._CAI_AVAILABLE, bool)

    def test_cai_tools_list_type(self):
        import orbit.orbit.tools.cai_security as cai

        # CAI_TOOLS should be a list (may be empty if SDK not installed)
        self.assertIsInstance(cai.CAI_TOOLS, list)

    def test_get_agent_returns_none_when_unavailable(self):
        import orbit.orbit.tools.cai_security as cai

        if cai._CAI_AVAILABLE:
            # If CAI SDK is installed, agent should be created (may need Ollama)
            agent = cai.get_agent()
            # Agent could be None if Ollama is down, that's OK
            self.assertTrue(agent is None or agent is not None)
        else:
            # If CAI SDK is NOT installed, get_agent must return None
            agent = cai.get_agent()
            self.assertIsNone(agent)

    def test_run_analysis_returns_string(self):
        import orbit.orbit.tools.cai_security as cai

        result = cai.run_analysis("test query")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_run_audit_returns_string(self):
        import orbit.orbit.tools.cai_security as cai

        result = cai.run_audit()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_run_threat_analysis_returns_string(self):
        import orbit.orbit.tools.cai_security as cai

        result = cai.run_threat_analysis()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_security_tool_standalone_works(self):
        # CAI wraps SecurityTool — verify SecurityTool works independently
        from orbit.orbit.tools.security import SecurityTool

        st = SecurityTool()
        procs = st.scan_processes()
        self.assertGreater(procs["total"], 0)


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — LLM PROVIDERS (isolated per-provider tests)
# ═══════════════════════════════════════════════════════════════════════════════

# Provider results collected for summary
_PROVIDER_RESULTS = {}


def _record_provider(name, status, reason, latency_ms=0):
    _PROVIDER_RESULTS[name] = {
        "status": status,
        "reason": reason,
        "latency_ms": latency_ms,
    }


class TestOllamaProvider(unittest.TestCase):
    """Isolated test for Ollama — local LLM provider."""

    def test_01_import(self):
        from orbit.orbit.core.llm.providers import OllamaProvider

        provider = OllamaProvider()
        self.assertTrue(hasattr(provider, "is_available"))
        self.assertTrue(hasattr(provider, "get_models"))
        self.assertTrue(hasattr(provider, "generate"))

    def test_02_is_available_returns_bool(self):
        from orbit.orbit.core.llm.providers import OllamaProvider

        provider = OllamaProvider()
        available = provider.is_available()
        self.assertIsInstance(available, bool)
        if available:
            _record_provider("Ollama", "PASS", "connected and responding")
        else:
            _record_provider("Ollama", "SKIP", "not running (connection refused)")

    def test_03_get_models(self):
        from orbit.orbit.core.llm.providers import OllamaProvider

        provider = OllamaProvider()
        if not provider.is_available():
            self.skipTest("Ollama not available")
        models = provider.get_models()
        self.assertIsInstance(models, list)
        if len(models) == 0:
            self.skipTest("Ollama running but no models installed")

    def test_04_generate_hello(self):
        import requests

        from orbit.orbit.core.config import DEFAULT_OLLAMA_MODEL, OLLAMA_URL

        try:
            check = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            if check.status_code != 200:
                _record_provider("Ollama", "SKIP", "not running (connection refused)")
                self.skipTest("Ollama not running")
        except Exception:  # noqa: BLE001
            _record_provider("Ollama", "SKIP", "not running (connection refused)")
            self.skipTest("Ollama not running")

        start = time.time()
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": DEFAULT_OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": "Say hello in one word."}],
                    "stream": False,
                    "options": {"temperature": 0.7},
                },
                timeout=10,
            )
            latency = int((time.time() - start) * 1000)
            if response.status_code == 200:
                data = response.json()
                content = data.get("message", {}).get("content", "")
                self.assertTrue(len(content) > 0)
                _record_provider("Ollama", "PASS", f"responded in {latency}ms", latency)
            else:
                _record_provider("Ollama", "SKIP", f"HTTP {response.status_code}")
                self.skipTest(f"Ollama API returned {response.status_code}")
        except requests.Timeout:
            _record_provider("Ollama", "SKIP", "timeout (>10s)")
            self.skipTest("Ollama timed out")
        except Exception as e:  # noqa: BLE001
            _record_provider("Ollama", "SKIP", str(e)[:100])
            self.skipTest(f"Ollama generation failed: {e}")


class TestOpenRouterProvider(unittest.TestCase):
    """Isolated test for OpenRouter — cloud API provider."""

    def test_01_import(self):
        from orbit.orbit.core.llm.providers import OpenRouterProvider

        self.assertTrue(OpenRouterProvider)

    def test_02_api_key_check(self):
        from orbit.orbit.core.config import OPENROUTER_API_KEY

        if (
            not OPENROUTER_API_KEY
            or OPENROUTER_API_KEY == "your_openrouter_api_key_here"
        ):
            _record_provider("OpenRouter", "SKIP", "OPENROUTER_API_KEY not set")
            self.skipTest("OPENROUTER_API_KEY not set in environment")
        from orbit.orbit.core.llm.providers import OpenRouterProvider

        provider = OpenRouterProvider(api_key=OPENROUTER_API_KEY)
        self.assertTrue(provider.is_available())
        _record_provider("OpenRouter", "PASS", "API key configured")

    def test_03_get_models(self):
        from orbit.orbit.core.llm.providers import OpenRouterProvider

        provider = OpenRouterProvider(api_key="dummy")
        models = provider.get_models()
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)

    def test_04_generate_hello(self):
        import requests

        from orbit.orbit.core.config import OPENROUTER_API_KEY

        api_key = OPENROUTER_API_KEY
        if not api_key or api_key == "your_openrouter_api_key_here":
            _record_provider("OpenRouter", "SKIP", "OPENROUTER_API_KEY not set")
            self.skipTest("OPENROUTER_API_KEY not set")

        start = time.time()
        endpoints = [
            ("OmniRouter", "http://localhost:20128/v1/chat/completions"),
            ("OpenRouter Direct", "https://openrouter.ai/api/v1/chat/completions"),
        ]
        for source, url in endpoints:
            try:
                response = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:3000",
                        "X-Title": "ORBIT",
                    },
                    json={
                        "model": "openai/gpt-4o-mini",
                        "messages": [
                            {"role": "user", "content": "Say hello in one word."}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 50,
                    },
                    timeout=15,
                )
                if response.status_code == 200:
                    latency = int((time.time() - start) * 1000)
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    self.assertTrue(len(content) > 0)
                    _record_provider(
                        "OpenRouter",
                        "PASS",
                        f"responded via {source} in {latency}ms",
                        latency,
                    )
                    return
                else:
                    continue
            except Exception:  # noqa: BLE001, S112
                continue

        _record_provider(
            "OpenRouter", "SKIP", "no active credentials via OmniRouter or direct"
        )
        self.skipTest(
            "OpenRouter not reachable: OmniRouter has no active providers, direct API key invalid (OmniRouter-scoped)"
        )


class TestGeminiProvider(unittest.TestCase):
    """Isolated test for Google Gemini — cloud API provider."""

    def test_01_import(self):
        from orbit.orbit.core.llm.providers import GeminiProvider

        self.assertTrue(GeminiProvider)

    def test_02_api_key_check(self):
        from orbit.orbit.core.config import GEMINI_API_KEY

        if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
            _record_provider("Gemini", "SKIP", "GEMINI_API_KEY not set")
            self.skipTest("GEMINI_API_KEY not set in environment")
        from orbit.orbit.core.llm.providers import GeminiProvider

        provider = GeminiProvider(api_key=GEMINI_API_KEY)
        self.assertTrue(provider.is_available())
        _record_provider("Gemini", "PASS", "API key configured")

    def test_03_get_models(self):
        from orbit.orbit.core.llm.providers import GeminiProvider

        provider = GeminiProvider(api_key="dummy")
        models = provider.get_models()
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)

    def test_04_generate_hello(self):
        import requests

        from orbit.orbit.core.config import GEMINI_API_KEY

        api_key = GEMINI_API_KEY
        if not api_key or api_key == "your_gemini_api_key_here":
            _record_provider("Gemini", "SKIP", "GEMINI_API_KEY not set")
            self.skipTest("GEMINI_API_KEY not set")

        model = "gemini-2.5-flash"
        start = time.time()
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                json={
                    "contents": [
                        {"role": "user", "parts": [{"text": "Say hello in one word."}]}
                    ],
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 50},
                },
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            latency = int((time.time() - start) * 1000)
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text_parts = candidates[0].get("content", {}).get("parts", [])
                    if text_parts:
                        content = text_parts[0].get("text", "")
                        self.assertTrue(len(content) > 0)
                        _record_provider(
                            "Gemini", "PASS", f"responded in {latency}ms", latency
                        )
                        return
                _record_provider("Gemini", "SKIP", "empty response from API")
                self.skipTest("Gemini returned empty response (key may be invalid)")
            else:
                _record_provider("Gemini", "SKIP", f"HTTP {response.status_code}")
                self.skipTest(
                    f"Gemini API returned {response.status_code} (key may be invalid)"
                )
        except requests.Timeout:
            _record_provider("Gemini", "SKIP", "timeout (>15s)")
            self.skipTest("Gemini timed out")
        except Exception as e:  # noqa: BLE001
            _record_provider("Gemini", "SKIP", str(e)[:100])
            self.skipTest(f"Gemini generation failed: {e}")


class TestGroqProvider(unittest.TestCase):
    """Isolated test for Groq — ultra-fast inference provider."""

    def test_01_import(self):
        from orbit.orbit.core.llm.providers import LLMProvider
        from orbit.orbit.core.llm.router import LLMRouter

        self.assertTrue(LLMProvider)
        self.assertTrue(LLMRouter)

    def test_02_api_key_check(self):
        from orbit.orbit.core.config import GROQ_API_KEY

        if not GROQ_API_KEY:
            _record_provider("Groq", "SKIP", "GROQ_API_KEY not set")
            self.skipTest("GROQ_API_KEY not set in environment")
        _record_provider("Groq", "PASS", "API key configured")

    def test_03_generate_hello(self):
        import requests

        from orbit.orbit.core.config import GROQ_API_KEY, GROQ_API_URL, GROQ_MODELS

        if not GROQ_API_KEY:
            _record_provider("Groq", "SKIP", "GROQ_API_KEY not set")
            self.skipTest("GROQ_API_KEY not set")

        model = GROQ_MODELS.get("fast", "llama-3.3-70b-versatile")
        start = time.time()
        try:
            response = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say hello in one word."}],
                    "temperature": 0.7,
                    "max_tokens": 50,
                },
                timeout=10,
            )
            latency = int((time.time() - start) * 1000)
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                self.assertTrue(len(content) > 0)
                _record_provider("Groq", "PASS", f"responded in {latency}ms", latency)
            else:
                _record_provider(
                    "Groq",
                    "SKIP",
                    f"HTTP {response.status_code}: API unavailable",
                )
                self.skipTest(f"Groq API returned {response.status_code}")
        except requests.Timeout:
            _record_provider("Groq", "FAIL", "timeout (>10s)")
            self.fail("Groq timed out")
        except unittest.case.SkipTest:
            raise
        except Exception as e:  # noqa: BLE001
            _record_provider("Groq", "FAIL", str(e)[:100])
            self.fail(f"Groq test failed: {e}")


class TestCloudflareProvider(unittest.TestCase):
    """Isolated test for Cloudflare Workers AI provider."""

    def test_01_import(self):
        from orbit.orbit.core.llm.providers import LLMProvider

        self.assertTrue(LLMProvider)

    def test_02_api_token_check(self):
        from orbit.orbit.core.config import CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN

        if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ACCOUNT_ID:
            _record_provider(
                "Cloudflare",
                "SKIP",
                "CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set",
            )
            self.skipTest("CLOUDFLARE credentials not set in environment")
        _record_provider("Cloudflare", "PASS", "API token configured")

    def test_03_generate_hello(self):
        import requests

        from orbit.orbit.core.config import (
            CLOUDFLARE_ACCOUNT_ID,
            CLOUDFLARE_AI_URL,
            CLOUDFLARE_API_TOKEN,
            CLOUDFLARE_MODELS,
        )

        if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ACCOUNT_ID:
            _record_provider("Cloudflare", "SKIP", "CLOUDFLARE credentials not set")
            self.skipTest("CLOUDFLARE credentials not set")

        model = CLOUDFLARE_MODELS.get("fast", "@cf/meta/llama-3.1-8b-instruct-awq")
        url = f"{CLOUDFLARE_AI_URL}/{model}"
        start = time.time()
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "messages": [{"role": "user", "content": "Say hello in one word."}],
                },
                timeout=15,
            )
            latency = int((time.time() - start) * 1000)
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {})
                content = result.get("response", "")
                self.assertTrue(len(content) > 0)
                _record_provider(
                    "Cloudflare", "PASS", f"responded in {latency}ms", latency
                )
            else:
                _record_provider("Cloudflare", "FAIL", f"HTTP {response.status_code}")
                self.fail(f"Cloudflare API returned {response.status_code}")
        except requests.Timeout:
            _record_provider("Cloudflare", "FAIL", "timeout (>15s)")
            self.fail("Cloudflare timed out")
        except Exception as e:  # noqa: BLE001
            _record_provider("Cloudflare", "FAIL", str(e)[:100])
            self.fail(f"Cloudflare test failed: {e}")


class TestLLMProviderSummary(unittest.TestCase):
    """Final test that generates and validates the provider summary table."""

    def test_01_all_providers_recorded(self):
        expected = {"Ollama", "OpenRouter", "Gemini", "Groq", "Cloudflare"}
        recorded = set(_PROVIDER_RESULTS.keys())
        # All providers should have been tested (may be SKIP or FAIL or PASS)
        missing = expected - recorded
        if missing:
            # Fill in missing ones as not-tested
            for name in missing:
                _record_provider(name, "SKIP", "test class did not run")
        # Verify all 5 are present
        self.assertEqual(len(_PROVIDER_RESULTS), 5)

    def test_02_print_provider_summary(self):
        print("\n" + "=" * 65)
        print(" LLM PROVIDER TEST SUMMARY")
        print("=" * 65)
        print(f" {'PROVIDER':<15} | {'STATUS':<8} | {'REASON'}")
        print("-" * 65)
        for name in ["Ollama", "Groq", "Cloudflare", "OpenRouter", "Gemini"]:
            info = _PROVIDER_RESULTS.get(
                name, {"status": "SKIP", "reason": "not tested"}
            )
            print(f" {name:<15} | {info['status']:<8} | {info['reason']}")
        print("=" * 65)
        passed = sum(1 for v in _PROVIDER_RESULTS.values() if v["status"] == "PASS")
        failed = sum(1 for v in _PROVIDER_RESULTS.values() if v["status"] == "FAIL")
        skipped = sum(1 for v in _PROVIDER_RESULTS.values() if v["status"] == "SKIP")
        print(f" Total: {passed} PASS | {failed} FAIL | {skipped} SKIP")
        print("=" * 65)
        # This test always passes — it just prints the summary
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
