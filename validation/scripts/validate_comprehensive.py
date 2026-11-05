import sys
import os
import time
import json
import threading
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "validation", "scripts"))
from experiment_base import (
    check_orbit_running, get_ollama_response, call_orbit_chat,
    score_response, load_dataset, RESULTS_DIR
)

print("=" * 70)
print("ORBIT VALIDATION - COMPREHENSIVE")
print("=" * 70)
print(f"ORBIT running: {check_orbit_running()}")
print()

results = {}

# === 1. Knowledge (5 tasks) ===
print("--- 1. Knowledge (5 tasks) ---")
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
results["Knowledge"] = {"direct": round(sum(direct_scores)/5, 3), "orbit": round(sum(orbit_scores)/5, 3)}
print(f"  Direct: {results['Knowledge']['direct']}  ORBIT: {results['Knowledge']['orbit']}")

# === 2. Reasoning (5 tasks) ===
print("\n--- 2. Reasoning (5 tasks) ---")
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
results["Reasoning"] = {"direct": round(sum(direct_scores)/5, 3), "orbit": round(sum(orbit_scores)/5, 3)}
print(f"  Direct: {results['Reasoning']['direct']}  ORBIT: {results['Reasoning']['orbit']}")

# === 3. Tool Use (3 tasks) ===
print("\n--- 3. Tool Use (3 tasks) ---")
tool_tests = [
    "Create a file called orbit_data/val_test.txt with content Hello",
    "List the files in the orbit directory",
    "What is my system information?",
]
tool_passed = 0
for t in tool_tests:
    r = call_orbit_chat(t, timeout=60)
    if "error" not in r and len(r.get("response", r.get("text", "")).strip()) > 5:
        tool_passed += 1
results["Tools"] = {"passed": tool_passed, "total": 3}
print(f"  Passed: {tool_passed}/3")

# === 4. Memory (2 tasks) ===
print("\n--- 4. Memory (2 tasks) ---")
setup = [
    {"role": "user", "content": "My cat's name is Whiskers and she is 3 years old."},
    {"role": "assistant", "content": "Got it! Whiskers is your 3-year-old cat."},
    {"role": "user", "content": "I work at Google and live in Seattle."},
    {"role": "assistant", "content": "Google in Seattle, nice!"},
]
memory_passed = 0
for q, expected in [("What is my cat's name?", ["whiskers"]), ("Where do I work?", ["google"])]:
    full = "\n".join(f"{t['role']}: {t['content']}" for t in setup) + f"\nuser: {q}"
    r = call_orbit_chat(full, timeout=60)
    if "error" not in r:
        resp = r.get("response", r.get("text", "")).lower().replace("**", "")
        if any(kw in resp for kw in expected):
            memory_passed += 1
results["Memory"] = {"passed": memory_passed, "total": 2}
print(f"  Passed: {memory_passed}/2")

# === 5. Concurrency (5 threads) ===
print("\n--- 5. Concurrency (5 threads) ---")
concurrent_results = {"success": 0, "failed": 0}
lock = threading.Lock()

def worker(idx):
    r = call_orbit_chat(f"Test concurrent {idx}", timeout=60)
    with lock:
        if "error" not in r:
            concurrent_results["success"] += 1
        else:
            concurrent_results["failed"] += 1

threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=120)
results["Concurrency"] = concurrent_results
print(f"  Success: {concurrent_results['success']}/5  Failed: {concurrent_results['failed']}/5")

# === 6. Error Recovery (3 tests) ===
print("\n--- 6. Error Recovery (3 tests) ---")
error_tests = [
    ("empty_message", lambda: call_orbit_chat("", timeout=10)),
    ("special_chars", lambda: call_orbit_chat("!@#$%^&*()", timeout=10)),
    ("injection", lambda: call_orbit_chat("'; DROP TABLE users; --", timeout=10)),
]
recovered = 0
for name, test_fn in error_tests:
    try:
        r = test_fn()
        recovered += 1
    except:
        pass
results["ErrorRecovery"] = {"recovered": recovered, "total": 3}
print(f"  Recovered: {recovered}/3")

# Save results
output = RESULTS_DIR / "comprehensive_results.json"
with open(output, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Summary
print("\n" + "=" * 70)
print("FINAL RESULTS")
print("=" * 70)

# Calculate overall
all_direct = [results["Knowledge"]["direct"], results["Reasoning"]["direct"]]
all_orbit = [results["Knowledge"]["orbit"], results["Reasoning"]["orbit"]]
avg_direct = sum(all_direct) / len(all_direct)
avg_orbit = sum(all_orbit) / len(all_orbit)

print(f"  Knowledge:   Direct={results['Knowledge']['direct']:.3f}  ORBIT={results['Knowledge']['orbit']:.3f}")
print(f"  Reasoning:   Direct={results['Reasoning']['direct']:.3f}  ORBIT={results['Reasoning']['orbit']:.3f}")
print(f"  Tools:       {results['Tools']['passed']}/{results['Tools']['total']} passed")
print(f"  Memory:      {results['Memory']['passed']}/{results['Memory']['total']} passed")
print(f"  Concurrency: {results['Concurrency']['success']}/{results['Concurrency']['success']+results['Concurrency']['failed']} success")
print(f"  Error Recovery: {results['ErrorRecovery']['recovered']}/{results['ErrorRecovery']['total']} recovered")
print()
print(f"  Average (Knowledge+Reasoning):")
print(f"    Direct: {avg_direct:.3f}")
print(f"    ORBIT:  {avg_orbit:.3f}")
print(f"    Delta:  {avg_orbit - avg_direct:+.3f} ({((avg_orbit - avg_direct) / max(0.001, avg_direct) * 100):+.1f}%)")
print()
print(f"Saved: {output}")
