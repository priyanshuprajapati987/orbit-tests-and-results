"""
Experiment 10: Real-World Task Suite

Test with realistic, multi-step tasks that users actually ask.

Categories:
- Research tasks
- Code generation
- File operations
- System administration
- Creative writing
- Data analysis
- Debugging
- Planning
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    run_experiment, get_ollama_response, call_orbit_chat,
    call_orbit_api, check_orbit_running, RESULTS_DIR
)


REAL_WORLD_TASKS = [
    {
        "id": "rw_001",
        "category": "file_management",
        "prompt": "Create a project structure for a Python package with src/, tests/, docs/, and a setup.py file",
        "validation": {
            "type": "file_check",
            "expected_files": ["src/", "tests/", "docs/", "setup.py"],
        },
    },
    {
        "id": "rw_002",
        "category": "code_generation",
        "prompt": "Write a Python class for a Stack data structure with push, pop, peek, and is_empty methods",
        "validation": {
            "type": "code_check",
            "expected_methods": ["push", "pop", "peek", "is_empty"],
        },
    },
    {
        "id": "rw_003",
        "category": "debugging",
        "prompt": "My Python script has this error: TypeError: unsupported operand type(s) for +: 'int' and 'str'. How do I fix it?",
        "validation": {
            "type": "response_check",
            "expected_keywords": ["int", "str", "convert", "type"],
        },
    },
    {
        "id": "rw_004",
        "category": "research",
        "prompt": "Compare PostgreSQL and MongoDB for a social media application. Which one would you recommend?",
        "validation": {
            "type": "response_check",
            "expected_keywords": ["postgresql", "mongodb", "recommend"],
        },
    },
    {
        "id": "rw_005",
        "category": "system_info",
        "prompt": "What operating system am I using and how much RAM does my system have?",
        "validation": {
            "type": "response_check",
            "expected_keywords": ["windows", "ram", "memory"],
        },
    },
    {
        "id": "rw_006",
        "category": "creative",
        "prompt": "Write a haiku about artificial intelligence",
        "validation": {
            "type": "response_check",
            "expected_keywords": ["ai", "intelligence", "machine"],
        },
    },
    {
        "id": "rw_007",
        "category": "planning",
        "prompt": "I want to learn machine learning. Give me a 3-month study plan.",
        "validation": {
            "type": "response_check",
            "expected_keywords": ["month", "learn", "plan"],
        },
    },
    {
        "id": "rw_008",
        "category": "file_operations",
        "prompt": "List all Python files in the current directory and count how many there are",
        "validation": {
            "type": "response_check",
            "expected_keywords": ["python", "files"],
        },
    },
    {
        "id": "rw_009",
        "category": "code_generation",
        "prompt": "Write a Python function that reads a CSV file and returns the column names",
        "validation": {
            "type": "code_check",
            "expected_keywords": ["csv", "def", "read"],
        },
    },
    {
        "id": "rw_010",
        "category": "explanation",
        "prompt": "Explain what a REST API is in simple terms",
        "validation": {
            "type": "response_check",
            "expected_keywords": ["rest", "api", "http"],
        },
    },
    {
        "id": "rw_011",
        "category": "file_management",
        "prompt": "Create a todo list file at orbit_data/validation_todo.txt with items: Buy groceries, Finish report, Call dentist",
        "validation": {
            "type": "file_check",
            "expected_files": ["orbit_data/validation_todo.txt"],
            "expected_content": ["Buy groceries", "Finish report", "Call dentist"],
        },
    },
    {
        "id": "rw_012",
        "category": "system_info",
        "prompt": "List the top 5 running processes by memory usage",
        "validation": {
            "type": "response_check",
            "expected_keywords": ["process", "memory"],
        },
    },
]


def run_real_world_experiment():
    """Run real-world task suite experiment."""
    orbit_running = check_orbit_running()

    results = {
        "experiment": "Real-World Task Suite",
        "description": "Test with realistic multi-step tasks",
        "orbit_running": orbit_running,
        "tasks": [],
        "summary": {},
    }

    category_scores = {}

    for task in REAL_WORLD_TASKS:
        print(f"\n  Task: {task['id']} ({task['category']})")

        # Baseline: Direct Ollama
        print(f"    Direct...", end="", flush=True)
        start = time.time()
        direct_response = get_ollama_response(task["prompt"], timeout=30)
        direct_latency = (time.time() - start) * 1000
        print(f" {direct_latency:.0f}ms")

        # ORBIT pipeline
        print(f"    ORBIT...", end="", flush=True)
        start = time.time()
        orbit_result = call_orbit_chat(task["prompt"], timeout=60, session_id=f"e10-{task['id']}")
        orbit_latency = (time.time() - start) * 1000

        if "error" not in orbit_result:
            orbit_response = orbit_result.get("response", orbit_result.get("text", ""))
            print(f" {orbit_latency:.0f}ms agent={orbit_result.get('agent', '?')}")
        else:
            orbit_response = orbit_result["error"]
            print(f" ERROR: {orbit_response[:80]}")

        # Simple scoring based on validation
        validation = task.get("validation", {})
        expected_keywords = validation.get("expected_keywords", [])

        if expected_keywords:
            direct_found = sum(1 for kw in expected_keywords if kw.lower() in direct_response.lower())
            orbit_found = sum(1 for kw in expected_keywords if kw.lower() in orbit_response.lower())
            direct_score = direct_found / max(1, len(expected_keywords))
            orbit_score = orbit_found / max(1, len(expected_keywords))
        else:
            direct_score = 0.5 if len(direct_response.strip()) > 10 else 0
            orbit_score = 0.5 if len(orbit_response.strip()) > 10 else 0

        cat = task["category"]
        if cat not in category_scores:
            category_scores[cat] = {"direct": [], "orbit": []}
        category_scores[cat]["direct"].append(direct_score)
        category_scores[cat]["orbit"].append(orbit_score)

        results["tasks"].append({
            "id": task["id"],
            "category": task["category"],
            "direct": {
                "score": direct_score,
                "latency_ms": round(direct_latency, 1),
                "response_preview": direct_response[:200],
            },
            "orbit": {
                "score": orbit_score,
                "latency_ms": round(orbit_latency, 1),
                "response_preview": orbit_response[:200],
                "agent": orbit_result.get("agent", "unknown") if "error" not in orbit_result else "error",
            },
        })

        time.sleep(0.5)

    # Summary
    all_direct = [t["direct"]["score"] for t in results["tasks"]]
    all_orbit = [t["orbit"]["score"] for t in results["tasks"]]

    results["summary"] = {
        "total_tasks": len(REAL_WORLD_TASKS),
        "direct_mean_score": round(sum(all_direct) / max(1, len(all_direct)), 3),
        "orbit_mean_score": round(sum(all_orbit) / max(1, len(all_orbit)), 3),
        "category_breakdown": {
            cat: {
                "direct_mean": round(sum(s["direct"]) / max(1, len(s["direct"])), 3),
                "orbit_mean": round(sum(s["orbit"]) / max(1, len(s["orbit"])), 3),
                "n": len(s["direct"]),
            }
            for cat, s in category_scores.items()
        },
    }

    return results


if __name__ == "__main__":
    result = run_experiment("Real-World Task Suite", run_real_world_experiment)
    if "summary" in result:
        s = result["summary"]
        print(f"\n{'='*60}")
        print(f"Real-World Task Results")
        print(f"{'='*60}")
        print(f"Direct mean score: {s['direct_mean_score']}")
        print(f"ORBIT mean score:  {s['orbit_mean_score']}")
        print(f"\nBy category:")
        for cat, data in s.get("category_breakdown", {}).items():
            print(f"  {cat}: direct={data['direct_mean']:.2f} orbit={data['orbit_mean']:.2f} (n={data['n']})")
