"""
Experiment 3: Memory Effectiveness

Question: Does ORBIT memory actually work?

Create multi-session tests to measure:
- Recall accuracy
- False recall
- Stale memory
- Contradiction handling
- Irrelevant memory injection

Compare: Memory ON vs Memory OFF
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    run_experiment, get_ollama_response, get_ollama_response_with_context,
    call_orbit_chat, call_orbit_api, check_orbit_running, RESULTS_DIR
)


# Memory test scenarios
MEMORY_TESTS = [
    {
        "id": "mem_001",
        "name": "basic_recall",
        "setup": [
            {"role": "user", "content": "My cat's name is Whiskers and she is 3 years old."},
            {"role": "assistant", "content": "Got it! Whiskers is your 3-year-old cat."},
            {"role": "user", "content": "My dog's name is Buddy and he is a Golden Retriever."},
            {"role": "assistant", "content": "Nice! Buddy is your Golden Retriever."},
            {"role": "user", "content": "I live in Seattle and work at Amazon."},
            {"role": "assistant", "content": "Got it, you live in Seattle and work at Amazon."},
        ],
        "question": "What is my cat's name?",
        "expected_keywords": ["whiskers"],
        "expected_wrong": ["buddy"],
    },
    {
        "id": "mem_002",
        "name": "multi_fact_recall",
        "setup": [
            {"role": "user", "content": "My favorite color is purple."},
            {"role": "assistant", "content": "Noted, purple is your favorite."},
            {"role": "user", "content": "I prefer Python over JavaScript."},
            {"role": "assistant", "content": "Python over JavaScript, got it."},
            {"role": "user", "content": "My birthday is March 15th."},
            {"role": "assistant", "content": "March 15th, noted!"},
            {"role": "user", "content": "I am allergic to peanuts."},
            {"role": "assistant", "content": "Peanut allergy noted."},
            {"role": "user", "content": "I have two siblings, both older."},
            {"role": "assistant", "content": "Two older siblings, got it."},
        ],
        "question": "What are all the facts you know about me?",
        "expected_keywords": ["purple", "python", "march", "peanut", "sibling"],
        "min_facts": 4,
    },
    {
        "id": "mem_003",
        "name": "contradiction_handling",
        "setup": [
            {"role": "user", "content": "I work at Google."},
            {"role": "assistant", "content": "Google, nice!"},
            {"role": "user", "content": "Actually, I just changed jobs. I work at Microsoft now."},
            {"role": "assistant", "content": "Microsoft, congrats on the new job!"},
        ],
        "question": "Where do I work?",
        "expected_keywords": ["microsoft"],
        "expected_wrong": ["google"],
    },
    {
        "id": "mem_004",
        "name": "indirect_recall",
        "setup": [
            {"role": "user", "content": "My mother tongue is Hindi."},
            {"role": "assistant", "content": "Hindi, great language!"},
            {"role": "user", "content": "I studied at IIT Bombay."},
            {"role": "assistant", "content": "IIT Bombay, impressive!"},
            {"role": "user", "content": "I drive a Toyota Camry."},
            {"role": "assistant", "content": "Toyota Camry, solid choice!"},
        ],
        "question": "What language did I grow up speaking?",
        "expected_keywords": ["hindi"],
    },
    {
        "id": "mem_005",
        "name": "irrelevant_memory_injection",
        "setup": [
            {"role": "user", "content": "The weather is nice today."},
            {"role": "assistant", "content": "Glad to hear it!"},
            {"role": "user", "content": "My project deadline is next Friday."},
            {"role": "assistant", "content": "Good to know, plan accordingly."},
        ],
        "question": "What is my project deadline?",
        "expected_keywords": ["friday"],
        "expected_wrong": ["weather"],
    },
    {
        "id": "mem_006",
        "name": "sequential_dependency",
        "setup": [
            {"role": "user", "content": "I have a meeting at 2pm."},
            {"role": "assistant", "content": "2pm meeting noted."},
            {"role": "user", "content": "It's with the engineering team."},
            {"role": "assistant", "content": "Engineering team at 2pm."},
            {"role": "user", "content": "We're discussing the Q4 roadmap."},
            {"role": "assistant", "content": "Q4 roadmap discussion."},
        ],
        "question": "What is my 2pm meeting about?",
        "expected_keywords": ["roadmap", "q4"],
    },
    {
        "id": "mem_007",
        "name": "preference_learning",
        "setup": [
            {"role": "user", "content": "I prefer short, concise answers."},
            {"role": "assistant", "content": "Noted, I'll keep responses concise."},
            {"role": "user", "content": "Don't use bullet points, I prefer paragraphs."},
            {"role": "assistant", "content": "Got it, paragraphs instead of bullets."},
        ],
        "question": "How should I format my responses to you?",
        "expected_keywords": ["concise", "paragraph"],
    },
    {
        "id": "mem_008",
        "name": "numerical_memory",
        "setup": [
            {"role": "user", "content": "My project has 47 open issues."},
            {"role": "assistant", "content": "47 open issues, noted."},
            {"role": "user", "content": "We have 5 developers on the team."},
            {"role": "assistant", "content": "5 developers."},
            {"role": "user", "content": "The budget is $150,000 for this quarter."},
            {"role": "assistant", "content": "$150K quarterly budget."},
        ],
        "question": "How many open issues does my project have?",
        "expected_keywords": ["47"],
    },
]


def run_memory_experiment():
    """Run memory effectiveness experiment."""
    orbit_running = check_orbit_running()

    results = {
        "experiment": "Memory Effectiveness",
        "description": "Does ORBIT memory actually work?",
        "orbit_running": orbit_running,
        "tests": [],
        "summary": {},
    }

    # Baseline: Ollama without ORBIT memory
    ollama_scores = []
    orbit_scores = []

    for test in MEMORY_TESTS:
        print(f"\n  Test: {test['name']} ({test['id']})")

        # Baseline: Direct Ollama with context
        print(f"    Baseline: Direct Ollama...", end="", flush=True)
        start = time.time()
        response = get_ollama_response_with_context(test["question"], test["setup"])
        latency = (time.time() - start) * 1000

        score = 0
        for kw in test["expected_keywords"]:
            if kw.lower() in response.lower():
                score += 1
        score = score / max(1, len(test["expected_keywords"]))

        # Check for wrong answers
        wrong_count = 0
        for wrong in test.get("expected_wrong", []):
            if wrong.lower() in response.lower():
                wrong_count += 1

        ollama_scores.append(score)
        print(f" score={score:.2f} wrong={wrong_count}")

        test_result = {
            "id": test["id"],
            "name": test["name"],
            "baseline": {
                "response": response[:500],
                "score": score,
                "wrong_answers": wrong_count,
                "latency_ms": round(latency, 1),
            },
        }

        # ORBIT pipeline
        if orbit_running:
            print(f"    ORBIT pipeline...", end="", flush=True)
            # Build the full conversation as one message
            full_prompt = ""
            for turn in test["setup"]:
                full_prompt += f"{turn['role']}: {turn['content']}\n"
            full_prompt += f"\n{test['question']}"

            start = time.time()
            orbit_response = call_orbit_chat(full_prompt, timeout=60)
            latency = (time.time() - start) * 1000

            if "error" not in orbit_response:
                actual = orbit_response.get("response", orbit_response.get("text", ""))
                score_o = 0
                for kw in test["expected_keywords"]:
                    if kw.lower() in actual.lower():
                        score_o += 1
                score_o = score_o / max(1, len(test["expected_keywords"]))

                wrong_o = 0
                for wrong in test.get("expected_wrong", []):
                    if wrong.lower() in actual.lower():
                        wrong_o += 1

                orbit_scores.append(score_o)
                test_result["orbit"] = {
                    "response": actual[:500],
                    "score": score_o,
                    "wrong_answers": wrong_o,
                    "latency_ms": round(latency, 1),
                }
                print(f" score={score_o:.2f} wrong={wrong_o}")
            else:
                test_result["orbit"] = {"error": orbit_response["error"]}
                print(f" ERROR")

        results["tests"].append(test_result)
        time.sleep(0.5)

    # Summary
    results["summary"] = {
        "baseline_mean_score": round(sum(ollama_scores) / max(1, len(ollama_scores)), 3),
        "baseline_n": len(ollama_scores),
    }
    if orbit_scores:
        results["summary"]["orbit_mean_score"] = round(sum(orbit_scores) / max(1, len(orbit_scores)), 3)
        results["summary"]["orbit_n"] = len(orbit_scores)
        results["summary"]["delta"] = round(
            results["summary"]["orbit_mean_score"] - results["summary"]["baseline_mean_score"], 3
        )

    return results


if __name__ == "__main__":
    result = run_experiment("Memory Effectiveness", run_memory_experiment)
