import sys, os, json, time
sys.path.insert(0, r"D:\JARVES\validation\scripts")
from experiment_base import call_orbit_chat, get_ollama_response, RESULTS_DIR

tasks = [
    ("What is 2+2?", "4", "math"),
    ("Capital of France?", "paris", "facts"),
    ("Red planet?", "mars", "facts"),
    ("Who wrote Hamlet?", "shakespeare", "facts"),
    ("Square root of 16?", "4", "math"),
    ("Largest ocean?", "pacific", "geography"),
    ("What is H2O?", "water", "science"),
    ("Speed of light?", "299792458", "science"),
    ("How many continents?", "7", "general"),
    ("What color is snow?", "white", "general"),
]

def score(r, e):
    if not r: return 0.0
    return 1.0 if e.lower() in r.lower() else 0.0

direct_scores, orbit_scores = [], []
direct_lat, orbit_lat = [], []
all_results = []

for i, (q, a, cat) in enumerate(tasks):
    t0 = time.time()
    d = get_ollama_response(q, timeout=30)
    dt = time.time() - t0
    ds = score(d, a)
    direct_scores.append(ds)
    direct_lat.append(dt)

    t0 = time.time()
    o = call_orbit_chat(q, timeout=60)
    ot = time.time() - t0
    ot2 = o.get("response", "")
    oss = score(ot2, a)
    orbit_scores.append(oss)
    orbit_lat.append(ot)

    all_results.append({"q": q, "expected": a, "cat": cat,
        "direct_score": ds, "direct_latency": round(dt, 1),
        "orbit_score": oss, "orbit_latency": round(ot, 1),
        "direct_text": d[:200], "orbit_text": ot2[:200]})

    with open(RESULTS_DIR / "quick_validation_v2.json", "w") as f:
        json.dump({"tasks": all_results, "summary": {
            "total": len(tasks),
            "direct_score": sum(direct_scores)/len(direct_scores),
            "orbit_score": sum(orbit_scores)/len(orbit_scores),
            "direct_latency": sum(direct_lat)/len(direct_lat),
            "orbit_latency": sum(orbit_lat)/len(orbit_lat),
        }}, f, indent=2)

    print(f"[{i+1}/10] D={ds:.0f}({dt:.0f}s) O={oss:.0f}({ot:.0f}s) {cat}")

print("DONE")
