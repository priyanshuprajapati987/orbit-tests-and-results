"""
Quick Validation — 3 tasks per category, ~5 minutes total
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))

from experiment_base import call_orbit_chat, get_ollama_response, RESULTS_DIR

def score(response, expected):
    if not response or not expected:
        return 0.0
    r = response.lower().strip()
    e = expected.lower().strip()
    if e in r:
        return 1.0
    words = e.split()
    matches = sum(1 for w in words if w in r)
    return matches / len(words) if words else 0.0

TASKS = [
    {"q": "What is the capital of France?", "a": "paris", "cat": "facts"},
    {"q": "What is 2 + 2?", "a": "4", "cat": "math"},
    {"q": "What planet is known as the Red Planet?", "a": "mars", "cat": "facts"},
    {"q": "Who wrote Romeo and Juliet?", "a": "shakespeare", "cat": "facts"},
    {"q": "What is the square root of 9?", "a": "3", "cat": "math"},
    {"q": "What color is the sky on a clear day?", "a": "blue", "cat": "general"},
    {"q": "How many continents are there?", "a": "7", "cat": "general"},
    {"q": "What gas do plants absorb?", "a": "carbon dioxide", "cat": "science"},
    {"q": "What is the speed of light?", "a": "299792458", "cat": "science"},
    {"q": "Which is the largest ocean?", "a": "pacific", "cat": "geography"},
]

def safe_print(text, limit=80):
    try:
        print(text[:limit])
    except UnicodeEncodeError:
        print(text[:limit].encode("ascii", "replace").decode())

def run():
    print("=" * 60)
    print("ORBIT QUICK VALIDATION — 10 tasks")
    print("=" * 60)
    
    results = {"direct": [], "orbit": []}
    
    for i, t in enumerate(TASKS):
        print(f"\n[{i+1}/10] {t['cat']}: {t['q']}")
        
        # Direct Ollama
        t0 = time.time()
        direct = get_ollama_response(t["q"], model="qwen3:1.7b", timeout=30)
        dt = time.time() - t0
        ds = score(direct, t["a"])
        results["direct"].append({"score": ds, "latency": dt, "cat": t["cat"]})
        safe_print(f"  Direct: {ds:.2f} ({dt:.1f}s) -> {direct}")
        
        # ORBIT pipeline
        t0 = time.time()
        orbit_resp = call_orbit_chat(t["q"], timeout=60)
        ot = time.time() - t0
        orbit_text = orbit_resp.get("response", orbit_resp.get("error", ""))
        os_score = score(orbit_text, t["a"])
        agent = orbit_resp.get("agent", "?")
        results["orbit"].append({"score": os_score, "latency": ot, "agent": agent, "cat": t["cat"]})
        safe_print(f"  ORBIT:  {os_score:.2f} ({ot:.1f}s) agent={agent} -> {orbit_text}")
    
    # Summary
    avg_direct = sum(r["score"] for r in results["direct"]) / len(results["direct"])
    avg_orbit = sum(r["score"] for r in results["orbit"]) / len(results["orbit"])
    avg_dt = sum(r["latency"] for r in results["direct"]) / len(results["direct"])
    avg_ot = sum(r["latency"] for r in results["orbit"]) / len(results["orbit"])
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Direct Ollama: {avg_direct:.2f} avg score, {avg_dt:.1f}s avg latency")
    print(f"ORBIT Pipeline: {avg_orbit:.2f} avg score, {avg_ot:.1f}s avg latency")
    
    if avg_orbit > avg_direct:
        print(f"ORBIT WINS by {(avg_orbit - avg_direct)*100:.1f}% accuracy")
    elif avg_direct > avg_orbit:
        print(f"Direct WINS by {(avg_direct - avg_orbit)*100:.1f}% accuracy")
    else:
        print("TIE")
    
    if avg_ot > 0 and avg_dt > 0:
        print(f"Latency overhead: {avg_ot/avg_dt:.1f}x (ORBIT vs Direct)")
    
    # Save
    out = RESULTS_DIR / "quick_validation.json"
    with open(out, "w") as f:
        json.dump({"results": results, "summary": {
            "direct_score": avg_direct, "orbit_score": avg_orbit,
            "direct_latency": avg_dt, "orbit_latency": avg_ot
        }}, f, indent=2)
    print(f"\nSaved: {out}")

if __name__ == "__main__":
    run()
