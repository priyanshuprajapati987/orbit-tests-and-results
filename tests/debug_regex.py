import re
import sys

sys.path.insert(0, "D:/JARVES/orbit")

# Exact regex from task_agents.py line 103-106
pattern = (
    r"(?:create|write|make)\s+(?:a\s+)?(?:file\s+)?(?:called\s+|named\s+)?"
    r"[`\"']?([^\s`\"']+)[`\"']?\s+(?:with|containing)\s+[`\"']?(.+?)[`\"']?\s*$"
)

tests = [
    "Create a file called orbit_data/test_debug1.txt with hello world",
    "Create orbit_data/test_debug2.txt containing test content",
    "Write orbit_data/test_debug3.txt with some data here",
    "Make a file called orbit_data/test_debug4.txt with python code",
]

for msg in tests:
    m = re.search(pattern, msg, re.IGNORECASE)
    if m:
        print(f"OK: {msg[:50]}... -> path={m.group(1)}, content={m.group(2)}")
    else:
        print(f"FAIL: {msg[:50]}... -> NO MATCH")

# Now test what the server actually does
print("\n--- Testing _execute_via_agent in-process ---")
from orbit.core.chat_api import _execute_via_agent

for msg in tests:
    result = _execute_via_agent("TAS", msg, "file")
    print(f"Result: {msg[:50]}... -> {str(result)[:80] if result else 'None'}")

# Test via HTTP with raw request to debug
print("\n--- Testing what chat_api._try_tool_execution returns ---")
from orbit.core.chat_api import _try_tool_execution

for msg in tests:
    result, tool = _try_tool_execution(msg)
    print(
        f"Tool result: {msg[:50]}... -> tool={tool}, result={str(result)[:80] if result else 'None'}"
    )
