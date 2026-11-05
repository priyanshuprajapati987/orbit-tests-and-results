import os

import pytest

# Hermetic test environment: the test suite must not depend on the developer's
# .env (real API keys). orbit/orbit/__init__.py loads the repo .env during
# import (pytest collection), so real provider keys would otherwise leak into
# the test environment and make provider-resolution tests depend on the
# developer's machine. Tests that specifically exercise auth (e.g.
# test_api_auth_security.py) set config attributes at runtime via monkeypatch.
# NOTE: these MUST stay at module level (not inside a fixture) so they run
# during conftest import — BEFORE any test module imports orbit, which caches
# config values from os.environ at import time.
os.environ.setdefault("ORBIT_API_KEY", "")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
SENSITIVE_ENV_KEYS = [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
    "CEREBRAS_API_KEY",
    "CLOUDFLARE_API_KEY",
    "OPPONENT_API_KEY",
    "OPPONENT_BASE_URL",
    "OPPONENT_MODEL",
    "OPPONENT_OPENAI_KEY",
    "OPPONENT_OPENAI_MODEL",
    "ORBIT_API_KEY",
    "ORBIT_SKIP_STARTUP",
]


@pytest.fixture(autouse=True, scope="session")
def _hermetic_environment():
    """Strip real API keys loaded from .env after collection.

    Runs after pytest collects (imports) all test modules, so any .env values
    loaded at import time are removed before the first test executes. This
    makes provider-resolution tests deterministic regardless of the developer's
    .env. Also normalizes ORBIT_SKIP_STARTUP so collection-time env mutations
    (e.g. module-level `os.environ[...]` in some test files) can never poison
    later tests like test_boot_wiring.py.
    """
    for key in SENSITIVE_ENV_KEYS:
        os.environ.pop(key, None)
    os.environ["ORBIT_API_KEY"] = ""
    os.environ["ORBIT_API_AUTH_ENABLED"] = "0"
    yield
    # process exits - nothing to restore


@pytest.fixture(autouse=True)
def _restore_environment():
    """Restore os.environ after each test so per-test env mutations never leak."""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


collect_ignore = [
    "test_all_core.py",
    "test_all_11_fixes.py",
    "test_file_create.py",
    "test_file_simple.py",
    "test_file_debug.py",
    "test_file_nl.py",
]
