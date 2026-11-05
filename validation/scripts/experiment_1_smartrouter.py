"""
Experiment 1: SmartRouter Value

Question: Does SmartRouter actually improve outcomes?

Compare:
- Baseline A: Direct Ollama (no ORBIT)
- Baseline C: Single agent with SmartRouter
- Baseline D: Full ORBIT pipeline

Use identical tasks from the benchmark dataset.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    load_dataset, score_response, run_experiment,
    get_ollama_response, call_orbit_chat, check_orbit_running,
    save_results, RESULTS_DIR
)


def run_smartrouter_experiment():
    """Run SmartRouter comparison experiment."""
    tasks = load_dataset(category=None, split="dev")

    # Use a subset for initial run (first 50 tasks)
    test_tasks = tasks[:50]

    results = {
        "experiment": "SmartRouter Value",
        "description": "Does SmartRouter improve outcomes vs direct model?",
        "total_tasks": len(test_tasks),
        "baselines": {},
        "task_results": [],
    }

    # Check ORBIT
    orbit_running = check_orbit_running()
    print(f"ORBIT running: {orbit_running}")

    ollama_running = False
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        ollama_running = True
    except:
        pass
    print(f"Ollama running: {ollama_running}")

    if not ollama_running:
        results["status"] = "BLOCKED"
        results["reason"] = "Ollama not running"
        return results

    baseline_a_scores = []
    baseline_c_scores = []
    baseline_d_scores = []

    for i, task in enumerate(test_tasks):
        print(f"\n  Task {i+1}/{len(test_tasks)}: {task['id']} ({task['category']})")
        prompt = task["prompt"]

        task_result = {
            "id": task["id"],
            "category": task["category"],
            "prompt": prompt[:200],
            "baselines": {},
        }

        # Baseline A: Direct Ollama (no ORBIT)
        print(f"    Baseline A: Direct Ollama...", end="", flush=True)
        start = time.time()
        response_a = get_ollama_response(prompt, timeout=30)
        latency_a = (time.time() - start) * 1000
        score_a = score_response(task, response_a)
        baseline_a_scores.append(score_a["score"])
        task_result["baselines"]["A_direct"] = {
            "response": response_a[:500],
            "score": score_a["score"],
            "latency_ms": round(latency_a, 1),
        }
        print(f" score={score_a['score']:.2f}")

        # Baseline C: ORBIT with SmartRouter (single agent)
        if orbit_running:
            print(f"    Baseline C: ORBIT pipeline...", end="", flush=True)
            start = time.time()
            response_c = call_orbit_chat(prompt, timeout=60)
            latency_c = (time.time() - start) * 1000
            if "error" not in response_c:
                actual_response = response_c.get("response", response_c.get("text", ""))
                score_c = score_response(task, actual_response)
                baseline_c_scores.append(score_c["score"])
                task_result["baselines"]["C_orbit"] = {
                    "response": actual_response[:500],
                    "score": score_c["score"],
                    "latency_ms": round(latency_c, 1),
                    "agent": response_c.get("agent", "unknown"),
                    "provider": response_c.get("provider", "unknown"),
                }
                print(f" score={score_c['score']:.2f} agent={response_c.get('agent', '?')}")
            else:
                task_result["baselines"]["C_orbit"] = {"error": response_c["error"]}
                print(f" ERROR: {response_c['error']}")
        else:
            task_result["baselines"]["C_orbit"] = {"error": "ORBIT not running"}

        results["task_results"].append(task_result)

        # Rate limit
        time.sleep(0.5)

    # Calculate aggregates
    results["baselines"]["A_direct"] = {
        "mean_score": round(sum(baseline_a_scores) / max(1, len(baseline_a_scores)), 3),
        "n": len(baseline_a_scores),
    }
    if baseline_c_scores:
        results["baselines"]["C_orbit"] = {
            "mean_score": round(sum(baseline_c_scores) / max(1, len(baseline_c_scores)), 3),
            "n": len(baseline_c_scores),
        }

    # Calculate delta
    if baseline_a_scores and baseline_c_scores:
        mean_a = sum(baseline_a_scores) / len(baseline_a_scores)
        mean_c = sum(baseline_c_scores) / len(baseline_c_scores)
        results["delta"] = {
            "absolute": round(mean_c - mean_a, 3),
            "relative_pct": round((mean_c - mean_a) / max(0.001, mean_a) * 100, 1),
            "verdict": "IMPROVEMENT" if mean_c > mean_a else "REGRESSION" if mean_c < mean_a else "NO_DIFFERENCE",
        }

    return results


if __name__ == "__main__":
    result = run_experiment("SmartRouter Value", run_smartrouter_experiment)
    print(f"\nVerdict: {result.get('delta', {}).get('verdict', 'INCONCLUSIVE')}")
