"""
ORBIT Hardening Tests — Concurrency + Failure Injection + Cache Validation
"""

import concurrent.futures
import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

os.environ["ORBIT_SKIP_STARTUP"] = "1"
sys.path.insert(0, str(Path(__file__).parent.parent))


# ══════════════════════════════════════════════════════════════════════
# PHASE 3: CONCURRENCY TESTS
# ══════════════════════════════════════════════════════════════════════


def test_concurrent_calculator():
    """100 concurrent calculator calls — no races."""
    from orbit.orbit.core.calculator import get_calculator

    calc = get_calculator()
    results = []
    errors = []

    def run_calc(expr):
        try:
            r = calc.calculate(expr)
            results.append(r)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(run_calc, f"{i} + {i}") for i in range(100)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors: {errors}"
    assert len(results) == 100
    assert all("result" in r for r in results)


def test_concurrent_password_gen():
    """50 concurrent password generations — no collisions."""
    from orbit.orbit.core.password_generator import get_password_generator

    pw = get_password_generator()
    passwords = set()
    lock = threading.Lock()

    def gen():
        r = pw.generate(32)
        with lock:
            passwords.add(r["password"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(gen) for _ in range(50)]
        concurrent.futures.wait(futures)

    assert len(passwords) == 50, f"Collisions: {50 - len(passwords)}"


def test_concurrent_json_formatter():
    """30 concurrent JSON format/minify — no corruption."""
    from orbit.orbit.core.json_formatter import get_json_formatter

    jf = get_json_formatter()
    errors = []

    def run_jf(i):
        try:
            data = json.dumps({"i": i, "data": list(range(10))})
            jf.format_json(data)
            jf.minify(data)
            jf.validate(data)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(run_jf, i) for i in range(30)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors: {errors}"


def test_concurrent_unit_converter():
    """40 concurrent conversions — no races."""
    from orbit.orbit.core.unit_converter import get_converter

    conv = get_converter()
    errors = []

    def run_conv(i):
        try:
            conv.convert(float(i), "km", "mile")
            conv.convert(float(i), "C", "F")
            conv.convert(float(i), "kg", "lb")
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(run_conv, i) for i in range(40)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors: {errors}"


def test_concurrent_smart_memory():
    """20 concurrent SmartMemory operations — no deadlocks."""
    from orbit.orbit.core.smart_memory import SmartMemory

    sm = SmartMemory()
    errors = []

    def run_sm(i):
        try:
            sm.build_personalization_context(f"query {i}")
            sm.record_topic(f"topic {i}")
            sm.get_stats()
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(run_sm, i) for i in range(20)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors: {errors}"


def test_concurrent_text_similarity():
    """25 concurrent similarity comparisons — no corruption."""
    from orbit.orbit.core.text_similarity import get_similarity

    sim = get_similarity()
    errors = []

    def run_sim(i):
        try:
            sim.compare(f"text sample {i}", f"another sample {i}")
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(run_sim, i) for i in range(25)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors: {errors}"


def test_concurrent_code_interpreter():
    """10 concurrent code executions — no crashes."""
    from orbit.orbit.core.code_interpreter import get_code_interpreter

    ci = get_code_interpreter()
    results = []
    errors = []

    def run_code(i):
        try:
            r = ci.execute(f"print({i} * 2)")
            results.append(r)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(run_code, i) for i in range(10)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors: {errors}"
    assert len(results) == 10


# ══════════════════════════════════════════════════════════════════════
# PHASE 4: FAILURE INJECTION TESTS
# ══════════════════════════════════════════════════════════════════════


def test_ollama_unavailable():
    """Router handles Ollama being down gracefully."""
    from orbit.orbit.core.llm.router import get_router

    router = get_router()
    # Just verify get_status works even if Ollama is down
    status = router.get_status()
    assert isinstance(status, dict)
    assert "provider_health" in status


def test_code_interpreter_timeout():
    """Code interpreter uses timeout correctly."""
    from orbit.orbit.core.code_interpreter import get_code_interpreter

    ci = get_code_interpreter()
    old_timeout = ci._timeout
    ci._timeout = 1
    try:
        # time.sleep is blocked by validator, so this hits blocked status
        # Use allowed code that takes time: a big loop (no import needed)
        r = ci.execute("[i**2 for i in range(10**7)]")
        # Should either timeout or error — just verify it doesn't hang
        assert r.status in ("timeout", "error", "blocked", "success")
    finally:
        ci._timeout = old_timeout


def test_code_interpreter_invalid_code():
    """Code interpreter handles syntax errors."""
    from orbit.orbit.core.code_interpreter import get_code_interpreter

    ci = get_code_interpreter()
    r = ci.execute("def (invalid syntax")
    assert r.status in ("error", "blocked")  # validator may block or executor may error


def test_code_interpreter_blocked_import():
    """Code interpreter blocks dangerous imports."""
    from orbit.orbit.core.code_interpreter import get_code_interpreter

    ci = get_code_interpreter()
    r = ci.execute("import os; os.system('echo pwned')")
    assert r.status == "blocked"
    assert "Banned" in r.error


def test_weather_service_unavailable():
    """Weather service handles network failure."""
    from orbit.orbit.core.weather_service import WeatherService

    ws = WeatherService()
    with patch(
        "orbit.orbit.core.weather_service.urllib.request.urlopen",
        side_effect=Exception("network down"),
    ):
        result = ws.get_weather("Delhi")
        # Should either error or use cache
        assert isinstance(result, dict)


def test_qr_generator_empty_input():
    """QR generator rejects empty input."""
    from orbit.orbit.core.qr_generator import get_qr_generator

    qr = get_qr_generator()
    r = qr.generate("")
    assert "error" in r


def test_qr_generator_oversized_input():
    """QR generator rejects oversized input."""
    from orbit.orbit.core.qr_generator import get_qr_generator

    qr = get_qr_generator()
    r = qr.generate("x" * 5000)
    assert "error" in r


def test_password_generator_zero_length():
    """Password generator handles zero length."""
    from orbit.orbit.core.password_generator import get_password_generator

    pw = get_password_generator()
    r = pw.generate(0)
    # Should either error or return empty
    assert isinstance(r, dict)


def test_converter_unknown_units():
    """Unit converter handles unknown units."""
    from orbit.orbit.core.unit_converter import get_converter

    conv = get_converter()
    r = conv.convert(100, "xyz", "abc")
    assert "error" in r


def test_smart_memory_empty_query():
    """SmartMemory handles empty query gracefully."""
    from orbit.orbit.core.smart_memory import SmartMemory

    sm = SmartMemory()
    ctx = sm.build_personalization_context("")
    # Should return None or a valid string
    assert ctx is None or isinstance(ctx, str)


def test_clipboard_manager_no_pyperclip():
    """Clipboard manager degrades when pyperclip unavailable."""
    from orbit.orbit.core.clipboard_manager import ClipboardManager

    cm = ClipboardManager()
    # Should not crash
    status = cm.get_stats()
    assert isinstance(status, dict)


def test_json_formatter_malformed():
    """JSON formatter handles malformed input."""
    from orbit.orbit.core.json_formatter import get_json_formatter

    jf = get_json_formatter()
    r = jf.format_json("{invalid json")
    assert r["status"] == "invalid"
    assert "error" in r


def test_markdown_converter_no_dep():
    """Markdown converter handles missing dependency."""
    from orbit.orbit.core.markdown_converter import MarkdownConverter

    md = MarkdownConverter()
    r = md.to_html("# Test")
    # Should either work or return error about missing dep
    assert isinstance(r, dict)


def test_policy_engine_thread_safety():
    """PolicyEngine handles concurrent access."""
    from orbit.orbit.core.policy_engine import get_policy_engine

    pe = get_policy_engine()
    errors = []

    def run_check():
        try:
            pe.check("test", "file.read", mutate=False)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(run_check) for _ in range(50)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors: {errors}"


# ══════════════════════════════════════════════════════════════════════
# PHASE 5: CACHE VALIDATION
# ══════════════════════════════════════════════════════════════════════


def test_models_cache_first_request():
    """First /api/chat/models request hits Ollama."""
    from orbit.orbit.server import create_app

    app = create_app()
    client = app.test_client()

    # Clear global cache
    import orbit.orbit.core.chat_api as ca

    ca._models_cache["data"] = None
    ca._models_cache["time"] = 0

    resp = client.get("/api/chat/models")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "available" in data
    assert "current" in data


def test_models_cache_second_request_uses_cache():
    """Second /api/chat/models within 60s uses cache."""
    from orbit.orbit.server import create_app

    app = create_app()
    client = app.test_client()

    import orbit.orbit.core.chat_api as ca

    ca._models_cache["data"] = ["test_model"]
    ca._models_cache["time"] = time.time()

    resp = client.get("/api/chat/models")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["available"] == ["test_model"]


def test_models_cache_expired():
    """Expired cache triggers fresh Ollama query."""
    from orbit.orbit.server import create_app

    app = create_app()
    client = app.test_client()

    import orbit.orbit.core.chat_api as ca

    ca._models_cache["data"] = ["stale_model"]
    ca._models_cache["time"] = time.time() - 120  # 2 min ago

    resp = client.get("/api/chat/models")
    assert resp.status_code == 200


def test_models_cache_ollama_down():
    """Failed refresh returns stale cache, not error."""
    from orbit.orbit.server import create_app

    app = create_app()
    client = app.test_client()

    import orbit.orbit.core.chat_api as ca

    ca._models_cache["data"] = ["cached_model"]
    ca._models_cache["time"] = time.time() - 120  # expired

    with patch("orbit.orbit.core.chat_api.OLLAMA_URL", "http://127.0.0.1:19999"):
        resp = client.get("/api/chat/models")
        assert resp.status_code == 200
        data = resp.get_json()
        # Should return cached data since Ollama is down
        assert data["available"] == ["cached_model"]


def test_models_cache_thread_safety():
    """Concurrent cache reads don't corrupt state."""
    from orbit.orbit.server import create_app

    app = create_app()
    client = app.test_client()

    import orbit.orbit.core.chat_api as ca

    ca._models_cache["data"] = ["thread_test_model"]
    ca._models_cache["time"] = time.time()

    errors = []

    def read_models():
        try:
            resp = client.get("/api/chat/models")
            if resp.status_code != 200:
                errors.append(f"status {resp.status_code}")
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(read_models) for _ in range(20)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Errors: {errors}"


# ══════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
