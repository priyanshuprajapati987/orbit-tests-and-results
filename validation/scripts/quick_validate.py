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
print("ORBIT QUICK VALIDATION (5 tasks per experiment)")
print("=" * 70)
print(f"ORBIT running: {check_orbit_running()}")
print()

results = {}

# === Experiment 1: SmartRouter ===
print("--- Experiment 1: SmartRouter Value ---")
tasks = load_dataset(split="dev")[:5]
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
results["SmartRouter"] = {
    "direct_mean": round(sum(direct_scores)/len(direct_scores), 3),
    "orbit_mean": round(sum(orbit_scores)/len(orbit_scores), 3),
    "n": len(tasks)
}
print(f"  Direct: {results['SmartRouter']['direct_mean']:.3f}  ORBIT: {results['SmartRouter']['orbit_mean']:.3f}")

# === Experiment 2: Multi-Agent ===
print("\n--- Experiment 2: Multi-Agent Value ---")
prompts = [
    "Research Python web frameworks and recommend one for a REST API",
    "Write a function to find the longest palindromic substring",
    "Analyze pros and cons of PostgreSQL vs MongoDB",
    "Create a deployment plan for Flask with Docker",
    "Explain the difference between SQL and NoSQL databases"
]
direct_scores, orbit_scores = [], []
for p in prompts:
    d = get_ollama_response(p, timeout=30)
    direct_scores.append(0.7 if len(d.split()) > 20 else 0.3)
    r = call_orbit_chat(p, timeout=60)
    orbit_scores.append(0.7 if "error" not in r and len(r.get("response", r.get("text", "")).split()) > 20 else 0.3)
results["Multi-Agent"] = {
    "direct_mean": round(sum(direct_scores)/len(direct_scores), 3),
    "orbit_mean": round(sum(orbit_scores)/len(orbit_scores), 3),
    "n": len(prompts)
}
print(f"  Direct: {results['Multi-Agent']['direct_mean']:.3f}  ORBIT: {results['Multi-Agent']['orbit_mean']:.3f}")

# === Experiment 3: Memory ===
print("\n--- Experiment 3: Memory Effectiveness ---")
setup = [
    {"role": "user", "content": "My cat's name is Whiskers and she is 3 years old."},
    {"role": "assistant", "content": "Got it! Whiskers is your 3-year-old cat."},
    {"role": "user", "content": "I work at Google and live in Seattle."},
    {"role": "assistant", "content": "Google in Seattle, nice!"},
]
passed = 0
for q, expected in [("What is my cat's name?", ["whiskers"]), ("Where do I work?", ["google"])]:
    full = "\n".join(f"{t['role']}: {t['content']}" for t in setup) + f"\nuser: {q}"
    r = call_orbit_chat(full, timeout=60)
    if "error" not in r:
        resp = r.get("response", r.get("text", "")).lower()
        if any(kw in resp for kw in expected):
            passed += 1
results["Memory"] = {"pass_rate": round(passed/2*100, 1), "n": 2}
print(f"  Pass rate: {results['Memory']['pass_rate']}%")

# === Experiment 4: Learning ===
print("\n--- Experiment 4: Learning Effectiveness ---")
setup = [
    {"role": "user", "content": "I prefer short, direct answers. No explanations unless asked."},
    {"role": "assistant", "content": "Got it! Short and direct."},
]
full = "\n".join(f"{t['role']}: {t['content']}" for t in setup) + "\nuser: What is the capital of France?"
r = call_orbit_chat(full, timeout=60)
if "error" not in r:
    resp = r.get("response", r.get("text", ""))
    results["Learning"] = {"response_length": len(resp.split()), "preference_followed": len(resp.split()) < 15}
    print(f"  Response length: {results['Learning']['response_length']} words (preference: short)")
else:
    results["Learning"] = {"error": r["error"][:80]}
    print(f"  ERROR: {r['error'][:80]}")

# === Experiment 5: Error Recovery ===
print("\n--- Experiment 5: Error Recovery ---")
error_tests = [
    ("empty_message", lambda: call_orbit_chat("", timeout=10)),
    ("special_chars", lambda: call_orbit_chat("!@#$%^&*()", timeout=10)),
    ("nonexistent_endpoint", lambda: __import__("requests").get("http://127.0.0.1:5000/api/nonexistent", timeout=5).json()),
]
recovered = 0
for name, test_fn in error_tests:
    try:
        r = test_fn()
        recovered += 1
    except:
        pass
results["ErrorRecovery"] = {"recovered": recovered, "total": len(error_tests), "rate": round(recovered/len(error_tests)*100, 1)}
print(f"  Recovery rate: {results['ErrorRecovery']['rate']}%")

# === Experiment 6: Tool Reality ===
print("\n--- Experiment 6: Tool Reality Test ---")
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
results["ToolReality"] = {"passed": tool_passed, "total": len(tool_tests), "rate": round(tool_passed/len(tool_tests)*100, 1)}
print(f"  Success rate: {results['ToolReality']['rate']}%")

# === Experiment 7: Concurrency ===
print("\n--- Experiment 7: Concurrency Stress Test ---")
import threading
concurrent_results = {"success": 0, "failed": 0}
lock = threading.Lock()
def worker(idx):
    r = call_orbit_chat(f"Test {idx}", timeout=60)
    with lock:
        if "error" not in r:
            concurrent_results["success"] += 1
        else:
            concurrent_results["failed"] += 1
threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
for t in threads: t.start()
for t in threads: t.join(timeout=120)
results["Concurrency"] = concurrent_results
results["Concurrency"]["rate"] = round(concurrent_results["success"]/(concurrent_results["success"]+concurrent_results["failed"])*100, 1) if (concurrent_results["success"]+concurrent_results["failed"]) > 0 else 0
print(f"  Success: {concurrent_results['success']}/5  Rate: {results['Concurrency']['rate']}%")

# === Experiment 8: Quality Gate ===
print("\n--- Experiment 8: Quality Gate ---")
qg_prompts = ["What is 2+2?", "Explain quantum computing", "Write a haiku about AI"]
qg_results = {"direct": [], "orbit": []}
for p in qg_prompts:
    d = get_ollama_response(p, timeout=30)
    qg_results["direct"].append(len(d.split()))
    r = call_orbit_chat(p, timeout=60)
    if "error" not in r:
        qg_results["orbit"].append(len(r.get("response", r.get("text", "")).split()))
results["QualityGate"] = {
    "direct_avg_words": round(sum(qg_results["direct"])/len(qg_results["direct"]), 1),
    "orbit_avg_words": round(sum(qg_results["orbit"])/len(qg_results["orbit"]), 1),
}
print(f"  Direct avg words: {results['QualityGate']['direct_avg_words']}  ORBIT: {results['QualityGate']['orbit_avg_words']}")

# === Experiment 9: Full Pipeline ===
print("\n--- Experiment 9: Full Pipeline Value ---")
tasks = load_dataset(split="dev")[:5]
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
results["FullPipeline"] = {
    "direct_mean": round(sum(direct_scores)/len(direct_scores), 3),
    "orbit_mean": round(sum(orbit_scores)/len(orbit_scores), 3),
    "delta": round(sum(orbit_scores)/len(orbit_scores) - sum(direct_scores)/len(direct_scores), 3),
}
print(f"  Direct: {results['FullPipeline']['direct_mean']:.3f}  ORBIT: {results['FullPipeline']['orbit_mean']:.3f}  Delta: {results['FullPipeline']['delta']:+.3f}")

# === Experiment 10: Real-World ===
print("\n--- Experiment 10: Real-World Task Suite ---")
rw_prompts = [
    "Create a project structure with src/, tests/, docs/, and setup.py",
    "Write a Python Stack class with push, pop, peek, is_empty",
    "My script gives TypeError: unsupported operand for +: int and str. Fix it",
    "Compare PostgreSQL and MongoDB for social media",
    "What OS am I using and how much RAM?",
]
rw_passed = 0
for p in rw_prompts:
    r = call_orbit_chat(p, timeout=60)
    if "error" not in r and len(r.get("response", r.get("text", "")).strip()) > 20:
        rw_passed += 1
results["RealWorld"] = {"passed": rw_passed, "total": len(rw_prompts), "rate": round(rw_passed/len(rw_prompts)*100, 1)}
print(f"  Success rate: {results['RealWorld']['rate']}%")

# Save results
output = RESULTS_DIR / "quick_results.json"
with open(output, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 70)
print("QUICK VALIDATION RESULTS")
print("=" * 70)
for name, data in results.items():
    print(f"  {name}: {json.dumps(data)}")
print(f"\nSaved: {output}")
