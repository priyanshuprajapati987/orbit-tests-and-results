"""
Experiment 9: Full Pipeline vs Direct Model

The most important experiment.

Does ORBIT's full pipeline actually provide value compared to raw model?

Compare:
- Baseline A: Direct Ollama (no ORBIT)
- Baseline D: Full ORBIT pipeline

Use identical tasks from the benchmark dataset.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    load_dataset, score_response, run_experiment,
    get_ollama_response, call_orbit_chat, call_orbit_api,
    check_orbit_running, RESULTS_DIR
)


def run_full_pipeline_experiment():
    """Run full pipeline comparison experiment."""
    tasks = load_dataset(split="dev")

    # Use first 60 tasks for initial run
    test_tasks = tasks[:60]

    results = {
        "experiment": "Full Pipeline Value",
        "description": "Does ORBIT's full pipeline outperform raw model?",
        "total_tasks": len(test_tasks),
        "orbit_running": check_orbit_running(),
        "task_results": [],
        "summary": {},
    }

    direct_scores = []
    orbit_scores = []
    direct_latencies = []
    orbit_latencies = []
    routing_decisions = []

    for i, task in enumerate(test_tasks):
        prompt = task["prompt"]
        print(f"\n  Task {i+1}/{len(test_tasks)}: {task['id']} ({task['category']})")

        # Baseline A: Direct Ollama
        print(f"    Direct...", end="", flush=True)
        start = time.time()
        direct_response = get_ollama_response(prompt, timeout=30)
        direct_latency = (time.time() - start) * 1000
        direct_score = score_response(task, direct_response)
        direct_scores.append(direct_score["score"])
        direct_latencies.append(direct_latency)
        print(f" score={direct_score['score']:.2f} {direct_latency:.0f}ms")

        # Baseline D: Full ORBIT pipeline
        print(f"    ORBIT...", end="", flush=True)
        start = time.time()
        # Fresh session per task: tasks are independent; sharing the server's
        # "default" session grows context every turn and inflates latency.
        orbit_result = call_orbit_chat(prompt, timeout=60, session_id=f"e9-{task['id']}")
        orbit_latency = (time.time() - start) * 1000

        if "error" not in orbit_result:
            orbit_response = orbit_result.get("response", orbit_result.get("text", ""))
            orbit_score = score_response(task, orbit_response)
            orbit_scores.append(orbit_score["score"])
            orbit_latencies.append(orbit_latency)

            agent = orbit_result.get("agent", "unknown")
            routing_decisions.append({
                "task_id": task["id"],
                "category": task["category"],
                "agent": agent,
                "score": orbit_score["score"],
            })

            print(f" score={orbit_score['score']:.2f} {orbit_latency:.0f}ms agent={agent}")
        else:
            orbit_scores.append(0)
            orbit_latencies.append(orbit_latency)
            print(f" ERROR: {orbit_result['error'][:80]}")

        # Store task result
        results["task_results"].append({
            "id": task["id"],
            "category": task["category"],
            "direct": {
                "score": direct_score["score"],
                "latency_ms": round(direct_latency, 1),
                "response_preview": direct_response[:200],
            },
            "orbit": {
                "score": orbit_scores[-1],
                "latency_ms": round(orbit_latency, 1),
                "agent": routing_decisions[-1]["agent"] if routing_decisions else "unknown",
                "response_preview": orbit_response[:200] if "error" not in orbit_result else orbit_result["error"],
            },
        })

        time.sleep(0.5)

    # Calculate summary
    if direct_scores and orbit_scores:
        mean_direct = sum(direct_scores) / len(direct_scores)
        mean_orbit = sum(orbit_scores) / len(orbit_scores)
        mean_direct_lat = sum(direct_latencies) / len(direct_latencies)
        mean_orbit_lat = sum(orbit_latencies) / len(orbit_latencies)

        # Per-category breakdown
        categories = {}
        for tr in results["task_results"]:
            cat = tr["category"]
            if cat not in categories:
                categories[cat] = {"direct": [], "orbit": []}
            categories[cat]["direct"].append(tr["direct"]["score"])
            categories[cat]["orbit"].append(tr["orbit"]["score"])

        category_summary = {}
        for cat, scores in categories.items():
            d = scores["direct"]
            o = scores["orbit"]
            category_summary[cat] = {
                "direct_mean": round(sum(d) / max(1, len(d)), 3),
                "orbit_mean": round(sum(o) / max(1, len(o)), 3),
                "n": len(d),
                "delta": round(sum(o) / max(1, len(o)) - sum(d) / max(1, len(d)), 3),
            }

        # Win/loss/tie
        wins = sum(1 for d, o in zip(direct_scores, orbit_scores) if o > d + 0.1)
        losses = sum(1 for d, o in zip(direct_scores, orbit_scores) if o < d - 0.1)
        ties = len(direct_scores) - wins - losses

        results["summary"] = {
            "direct_mean_score": round(mean_direct, 3),
            "orbit_mean_score": round(mean_orbit, 3),
            "delta_absolute": round(mean_orbit - mean_direct, 3),
            "delta_relative_pct": round((mean_orbit - mean_direct) / max(0.001, mean_direct) * 100, 1),
            "direct_mean_latency_ms": round(mean_direct_lat, 1),
            "orbit_mean_latency_ms": round(mean_orbit_lat, 1),
            "latency_overhead_ms": round(mean_orbit_lat - mean_direct_lat, 1),
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "win_rate": round(wins / max(1, wins + losses + ties) * 100, 1),
            "category_breakdown": category_summary,
            "routing_accuracy": {
                "total": len(routing_decisions),
                "by_category": {},
            },
        }

        # Routing accuracy per category
        for rd in routing_decisions:
            cat = rd["category"]
            if cat not in results["summary"]["routing_accuracy"]["by_category"]:
                results["summary"]["routing_accuracy"]["by_category"][cat] = []
            results["summary"]["routing_accuracy"]["by_category"][cat].append(rd["agent"])

        # Most commonly routed agents
        agent_counts = {}
        for rd in routing_decisions:
            agent = rd["agent"]
            agent_counts[agent] = agent_counts.get(agent, 0) + 1
        results["summary"]["routing_decisions"] = dict(sorted(agent_counts.items(), key=lambda x: -x[1]))

    return results


if __name__ == "__main__":
    result = run_experiment("Full Pipeline Value", run_full_pipeline_experiment)
    if "summary" in result:
        s = result["summary"]
        print(f"\n{'='*60}")
        print(f"RESULTS SUMMARY")
        print(f"{'='*60}")
        print(f"Direct model mean score:  {s.get('direct_mean_score', 'N/A')}")
        print(f"ORBIT pipeline mean score: {s.get('orbit_mean_score', 'N/A')}")
        print(f"Delta:                    {s.get('delta_absolute', 'N/A')} ({s.get('delta_relative_pct', 'N/A')}%)")
        print(f"Direct latency:           {s.get('direct_mean_latency_ms', 'N/A')}ms")
        print(f"ORBIT latency:            {s.get('orbit_mean_latency_ms', 'N/A')}ms")
        print(f"Wins/Losses/Ties:         {s.get('wins', '?')}/{s.get('losses', '?')}/{s.get('ties', '?')}")
        print(f"Win rate:                 {s.get('win_rate', 'N/A')}%")
