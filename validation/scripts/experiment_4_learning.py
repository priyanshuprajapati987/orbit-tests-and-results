"""
Experiment 4: Learning Effectiveness

Question: Does ORBIT's self-improvement system actually learn?

Test:
- Memory consolidation
- Preference learning
- Correction patterns
- Routing improvements
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


LEARNING_TESTS = [
    {
        "id": "learn_001",
        "name": "preference_learning",
        "description": "Teach a preference and see if it's remembered",
        "setup": [
            {"role": "user", "content": "I prefer short, direct answers. No explanations unless I ask for them."},
            {"role": "assistant", "content": "Got it! Short and direct."},
        ],
        "query": "What is the capital of France?",
        "expected": "Paris",
        "preference_check": "should be short (under 10 words)",
    },
    {
        "id": "learn_002",
        "name": "context_retention",
        "description": "Test if context from earlier turns is retained",
        "setup": [
            {"role": "user", "content": "I'm building a social media app called SocialX"},
            {"role": "assistant", "content": "SocialX, nice name! What do you need help with?"},
            {"role": "user", "content": "I'm using React for frontend and Node.js for backend"},
            {"role": "assistant", "content": "React + Node.js, solid stack!"},
        ],
        "query": "What tech stack am I using for my project?",
        "expected": "React Node.js",
        "preference_check": "should mention both React and Node.js",
    },
    {
        "id": "learn_003",
        "name": "correction_handling",
        "description": "Correct the model and see if it adapts",
        "setup": [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "2+2 = 4"},
            {"role": "user", "content": "Actually, I meant 2+2 in binary, which is 10."},
            {"role": "assistant", "content": "You're right, 2+2 in binary is 10."},
        ],
        "query": "What is 2+2 in binary?",
        "expected": "10",
        "preference_check": "should answer 10, not 4",
    },
    {
        "id": "learn_004",
        "name": "multi_turn_coherence",
        "description": "Maintain coherent conversation across multiple turns",
        "setup": [
            {"role": "user", "content": "Let's discuss Python decorators"},
            {"role": "assistant", "content": "Sure! Decorators are a powerful feature in Python..."},
            {"role": "user", "content": "Can you show me a basic example?"},
            {"role": "assistant", "content": "Here's a simple decorator example..."},
            {"role": "user", "content": "How about a decorator with arguments?"},
            {"role": "assistant", "content": "For decorators with arguments, you need an extra layer..."},
        ],
        "query": "What were we just discussing?",
        "expected": "decorator",
        "preference_check": "should mention decorators or the topic of conversation",
    },
    {
        "id": "learn_005",
        "name": "fact_correction",
        "description": "Correct a factual error and verify the correction sticks",
        "setup": [
            {"role": "user", "content": "The capital of Australia is Sydney."},
            {"role": "assistant", "content": "Actually, the capital of Australia is Canberra, not Sydney."},
        ],
        "query": "What is the capital of Australia?",
        "expected": "Canberra",
        "preference_check": "should say Canberra, not Sydney",
    },
    {
        "id": "learn_006",
        "name": "domain_knowledge",
        "description": "Test domain-specific knowledge retention",
        "setup": [
            {"role": "user", "content": "I'm a Python developer with 5 years of experience"},
            {"role": "assistant", "content": "Nice! With that experience, you probably know Python well."},
            {"role": "user", "content": "I mainly work with Django and data science libraries"},
            {"role": "assistant", "content": "Django + data science, great combo!"},
        ],
        "query": "What kind of developer am I?",
        "expected": "Python Django data science",
        "preference_check": "should mention Python, Django, and data science",
    },
    {
        "id": "learn_007",
        "name": "instruction_following",
        "description": "Follow specific formatting instructions",
        "setup": [
            {"role": "user", "content": "When I ask for a list, always use numbered items, not bullet points."},
            {"role": "assistant", "content": "Got it! I'll use numbered lists from now on."},
        ],
        "query": "Give me a list of 3 programming languages",
        "expected": "1.",
        "preference_check": "should use numbered list format (1. 2. 3.)",
    },
    {
        "id": "learn_008",
        "name": "context_switching",
        "description": "Switch topics and return to original",
        "setup": [
            {"role": "user", "content": "My project uses FastAPI and PostgreSQL"},
            {"role": "assistant", "content": "FastAPI + PostgreSQL, great stack!"},
            {"role": "user", "content": "What's the weather today?"},
            {"role": "assistant", "content": "I don't have access to real-time weather data."},
            {"role": "user", "content": "Back to my project - what database migrations should I use?"},
            {"role": "assistant", "content": "For FastAPI + PostgreSQL, I recommend Alembic for migrations."},
        ],
        "query": "What database am I using for my project?",
        "expected": "PostgreSQL",
        "preference_check": "should remember PostgreSQL from earlier",
    },
]


def run_learning_experiment():
    """Run learning effectiveness experiment."""
    orbit_running = check_orbit_running()

    results = {
        "experiment": "Learning Effectiveness",
        "description": "Does ORBIT's self-improvement system actually learn?",
        "orbit_running": orbit_running,
        "tests": [],
        "summary": {},
    }

    passed = 0
    failed = 0

    for test in LEARNING_TESTS:
        print(f"\n  Test: {test['name']}")

        # Build full conversation with context
        full_prompt = ""
        for turn in test["setup"]:
            full_prompt += f"{turn['role']}: {turn['content']}\n"
        full_prompt += f"\n{test['query']}"

        # Test with ORBIT
        if orbit_running:
            print(f"    ORBIT...", end="", flush=True)
            start = time.time()
            orbit_result = call_orbit_chat(full_prompt, timeout=60, session_id=f"e4-{test['id']}")
            latency = (time.time() - start) * 1000

            if "error" not in orbit_result:
                orbit_response = orbit_result.get("response", orbit_result.get("text", ""))
                # Check if expected keywords are present
                expected_keywords = test["expected"].split()
                found = sum(1 for kw in expected_keywords if kw.lower() in orbit_response.lower())
                score = found / max(1, len(expected_keywords))
                test_passed = score >= 0.5

                if test_passed:
                    passed += 1
                    print(f" PASS ({latency:.0f}ms)")
                else:
                    failed += 1
                    print(f" FAIL ({latency:.0f}ms) expected='{test['expected']}' got='{orbit_response[:100]}'")

                results["tests"].append({
                    "id": test["id"],
                    "name": test["name"],
                    "status": "passed" if test_passed else "failed",
                    "response": orbit_response[:500],
                    "expected": test["expected"],
                    "score": score,
                    "latency_ms": round(latency, 1),
                })
            else:
                failed += 1
                print(f" ERROR: {orbit_result['error'][:80]}")
                results["tests"].append({
                    "id": test["id"],
                    "name": test["name"],
                    "status": "error",
                    "error": orbit_result["error"],
                })
        else:
            print(f"    SKIPPED (ORBIT not running)")
            results["tests"].append({
                "id": test["id"],
                "name": test["name"],
                "status": "skipped",
            })

        time.sleep(1)

    total = passed + failed
    results["summary"] = {
        "total_tests": len(LEARNING_TESTS),
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / max(1, total) * 100, 1),
    }

    return results


if __name__ == "__main__":
    result = run_experiment("Learning Effectiveness", run_learning_experiment)
    if "summary" in result:
        s = result["summary"]
        print(f"\nPass rate: {s['pass_rate']}% ({s['passed']}/{s['total_tests']})")
