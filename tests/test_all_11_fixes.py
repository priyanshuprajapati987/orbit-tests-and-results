"""
Regression tests for all 11 fixed patterns.
Tests ROUTE + TOOL EXECUTION + REAL SIDE EFFECTS.
Requires running ORBIT server on localhost:5000.
"""

__test__ = False  # Standalone script â€” not a pytest test

import os

import requests

API_KEY = os.environ.get("ORBIT_API_KEY", "")
H = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
BASE = "http://127.0.0.1:5000"
TEST_DIR = "D:/JARVES/orbit_data/_test_regression"

passed = 0
failed = 0
results = []


def chat(msg):
    r = requests.post(f"{BASE}/api/chat", headers=H, json={"message": msg}, timeout=60)
    return r.json()


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        results.append(f"  PASS  {name}")
    else:
        failed += 1
        results.append(f"  FAIL  {name} â€” {detail}")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 1. CREATE FILE â€” natural language patterns
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("=== 1. CREATE FILE (4 NL patterns) ===")

# Pattern A: "Create a file called X with Y"
f1 = f"{TEST_DIR}/create_a.txt"
resp = chat(f"Create a file called {f1} with hello world")
check(
    "create_a route",
    resp.get("agent") == "TAS" and "file" in resp.get("tools_used", []),
)
check("create_a side effect", os.path.exists(f1), f"file missing: {f1}")
if os.path.exists(f1):
    check("create_a content", open(f1).read() == "hello world")

# Pattern B: "Create X containing Y"
f2 = f"{TEST_DIR}/create_b.txt"
resp = chat(f"Create {f2} containing test content here")
check(
    "create_b route",
    resp.get("agent") == "TAS" and "file" in resp.get("tools_used", []),
)
check("create_b side effect", os.path.exists(f2))
if os.path.exists(f2):
    check("create_b content", open(f2).read() == "test content here")

# Pattern C: "Write X with Y"
f3 = f"{TEST_DIR}/create_c.txt"
resp = chat(f"Write {f3} with some data here")
check(
    "create_c route",
    resp.get("agent") == "TAS" and "file" in resp.get("tools_used", []),
)
check("create_c side effect", os.path.exists(f3))
if os.path.exists(f3):
    check("create_c content", open(f3).read() == "some data here")

# Pattern D: "Make a file called X with Y"
f4 = f"{TEST_DIR}/create_d.txt"
resp = chat(f"Make a file called {f4} with python code")
check(
    "create_d route",
    resp.get("agent") == "TAS" and "file" in resp.get("tools_used", []),
)
check("create_d side effect", os.path.exists(f4))
if os.path.exists(f4):
    check("create_d content", open(f4).read() == "python code")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 2. MOVE FILE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 2. MOVE FILE ===")
f_src = f"{TEST_DIR}/move_src.txt"
f_dst = f"{TEST_DIR}/move_dst.txt"
# Create source file first
with open(f_src, "w") as f:
    f.write("move me")
resp = chat(f"Move {f_src} to {f_dst}")
check("move route", resp.get("agent") == "TAS" and "file" in resp.get("tools_used", []))
# ToolGate may block move in strict mode â€” check either success OR policy block
resp_text = resp.get("response", "")
move_worked = os.path.exists(f_dst) and not os.path.exists(f_src)
move_blocked = (
    "Access denied" in resp_text
    or "strict_mode" in resp_text
    or "approval" in resp_text
)
check(
    "move executed or blocked by policy",
    move_worked or move_blocked,
    f"src_exists={os.path.exists(f_src)}, dst_exists={os.path.exists(f_dst)}, resp={resp_text[:100]}",
)
if move_worked and os.path.exists(f_dst):
    check("move content preserved", open(f_dst).read() == "move me")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 3. RENAME FILE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 3. RENAME FILE ===")
f_old = f"{TEST_DIR}/rename_old.txt"
f_new = f"{TEST_DIR}/rename_new.txt"
with open(f_old, "w") as f:
    f.write("rename me")
resp = chat(f"Rename {f_old} to {f_new}")
check(
    "rename route", resp.get("agent") == "TAS" and "file" in resp.get("tools_used", [])
)
resp_text = resp.get("response", "")
rename_worked = os.path.exists(f_new) and not os.path.exists(f_old)
rename_blocked = (
    "Access denied" in resp_text
    or "strict_mode" in resp_text
    or "approval" in resp_text
)
check(
    "rename executed or blocked by policy",
    rename_worked or rename_blocked,
    f"old_exists={os.path.exists(f_old)}, new_exists={os.path.exists(f_new)}, resp={resp_text[:100]}",
)
if rename_worked and os.path.exists(f_new):
    check("rename content", open(f_new).read() == "rename me")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 4. COPY FILE (unquoted)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 4. COPY FILE (unquoted) ===")
f_csrc = f"{TEST_DIR}/copy_src.txt"
f_cdst = f"{TEST_DIR}/copy_dst.txt"
with open(f_csrc, "w") as f:
    f.write("copy me")
resp = chat(f"Copy file {f_csrc} to {f_cdst}")
check("copy route", resp.get("agent") == "TAS" and "file" in resp.get("tools_used", []))
check("copy src exists", os.path.exists(f_csrc))
check("copy dst exists", os.path.exists(f_cdst))
if os.path.exists(f_cdst):
    check("copy content", open(f_cdst).read() == "copy me")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 5. DELETE FILE (with confirmation)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 5. DELETE FILE (confirmation) ===")
f_del = f"{TEST_DIR}/delete_me.txt"
with open(f_del, "w") as f:
    f.write("delete me")
resp = chat(f"Delete file {f_del}")
resp_text = resp.get("response", "")
# Should return confirmation prompt, NOT actually delete
check(
    "delete asks confirmation",
    "CONFIRM_DELETE" in resp_text
    or "confirm" in resp_text.lower()
    or "delete" in resp_text.lower(),
    f"response: {resp_text[:100]}",
)
check(
    "delete file still exists",
    os.path.exists(f_del),
    "file was deleted without confirmation!",
)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 6. SEARCH FILES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 6. SEARCH FILES ===")
resp = chat(f"Search files for *.txt in {TEST_DIR}")
check(
    "search route", resp.get("agent") == "TAS" and "file" in resp.get("tools_used", [])
)
resp_text = resp.get("response", "")
check(
    "search returns results",
    "copy_src" in resp_text or "move_src" in resp_text or "txt" in resp_text.lower(),
    f"response: {resp_text[:150]}",
)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 7. LIST FILES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 7. LIST FILES ===")
resp = chat(f"List files in {TEST_DIR}")
check("list route", resp.get("agent") == "TAS" and "file" in resp.get("tools_used", []))
resp_text = resp.get("response", "")
check(
    "list shows files",
    "create_a" in resp_text or "copy_src" in resp_text,
    f"response: {resp_text[:150]}",
)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 8. SEND EMAIL (should route to WRI, not LLM)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 8. SEND EMAIL ===")
resp = chat("Send an email to test@example.com with subject Hello and body World")
check("email route", resp.get("agent") in ("WRI", "TAS"), f"agent={resp.get('agent')}")
check("email not LLM", resp.get("model") != "qwen3:8b", f"model={resp.get('model')}")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 9. CREATE CALENDAR EVENT (should route to MTG, not LLM)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 9. CREATE CALENDAR EVENT ===")
resp = chat("Create a calendar event for tomorrow at 3pm called Team Meeting")
check(
    "calendar route", resp.get("agent") in ("MTG", "TAS"), f"agent={resp.get('agent')}"
)
check("calendar not LLM", resp.get("model") != "qwen3:8b", f"model={resp.get('model')}")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 10. WHAT'S MY IP
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 10. WHAT'S MY IP ===")
resp = chat("What's my IP address")
check("ip route", resp.get("agent") == "TAS", f"agent={resp.get('agent')}")
check(
    "ip not LLM",
    resp.get("model") not in ("qwen3:8b", "cache"),
    f"model={resp.get('model')}",
)
resp_text = resp.get("response", "")
check(
    "ip returns address",
    "ip" in resp_text.lower()
    or "192" in resp_text
    or "10." in resp_text
    or "172" in resp_text,
    f"response: {resp_text[:100]}",
)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 11. SCREENSHOT (should work)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n=== 11. SCREENSHOT ===")
resp = chat("Take a screenshot")
check(
    "screenshot route",
    resp.get("agent") in ("SCR", "TAS"),
    f"agent={resp.get('agent')}",
)
check(
    "screenshot not LLM",
    resp.get("model") not in ("qwen3:8b", "cache"),
    f"model={resp.get('model')}",
)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SUMMARY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)
for r in results:
    print(r)
print(f"\nTotal: {passed + failed} | Passed: {passed} | Failed: {failed}")
print(
    f"Score: {passed}/{passed + failed} ({100 * passed // (passed + failed) if passed + failed else 0}%)"
)

# Cleanup
import shutil

shutil.rmtree(TEST_DIR, ignore_errors=True)
