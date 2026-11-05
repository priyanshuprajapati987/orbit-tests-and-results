import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    check_orbit_running, get_ollama_response, call_orbit_chat,
    score_response, load_dataset, RESULTS_DIR
)

print("=" * 70)
print("ORBIT MINI VALIDATION")
print("=" * 70)
print(f"ORBIT running: {check_orbit_running()}")
print()

results = {}

# === Quick Test: Basic Pipeline ===
print("--- Test 1: Basic Pipeline (3 tasks) ---")
tasks = load_dataset(split="dev")[:3]
direct_scores, orbit_scores = [], []
for t in tasks:
    d = get_ollama_response(t["prompt"], timeout=30)
    ds = score_response(t, d)
    direct_scores.append(ds["score"])
    r = call_orbit_chat(t["prompt"], timeout=60)
    if "error" not in r:
        oscore = score_response(t, r.get("response", r.get("text", "")))
        orbit_scores.append(oscore["score"])
    else:
        orbit_scores.append(0)
results["Pipeline"] = {
    "direct_mean": round(sum(direct_scores)/len(direct_scores), 3),
    "orbit_mean": round(sum(orbit_scores)/len(orbit_scores), 3),
    "n": len(tasks)
}
print(f"  Direct: {results['Pipeline']['direct_mean']:.3f}  ORBIT: {results['Pipeline']['orbit_mean']:.3f}")

# === Quick Test: Tool Use ===
print("\n--- Test 2: Tool Use (3 tasks) ---")
tool_tests = [
    "Create a file called orbit_data/val_test.txt with content Hello",
    "List the files in the orbit directory",
    "What is the system information?",
]
tool_passed = 0
for t in tool_tests:
    r = call_orbit_chat(t, timeout=60)
    if "error" not in r and len(r.get("response", r.get("text", "")).strip()) > 5:
        tool_passed += 1
results["Tools"] = {"passed": tool_passed, "total": len(tool_tests)}
print(f"  Passed: {tool_passed}/{len(tool_tests)}")

# Save
output = RESULTS_DIR / "mini_results.json"
with open(output, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 70)
print("RESULTS")
print("=" * 70)
for name, data in results.items():
    print(f"  {name}: {json.dumps(data)}")
print(f"\nSaved: {output}")
