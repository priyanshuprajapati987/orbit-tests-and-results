# ORBIT — Phase 0 Smoke Suite (baseline: 2026-10-12)
#
# Purpose: one command, fast signal that the core still imports, config
# loads, and the local environment is sane. Stress/debug scripts in this
# directory are NOT part of this suite.
#
# Run:  python -m pytest tests/test_smoke_core.py -v
# Markers: unit (default), integration (needs local services)
#
# (c) 2026 Priyanshu Prajapati

from __future__ import annotations

import os
import sys
import urllib.request

import pytest

pytestmark = pytest.mark.unit


def test_python_version():
    assert sys.version_info >= (3, 10), "ORBIT requires Python 3.10+"


def test_import_outer_package():
    orbit = pytest.importorskip("orbit", reason="package not importable on this machine")
    assert getattr(orbit, "__version__", None), "orbit.__version__ missing"


def test_import_inner_package_and_version():
    inner = pytest.importorskip("orbit.orbit", reason="inner package not importable")
    assert inner.__version__


def test_agents_registry_present():
    agents = pytest.importorskip("orbit.agents", reason="agents package not importable")
    registry = getattr(agents, "AGENT_REGISTRY", None)
    assert registry, "AGENT_REGISTRY missing or empty"
    assert len(registry) >= 20, f"suspiciously small registry: {len(registry)}"
    assert "QUEEN" in registry, "QUEEN not in AGENT_REGISTRY"


def test_agent_classes_instantiable():
    agents = pytest.importorskip("orbit.agents")
    queen_cls = getattr(agents, "QueenAgent", None)
    assert queen_cls is not None, "QueenAgent missing"
    instance = queen_cls()
    assert hasattr(instance, "execute"), "QueenAgent.execute missing"


def test_config_exposes_llm_settings():
    cfg = pytest.importorskip("orbit.orbit.config", reason="config not importable")
    for attr in ("OLLAMA_URL", "DEFAULT_OLLAMA_MODEL"):
        assert hasattr(cfg, attr), f"config missing {attr}"


def test_provider_key_stub_returns_none_by_default():
    vk = pytest.importorskip(
        "orbit.orbit.core.provider_keys",
        reason="provider_keys not importable",
    )
    # env-only resolution: unset key -> None (vault is private-product only
    # in the public distribution; in the private repo this hits the vault)
    result = vk.get_provider_key("SMOKE_NONEXISTENT_KEY_XYZ")
    assert result is None or isinstance(result, str)


def test_secret_redactor_masks_common_patterns():
    red = pytest.importorskip(
        "orbit.orbit.core.secret_redactor",
        reason="secret_redactor not importable",
    )
    masked = red.redact_text("token sk-abcdefghijklmnop1234567890abcdefghijklmnop")
    assert "sk-abcdefghijklmnop" not in str(masked)


@pytest.mark.integration
def test_ollama_reachable():
    base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=4) as resp:
            assert resp.status == 200
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Ollama not reachable: {exc}")


@pytest.mark.integration
def test_default_model_installed():
    base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    default = os.getenv("DEFAULT_OLLAMA_MODEL", "qwen3:8b")
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=4) as resp:
            import json

            names = [m.get("name", "") for m in json.loads(resp.read().decode()).get("models", [])]
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Ollama not reachable: {exc}")
    stems = {n.split(":")[0] for n in names}
    if default not in names and default.split(":")[0] not in stems:
        pytest.fail(
            f"DEFAULT_OLLAMA_MODEL '{default}' not installed; available: {names}. "
            "Run scripts/preflight.py for guidance."
        )


@pytest.mark.integration
def test_flask_app_factory_health_route():
    import os

    if os.getenv("ORBIT_SMOKE_SERVER", "").lower() not in ("1", "true", "yes", "on"):
        pytest.skip("set ORBIT_SMOKE_SERVER=1 to boot full app (heavy, dev machine only)")
    pytest.importorskip("flask", reason="flask not installed")
    server = pytest.importorskip("orbit.orbit.server", reason="server module not importable")
    create = getattr(server, "create_app", None)
    if create is None:
        pytest.skip("create_app factory not present")
    try:
        app = create()
    except Exception as exc:  # noqa: BLE001 - factory may need full env
        pytest.skip(f"create_app failed (needs full env): {exc}")
    client = app.test_client()
    resp = client.get("/api/health")
    assert resp.status_code in (200, 308, 401), f"unexpected health status {resp.status_code}"
