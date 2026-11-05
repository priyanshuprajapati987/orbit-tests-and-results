"""
Run All Validation Experiments

Main runner script that executes all experiments and produces
a comprehensive validation report.
"""

import json
import sys
import time
import importlib
from pathlib import Path
from datetime import datetime

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent))

from experiment_base import RESULTS_DIR, check_orbit_running


# Map module_name -> (display_name, function_name)
EXPERIMENTS = [
    ("experiment_1_smartrouter", "SmartRouter Value", "run_smartrouter_experiment"),
    ("experiment_2_multi_agent", "Queen / Multi-Agent Value", "run_multi_agent_experiment"),
    ("experiment_3_memory", "Memory Effectiveness", "run_memory_experiment"),
    ("experiment_4_learning", "Learning Effectiveness", "run_learning_experiment"),
    ("experiment_5_error_recovery", "Error Recovery", "run_error_recovery_experiment"),
    ("experiment_6_tool_reality", "Tool Reality Test", "run_tool_reality_experiment"),
    ("experiment_7_concurrency", "Concurrency Stress Test", "run_concurrency_experiment"),
    ("experiment_8_quality_gate", "Quality Gate", "run_quality_gate_experiment"),
    ("experiment_9_full_pipeline", "Full Pipeline Value", "run_full_pipeline_experiment"),
    ("experiment_10_real_world", "Real-World Task Suite", "run_real_world_experiment"),
]


def run_all_experiments(skip_list=None):
    """Run all validation experiments."""
    skip_list = skip_list or []

    print(f"{'='*70}")
    print(f"ORBIT VALIDATION FRAMEWORK")
    print(f"{'='*70}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"ORBIT running: {check_orbit_running()}")
    print(f"Experiments: {len(EXPERIMENTS)}")
    print(f"Skipping: {skip_list or 'none'}")
    print()

    all_results = {}

    for module_name, exp_name, func_name in EXPERIMENTS:
        if exp_name in skip_list:
            print(f"\n--- Skipping: {exp_name} ---\n")
            continue

        print(f"\n{'='*70}")
        print(f"EXPERIMENT: {exp_name}")
        print(f"{'='*70}")

        try:
            start = time.time()
            mod = importlib.import_module(module_name)
            run_func = getattr(mod, func_name)
            result = mod.run_experiment(exp_name, run_func)
            elapsed = time.time() - start

            result["elapsed_seconds"] = round(elapsed, 1)
            all_results[exp_name] = result
            print(f"\n  Completed in {elapsed:.1f}s")

        except Exception as e:
            print(f"\n  FAILED: {e}")
            import traceback
            traceback.print_exc()
            all_results[exp_name] = {"error": str(e), "status": "failed"}

        print()

    # Save combined results
    output_file = RESULTS_DIR / "all_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*70}")
    print(f"ALL EXPERIMENTS COMPLETE")
    print(f"{'='*70}")
    print(f"Results saved: {output_file}")
    print(f"Completed: {datetime.now().isoformat()}")

    # Print summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    for name, result in all_results.items():
        if "error" in result:
            print(f"  {name}: FAILED - {result['error'][:80]}")
        else:
            summary = result.get("summary", {})
            score = summary.get("orbit_mean_score", summary.get("pass_rate", summary.get("success_rate", "?")))
            print(f"  {name}: {score}")

    return all_results


if __name__ == "__main__":
    # Parse skip list from args
    skip = []
    if len(sys.argv) > 1:
        skip = sys.argv[1:]

    results = run_all_experiments(skip_list=skip)
