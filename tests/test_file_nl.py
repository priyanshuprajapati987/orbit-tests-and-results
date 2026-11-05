import os

import requests

__test__ = False  # Standalone script â€” not a pytest test

API_KEY = os.environ.get("ORBIT_API_KEY", "")
H = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

tests = [
    "Create a file called orbit_data/test_nl1.txt with hello world",
    "Create orbit_data/test_nl2.txt containing test content",
    "Write orbit_data/test_nl3.txt with some data here",
    "Make a file called orbit_data/test_nl4.txt with python code",
]

for msg in tests:
    print(f"Message: {msg[:55]}")
    try:
        r = requests.post(
            "http://127.0.0.1:5000/api/chat",
            headers=H,
            json={"message": msg},
            timeout=60,
        )
        resp = r.json()
        print(f"  Response: {str(resp.get('response', ''))[:100]}")
        print(f"  Agent: {resp.get('agent')}")
        print(f"  Tools: {resp.get('tools_used')}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()

print("--- File Check ---")
for i in range(1, 5):
    path = f"D:/JARVES/orbit_data/test_nl{i}.txt"
    exists = os.path.exists(path)
    if exists:
        content = open(path).read()
        print(f"test_nl{i}.txt: EXISTS - {content[:50]}")
    else:
        print(f"test_nl{i}.txt: MISSING")
