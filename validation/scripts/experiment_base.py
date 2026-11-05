"""
ORBIT Validation — Experiment Runner Base Framework

Provides shared utilities for all experiments.
"""

import json
import os
import sys
import time
import hashlib
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

# Load .env for API keys
_env_file = Path(__file__).parent.parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Add project to path (root for `orbit.orbit.*` imports + orbit/ for inner layout)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "orbit"))
sys.path.insert(0, str(_PROJECT_ROOT))

RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def load_dataset(category: str = None, split: str = None) -> List[Dict]:
    """Load benchmark dataset with optional filtering."""
    dataset_path = Path(__file__).parent.parent / "benchmark_dataset.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    tasks = data["tasks"]
    if category:
        tasks = [t for t in tasks if t["category"] == category]
    if split:
        tasks = [t for t in tasks if t["split"] == split]
    return tasks


def score_response(task: Dict, response: str) -> Dict[str, Any]:
    """Score a response against expected answer."""
    method = task.get("scoring_method", "keyword_match")
    expected = task.get("expected_answer", "")

    if method == "keyword_match":
        if isinstance(expected, list):
            keywords = expected
        else:
            keywords = [expected] if expected else []
        # Strip markdown bold/italic for matching
        clean_response = response.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
        matched = sum(1 for kw in keywords if kw.lower() in clean_response.lower())
        score = matched / max(1, len(keywords))
        return {"score": score, "matched": matched, "total": len(keywords), "expected": expected, "got": response[:200]}

    elif method == "exact_match":
        # Check if expected answer appears anywhere in response (lenient match)
        clean_response = response.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
        score = 1.0 if expected.strip().lower() in clean_response.strip().lower() else 0.0
        return {"score": score, "expected": expected, "got": response[:200]}

    elif method == "numeric":
        try:
            import re
            nums = re.findall(r"[-+]?\d*\.?\d+", response)
            if nums:
                got = float(nums[0])
                exp = float(expected)
                if exp == 0:
                    score = 1.0 if got == 0 else 0.0
                else:
                    diff = abs(got - exp) / abs(exp)
                    score = max(0, 1.0 - diff)
            else:
                score = 0.0
            return {"score": score, "expected": expected, "got": nums[0] if nums else None}
        except:
            return {"score": 0.0, "error": "parse_failed"}

    elif method == "human_eval":
        return {"score": None, "note": "requires human evaluation"}

    else:
        return {"score": 0.0, "error": f"unknown method: {method}"}


def run_experiment(name: str, func: Callable, **kwargs) -> Dict:
    """Run an experiment with timing and error handling."""
    print(f"\n{'='*60}")
    print(f"EXPERIMENT: {name}")
    print(f"{'='*60}")

    start = time.time()
    try:
        result = func(**kwargs)
        elapsed = time.time() - start
        result["experiment"] = name
        result["elapsed_seconds"] = round(elapsed, 2)
        result["status"] = "completed"
        print(f"  Completed in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - start
        result = {
            "experiment": name,
            "status": "failed",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "elapsed_seconds": round(elapsed, 2),
        }
        print(f"  FAILED: {e}")

    # Save result
    safe_name = name.lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
    result_path = RESULTS_DIR / f"{safe_name}.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Saved to {result_path}")

    return result


def save_results(results: List[Dict], filename: str = "all_results.json"):
    """Save all experiment results."""
    path = RESULTS_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nAll results saved to {path}")


def call_orbit_api(endpoint: str, method: str = "GET", data: Dict = None, timeout: int = 30,
                   session_id: str = "") -> Dict:
    """Call ORBIT Flask API.

    session_id: optional X-Session-Id value. Independent tasks must pass a
    unique id — otherwise every call accumulates into the server-side
    "default" conversation session and later tasks pay a growing-context
    latency penalty (E9 was measuring this artifact, not pipeline cost).
    """
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:5000{endpoint}"

    try:
        if method == "GET":
            req = urllib.request.Request(url)
        else:
            body = json.dumps(data or {}).encode()
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header("Content-Type", "application/json")

        # Add API key if available
        api_key = os.environ.get("ORBIT_API_KEY", "")
        if api_key:
            req.add_header("X-API-Key", api_key)
        if session_id:
            req.add_header("X-Session-Id", session_id)

        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode()[:500]}
    except Exception as e:
        return {"error": str(e)}


def call_orbit_chat(prompt: str, timeout: int = 60, session_id: str = "") -> Dict:
    """Send a message through ORBIT's chat API."""
    return call_orbit_api("/api/chat", "POST", {"message": prompt}, timeout=timeout,
                          session_id=session_id)


def check_orbit_running() -> bool:
    """Check if ORBIT Flask server is running."""
    result = call_orbit_api("/api/health")
    return "error" not in result


def get_ollama_response(prompt: str, model: str = "qwen3:1.7b", timeout: int = 60) -> str:
    """Get direct response from Ollama (no ORBIT pipeline)."""
    import urllib.request

    url = "http://127.0.0.1:11434/api/generate"
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 512}
    }).encode()

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=timeout)
        result = json.loads(resp.read())
        return result.get("response", "")
    except Exception as e:
        return f"ERROR: {e}"


def get_ollama_response_with_context(prompt: str, context: List[Dict], model: str = "qwen3:8b") -> str:
    """Get Ollama response with conversation context."""
    import urllib.request

    # Build context string
    context_str = ""
    for turn in context[-5:]:  # last 5 turns
        role = turn.get("role", "user")
        content = turn.get("content", "")
        context_str += f"{role}: {content}\n"
    context_str += f"user: {prompt}\nassistant:"

    url = "http://127.0.0.1:11434/api/generate"
    data = json.dumps({
        "model": model,
        "prompt": context_str,
        "stream": False,
        "options": {"num_predict": 512}
    }).encode()

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        return result.get("response", "")
    except Exception as e:
        return f"ERROR: {e}"
