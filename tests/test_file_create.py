import os
import sys

import requests

__test__ = False  # Standalone script â€” not a pytest test

sys.path.insert(0, r"D:\JARVES\orbit")

API_KEY = os.environ.get("ORBIT_API_KEY", "")
H = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

tests = [
    "Create a file called orbit_data/test1.txt with hello world",
    "Create orbit_data/test2.txt containing test content",
    "Write orbit_data/test3.txt with some data here",
    "Make a file called orbit_data/test4.txt with python code",
]

for msg in tests:
    r = requests.post(
        "http://127.0.0.1:5000/api/chat", headers=H, json={"message": msg}, timeout=60
    )
    resp = r.json()
    print(f"Message: {msg[:55]}")
    print(f"  Response: {resp.get('response', '')[:100]}")
    print(f"  Agent: {resp.get('agent')}")

# Check files
print("\n--- File Check ---")
for i in range(1, 5):
    path = f"D:/JARVES/orbit_data/test{i}.txt"
    exists = os.path.exists(path)
    if exists:
        content = open(path).read()
        print(f"test{i}.txt: EXISTS - content: {content[:50]}")
    else:
        print(f"test{i}.txt: MISSING")
