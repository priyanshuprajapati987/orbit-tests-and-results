import sys

sys.path.insert(0, "D:/JARVES/orbit")

# Test SmartIntelligence
from orbit.core.smart_intelligence import get_smart_intelligence

intel = get_smart_intelligence()

tests = [
    "Create a file called orbit_data/test_nl1.txt with hello world",
    "Create orbit_data/test_nl2.txt containing test content",
    "Write orbit_data/test_nl3.txt with some data here",
    "Make a file called orbit_data/test_nl4.txt with python code",
]

for msg in tests:
    analysis = intel.analyze(msg)
    ag = analysis.get("agent")
    feats = analysis.get("features", [])
    print(f"Msg: {msg[:60]}")
    print(f"  agent={ag}, features={feats[:2]}")
    print()

# Test SmartRouter
from orbit.core.smart_router import auto_route

print("--- SmartRouter ---")
for msg in tests:
    r = auto_route(msg)
    print(f"Msg: {msg[:60]}")
    print(f"  is_tool={r.is_tool_command}, agent={r.best_agent()}, intent={r.intent}")
    print()

# Test _try_tool_execution directly
print("--- _try_tool_execution ---")
from orbit.core.chat_api import _try_tool_execution

for msg in tests:
    result, tool = _try_tool_execution(msg)
    has_file = False
    import os

    for f in ["test_nl1.txt", "test_nl2.txt", "test_nl3.txt", "test_nl4.txt"]:
        if os.path.exists(f"D:/JARVES/orbit_data/{f}"):
            has_file = True
            break
    print(f"Msg: {msg[:60]}")
    result_preview = (result or "None")[:120]
    print(f"  result={result_preview}, tool={tool}, file_exists={has_file}")
    print()
