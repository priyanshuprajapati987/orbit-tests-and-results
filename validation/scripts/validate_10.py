import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "validation", "scripts"))
from experiment_base import (
    check_orbit_running, get_ollama_response, call_orbit_chat,
    score_response, load_dataset, RESULTS_DIR
)

print("=" * 70)
print("ORBIT VALIDATION - 10 TASKS")
print("=" * 70)
print(f"ORBIT running: {check_orbit_running()}")
print()

results = {}

# === Test 1: Knowledge (5 tasks) ===
print("--- Test 1: Knowledge (5 tasks) ---")
tasks = load_dataset(category="general_knowledge", split="dev")[:5]
direct_scores, orbit_scores = [], []
for t in tasks:
    d = get_ollama_response(t["prompt"], timeout=60)
    ds = score_response(t, d)
    direct_scores.append(ds["score"])
    r = call_orbit_chat(t["prompt"], timeout=60)
    if "error" not in r:
        oscore = score_response(t, r.get("response", r.get("text", "")))
        orbit_scores.append(oscore["score"])
    else:
        orbit_scores.append(0)
results["Knowledge"] = {
    "direct_mean": round(sum(direct_scores)/len(direct_scores), 3),
    "orbit_mean": round(sum(orbit_scores)/len(orbit_scores), 3),
    "n": len(tasks)
}
print(f"  Direct: {results['Knowledge']['direct_mean']:.3f}  ORBIT: {results['Knowledge']['orbit_mean']:.3f}")

# === Test 2: Reasoning (5 tasks) ===
print("\n--- Test 2: Reasoning (5 tasks) ---")
tasks = load_dataset(category="reasoning", split="dev")[:5]
direct_scores, orbit_scores = [], []
for t in tasks:
    d = get_ollama_response(t["prompt"], timeout=60)
    ds = score_response(t, d)
    direct_scores.append(ds["score"])
    r = call_orbit_chat(t["prompt"], timeout=60)
    if "error" not in r:
        oscore = score_response(t, r.get("response", r.get("text", "")))
        orbit_scores.append(oscore["score"])
    else:
        orbit_scores.append(0)
results["Reasoning"] = {
    "direct_mean": round(sum(direct_scores)/len(direct_scores), 3),
    "orbit_mean": round(sum(orbit_scores)/len(orbit_scores), 3),
    "n": len(tasks)
}
print(f"  Direct: {results['Reasoning']['direct_mean']:.3f}  ORBIT: {results['Reasoning']['orbit_mean']:.3f}")

# Save
output = RESULTS_DIR / "validation_10tasks.json"
with open(output, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 70)
print("RESULTS SUMMARY")
print("=" * 70)
for name, data in results.items():
    delta = data["orbit_mean"] - data["direct_mean"]
    print(f"  {name}: Direct={data['direct_mean']:.3f}  ORBIT={data['orbit_mean']:.3f}  Delta={delta:+.3f}")
print(f"\nSaved: {output}")
