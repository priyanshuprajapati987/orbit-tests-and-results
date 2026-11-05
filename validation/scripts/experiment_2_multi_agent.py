"""
Experiment 2: Queen / Multi-Agent Value

Question: Does multi-agent orchestration actually improve results?

Compare:
- Baseline: Single agent (direct model)
- ORBIT: Queen orchestration (planner + worker + critic)

Measure:
- Correctness
- Completion quality
- Latency
- Agent routing accuracy
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    run_experiment, get_ollama_response, call_orbit_chat,
    call_orbit_api, check_orbit_running, RESULTS_DIR
)


# Tasks that might benefit from multi-agent orchestration
MULTI_AGENT_TASKS = [
    {
        "id": "ma_001",
        "prompt": "Research the latest Python web frameworks and recommend one for a REST API project",
        "category": "research",
        "expected_elements": ["framework", "python", "rest", "api"],
    },
    {
        "id": "ma_002",
        "prompt": "Write a Python function to find the longest palindromic substring and explain the algorithm",
        "category": "code_explain",
        "expected_elements": ["def", "palindrome", "function"],
    },
    {
        "id": "ma_003",
        "prompt": "Analyze the pros and cons of using PostgreSQL vs MongoDB for a social media application",
        "category": "analysis",
        "expected_elements": ["postgresql", "mongodb", "pros", "cons"],
    },
    {
        "id": "ma_004",
        "prompt": "Create a plan to deploy a Python Flask app to production with Docker and CI/CD",
        "category": "planning",
        "expected_elements": ["docker", "flask", "ci", "deploy"],
    },
    {
        "id": "ma_005",
        "prompt": "Debug this issue: my Python script gives 'ModuleNotFoundError: No module named requests'",
        "category": "debugging",
        "expected_elements": ["pip", "install", "requests"],
    },
    {
        "id": "ma_006",
        "prompt": "Write unit tests for a calculator function that handles add, subtract, multiply, divide",
        "category": "testing",
        "expected_elements": ["test", "assert", "def"],
    },
    {
        "id": "ma_007",
        "prompt": "Explain the difference between SQL and NoSQL databases with examples",
        "category": "explanation",
        "expected_elements": ["sql", "nosql", "example"],
    },
    {
        "id": "ma_008",
        "prompt": "Design a REST API for a todo list application with authentication",
        "category": "design",
        "expected_elements": ["api", "todo", "auth", "endpoint"],
    },
    {
        "id": "ma_009",
        "prompt": "What are the best practices for securing a Python web application?",
        "category": "security",
        "expected_elements": ["security", "authentication", "input"],
    },
    {
        "id": "ma_010",
        "prompt": "Write a Python script that fetches weather data from an API and displays it",
        "category": "code_generation",
        "expected_elements": ["def", "import", "weather"],
    },
]


def score_task_response(task: Dict, response: str) -> Dict:
    """Score a task response on multiple dimensions."""
    expected = task.get("expected_elements", [])
    words = set(response.lower().split())

    # Element coverage
    elements_found = sum(1 for e in expected if e.lower() in response.lower())
    element_coverage = elements_found / max(1, len(expected))

    # Response quality
    word_count = len(response.split())
    has_code = "```" in response or "def " in response
    has_structure = "- " in response or "* " in response or "1." in response

    # Basic quality score
    score = 0.5
    if element_coverage > 0.7:
        score = 0.8
    if element_coverage > 0.9:
        score = 1.0
    if word_count < 10:
        score *= 0.5
    if has_code:
        score = min(1.0, score + 0.1)
    if has_structure:
        score = min(1.0, score + 0.1)

    return {
        "score": score,
        "element_coverage": element_coverage,
        "elements_found": elements_found,
        "elements_total": len(expected),
        "word_count": word_count,
        "has_code": has_code,
        "has_structure": has_structure,
    }


def run_multi_agent_experiment():
    """Run multi-agent value experiment."""
    orbit_running = check_orbit_running()

    results = {
        "experiment": "Queen / Multi-Agent Value",
        "description": "Does multi-agent orchestration improve results?",
        "orbit_running": orbit_running,
        "tasks": [],
        "summary": {},
    }

    direct_scores = []
    orbit_scores = []
    direct_latencies = []
    orbit_latencies = []

    for task in MULTI_AGENT_TASKS:
        print(f"\n  Task: {task['id']} ({task['category']})")

        # Baseline: Direct Ollama
        print(f"    Direct...", end="", flush=True)
        start = time.time()
        direct_response = get_ollama_response(task["prompt"], timeout=30)
        direct_latency = (time.time() - start) * 1000
        direct_score = score_task_response(task, direct_response)
        direct_scores.append(direct_score["score"])
        direct_latencies.append(direct_latency)
        print(f" score={direct_score['score']:.2f}")

        # ORBIT with full pipeline
        print(f"    ORBIT...", end="", flush=True)
        start = time.time()
        orbit_result = call_orbit_chat(task["prompt"], timeout=60)
        orbit_latency = (time.time() - start) * 1000

        if "error" not in orbit_result:
            orbit_response = orbit_result.get("response", orbit_result.get("text", ""))
            orbit_score_result = score_task_response(task, orbit_response)
            orbit_scores.append(orbit_score_result["score"])
            orbit_latencies.append(orbit_latency)
            print(f" score={orbit_score_result['score']:.2f}")
        else:
            orbit_scores.append(0)
            orbit_latencies.append(orbit_latency)
            orbit_response = orbit_result["error"]
            print(f" ERROR")

        results["tasks"].append({
            "id": task["id"],
            "category": task["category"],
            "direct": {
                "score": direct_score["score"],
                "element_coverage": direct_score["element_coverage"],
                "latency_ms": round(direct_latency, 1),
            },
            "orbit": {
                "score": orbit_scores[-1],
                "latency_ms": round(orbit_latency, 1),
                "agent": orbit_result.get("agent", "unknown") if "error" not in orbit_result else "error",
            },
        })

        time.sleep(0.5)

    if direct_scores and orbit_scores:
        mean_direct = sum(direct_scores) / len(direct_scores)
        mean_orbit = sum(orbit_scores) / len(orbit_scores)

        results["summary"] = {
            "direct_mean_score": round(mean_direct, 3),
            "orbit_mean_score": round(mean_orbit, 3),
            "delta": round(mean_orbit - mean_direct, 3),
            "direct_mean_latency_ms": round(sum(direct_latencies) / len(direct_latencies), 1),
            "orbit_mean_latency_ms": round(sum(orbit_latencies) / len(orbit_latencies), 1),
        }

    return results


if __name__ == "__main__":
    result = run_experiment("Queen / Multi-Agent Value", run_multi_agent_experiment)
