"""
Experiment 8: Quality Gate

Question: Does the quality gate actually improve final responses?

Compare:
- Quality Gate ON (default)
- Quality Gate OFF

Measure:
- correctness
- unnecessary refinement
- latency
- false positives
- false negatives
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    run_experiment, get_ollama_response, call_orbit_chat, call_orbit_api,
    check_orbit_running, load_dataset, RESULTS_DIR
)


# Prompts likely to trigger quality gate
QUALITY_GATE_TRIGGERS = [
    {
        "id": "qg_001",
        "prompt": "What is 2+2?",
        "type": "short_answer",
        "expected": "should be concise, not overly verbose",
    },
    {
        "id": "qg_002",
        "prompt": "Write a function to add two numbers in Python",
        "type": "code_generation",
        "expected": "should produce working code",
    },
    {
        "id": "qg_003",
        "prompt": "Explain quantum computing in simple terms",
        "type": "explanation",
        "expected": "should be clear and accessible",
    },
    {
        "id": "qg_004",
        "prompt": "What are the pros and cons of microservices?",
        "type": "analysis",
        "expected": "should be balanced and structured",
    },
    {
        "id": "qg_005",
        "prompt": "Help me debug this: my Python script gives ImportError",
        "type": "debugging",
        "expected": "should provide actionable steps",
    },
    {
        "id": "qg_006",
        "prompt": "Write a haiku about artificial intelligence",
        "type": "creative",
        "expected": "should follow 5-7-5 syllable pattern",
    },
    {
        "id": "qg_007",
        "prompt": "What is the time complexity of binary search?",
        "type": "factual",
        "expected": "should say O(log n)",
    },
    {
        "id": "qg_008",
        "prompt": "Summarize the benefits of exercise in 3 bullet points",
        "type": "structured",
        "expected": "should have exactly 3 bullet points",
    },
    {
        "id": "qg_009",
        "prompt": "Convert 100 USD to EUR approximately",
        "type": "conversion",
        "expected": "should give a reasonable estimate",
    },
    {
        "id": "qg_010",
        "prompt": "What is the difference between a list and a tuple in Python?",
        "type": "comparison",
        "expected": "should mention mutability, syntax, performance",
    },
]


def analyze_response_quality(response: str, task_type: str) -> Dict:
    """Analyze response quality heuristically."""
    analysis = {
        "length": len(response),
        "word_count": len(response.split()),
        "has_code": "```" in response or "def " in response or "import " in response,
        "has_list": "- " in response or "* " in response or "1." in response,
        "is_empty": len(response.strip()) == 0,
        "is_very_short": len(response.split()) < 5,
        "is_very_long": len(response.split()) > 500,
        "quality_score": 0,
    }

    # Basic quality heuristic
    score = 0.5
    if analysis["is_empty"]:
        score = 0
    elif analysis["is_very_short"] and task_type not in ["factual", "short_answer"]:
        score = 0.3
    elif analysis["is_very_long"]:
        score = 0.4
    elif analysis["word_count"] >= 10:
        score = 0.7
    if analysis["has_code"] and task_type == "code_generation":
        score = min(1.0, score + 0.2)
    if analysis["has_list"] and task_type == "structured":
        score = min(1.0, score + 0.1)

    analysis["quality_score"] = score
    return analysis


def run_quality_gate_experiment():
    """Run quality gate comparison experiment."""
    orbit_running = check_orbit_running()

    results = {
        "experiment": "Quality Gate",
        "description": "Does the quality gate improve responses?",
        "orbit_running": orbit_running,
        "tasks": [],
        "summary": {},
    }

    if not orbit_running:
        results["status"] = "BLOCKED"
        results["reason"] = "ORBIT not running"
        return results

    for task in QUALITY_GATE_TRIGGERS:
        print(f"\n  Task: {task['id']} ({task['type']})")

        # Baseline: Direct Ollama (no quality gate)
        print(f"    Direct Ollama...", end="", flush=True)
        start = time.time()
        direct_response = get_ollama_response(task["prompt"], timeout=30)
        direct_latency = (time.time() - start) * 1000
        direct_analysis = analyze_response_quality(direct_response, task["type"])
        print(f" words={direct_analysis['word_count']} score={direct_analysis['quality_score']:.2f}")

        # ORBIT with quality gate (default)
        print(f"    ORBIT (gate ON)...", end="", flush=True)
        start = time.time()
        orbit_on = call_orbit_chat(task["prompt"], timeout=60)
        orbit_on_latency = (time.time() - start) * 1000
        if "error" not in orbit_on:
            on_response = orbit_on.get("response", orbit_on.get("text", ""))
            on_analysis = analyze_response_quality(on_response, task["type"])
            print(f" words={on_analysis['word_count']} score={on_analysis['quality_score']:.2f}")
        else:
            on_response = ""
            on_analysis = {"error": orbit_on["error"]}
            print(f" ERROR")

        task_result = {
            "id": task["id"],
            "type": task["type"],
            "direct": {
                "response": direct_response[:500],
                "analysis": direct_analysis,
                "latency_ms": round(direct_latency, 1),
            },
            "orbit_on": {
                "response": on_response[:500],
                "analysis": on_analysis,
                "latency_ms": round(orbit_on_latency, 1),
            },
        }

        results["tasks"].append(task_result)
        time.sleep(1)

    # Summary
    direct_scores = [t["direct"]["analysis"].get("quality_score", 0) for t in results["tasks"]]
    orbit_scores = [t["orbit_on"]["analysis"].get("quality_score", 0) for t in results["tasks"] if "error" not in t["orbit_on"].get("analysis", {})]

    results["summary"] = {
        "direct_mean_quality": round(sum(direct_scores) / max(1, len(direct_scores)), 3),
        "orbit_mean_quality": round(sum(orbit_scores) / max(1, len(orbit_scores)), 3),
        "direct_mean_latency": round(sum(t["direct"]["latency_ms"] for t in results["tasks"]) / len(results["tasks"]), 1),
        "orbit_mean_latency": round(sum(t["orbit_on"]["latency_ms"] for t in results["tasks"] if "error" not in t["orbit_on"].get("analysis", {})) / max(1, len(orbit_scores)), 1),
        "tasks_with_quality_gate": len([t for t in results["tasks"] if t["orbit_on"]["analysis"].get("quality_score", 0) > t["direct"]["analysis"].get("quality_score", 0)]),
        "tasks_without_improvement": len([t for t in results["tasks"] if t["orbit_on"]["analysis"].get("quality_score", 0) <= t["direct"]["analysis"].get("quality_score", 0)]),
    }

    return results


if __name__ == "__main__":
    result = run_experiment("Quality Gate", run_quality_gate_experiment)
