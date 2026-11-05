import os

import requests

__test__ = False  # Standalone script â€” not a pytest test

API_KEY = os.environ.get("ORBIT_API_KEY", "")
H = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Test with quoted path (original working format)
msg = "write file 'orbit_data/test_simple.txt' with 'hello world'"
print(f"Message: {msg}")
r = requests.post(
    "http://127.0.0.1:5000/api/chat", headers=H, json={"message": msg}, timeout=60
)
resp = r.json()
print(f"Response: {resp.get('response', '')[:200]}")
print(f"Agent: {resp.get('agent')}")
print(f"Tools: {resp.get('tools_used')}")

exists = os.path.exists("D:/JARVES/orbit_data/test_simple.txt")
print(f"File exists: {exists}")
if exists:
    print(f"Content: {open('D:/JARVES/orbit_data/test_simple.txt').read()}")
