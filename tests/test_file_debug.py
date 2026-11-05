import os
import time

import requests

__test__ = False  # Standalone script â€” not a pytest test

API_KEY = os.environ.get("ORBIT_API_KEY", "")
H = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Test each message one at a time with delay
tests = [
    "Create a file called orbit_data/test_debug1.txt with hello world",
    "Create orbit_data/test_debug2.txt containing test content",
    "Write orbit_data/test_debug3.txt with some data here",
    "Make a file called orbit_data/test_debug4.txt with python code",
]

for i, msg in enumerate(tests):
    print(f"=== Test {i + 1}: {msg[:60]} ===")
    try:
        r = requests.post(
            "http://127.0.0.1:5000/api/chat",
            headers=H,
            json={"message": msg},
            timeout=120,
        )
        resp = r.json()
        print(f"  Response: {str(resp.get('response', ''))[:150]}")
        print(f"  Agent: {resp.get('agent')}")
        print(f"  Tools: {resp.get('tools_used')}")
        print(f"  Model: {resp.get('model')}")
        print(f"  Latency: {resp.get('latency_ms', 0)}ms")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Check file
    fname = f"orbit_data/test_debug{i + 1}.txt"
    fpath = f"D:/JARVES/{fname}"
    exists = os.path.exists(fpath)
    if exists:
        content = open(fpath).read()
        print(f"  FILE: EXISTS - {content[:50]}")
    else:
        print("  FILE: MISSING")
    print()
    time.sleep(2)  # Wait between requests
