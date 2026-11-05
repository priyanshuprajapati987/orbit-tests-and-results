"""
Experiment 6: Tool Reality Test

Test complete tasks, not just endpoint responses.

For every tool, test:
START → PLAN → TOOL USE → RESULT → VERIFICATION
"""
from __future__ import annotations

import json
import os
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    run_experiment, call_orbit_chat, call_orbit_api,
    get_ollama_response, RESULTS_DIR
)


TOOL_TASKS = [
    {
        "id": "tool_001",
        "name": "file_create_read",
        "description": "Create a file, read it back, verify content",
        "steps": [
            {"action": "chat", "prompt": "Create a file called orbit_data/validation_test.txt with the content 'Hello from validation test'"},
            {"action": "verify", "check": "file_exists", "path": "orbit_data/validation_test.txt"},
            {"action": "verify", "check": "file_contains", "path": "orbit_data/validation_test.txt", "expected": "Hello from validation test"},
        ],
    },
    {
        "id": "tool_002",
        "name": "file_edit",
        "description": "Create file, edit it, verify changes",
        "steps": [
            {"action": "chat", "prompt": "Create a file called orbit_data/validation_edit_test.txt with the content 'Line 1'"},
            {"action": "chat", "prompt": "Append 'Line 2' to the file orbit_data/validation_edit_test.txt"},
            {"action": "verify", "check": "file_contains", "path": "orbit_data/validation_edit_test.txt", "expected": "Line 2"},
        ],
    },
    {
        "id": "tool_003",
        "name": "system_info",
        "description": "Get system information",
        "steps": [
            {"action": "chat", "prompt": "Tell me the system information including OS and memory"},
            {"action": "verify", "check": "response_contains", "keywords": ["windows", "memory"]},
        ],
    },
    {
        "id": "tool_004",
        "name": "list_processes",
        "description": "List running processes",
        "steps": [
            {"action": "chat", "prompt": "List the running processes"},
            {"action": "verify", "check": "response_not_empty"},
        ],
    },
    {
        "id": "tool_005",
        "name": "list_files",
        "description": "List files in a directory",
        "steps": [
            {"action": "chat", "prompt": "List the files in the orbit directory"},
            {"action": "verify", "check": "response_not_empty"},
        ],
    },
    {
        "id": "tool_006",
        "name": "clipboard_operations",
        "description": "Read and write clipboard",
        "steps": [
            {"action": "chat", "prompt": "Copy the text 'validation clipboard test' to the clipboard"},
            {"action": "chat", "prompt": "What is currently in the clipboard?"},
            {"action": "verify", "check": "response_contains", "keywords": ["validation", "clipboard"]},
        ],
    },
    {
        "id": "tool_007",
        "name": "code_generation",
        "description": "Generate and save a Python script",
        "steps": [
            {"action": "chat", "prompt": "Write a Python function that calculates factorial and save it to orbit_data/validation_factorial.py"},
            {"action": "verify", "check": "file_exists", "path": "orbit_data/validation_factorial.py"},
        ],
    },
    {
        "id": "tool_008",
        "name": "file_search",
        "description": "Search for files",
        "steps": [
            {"action": "chat", "prompt": "Search for Python files in the orbit directory"},
            {"action": "verify", "check": "response_not_empty"},
        ],
    },
    {
        "id": "tool_009",
        "name": "file_delete",
        "description": "Delete a test file",
        "steps": [
            {"action": "chat", "prompt": "Create a file called orbit_data/validation_delete_me.txt with content 'delete me'"},
            {"action": "chat", "prompt": "Delete the file orbit_data/validation_delete_me.txt"},
            {"action": "verify", "check": "file_not_exists", "path": "orbit_data/validation_delete_me.txt"},
        ],
    },
    {
        "id": "tool_010",
        "name": "multi_step_task",
        "description": "Create, modify, verify, and report on a file",
        "steps": [
            {"action": "chat", "prompt": "Create orbit_data/validation_multi.txt with 'Step 1: Created'"},
            {"action": "chat", "prompt": "Add 'Step 2: Modified' to orbit_data/validation_multi.txt"},
            {"action": "chat", "prompt": "Read orbit_data/validation_multi.txt and tell me what it contains"},
            {"action": "verify", "check": "response_contains", "keywords": ["Step 1", "Step 2"]},
        ],
    },
]


def verify_step(step: Dict) -> Dict:
    """Execute a verification step."""
    check = step.get("check", "")

    if check == "file_exists":
        path = Path(step["path"])
        return {"passed": path.exists(), "detail": f"File {path} exists={path.exists()}"}

    elif check == "file_not_exists":
        path = Path(step["path"])
        return {"passed": not path.exists(), "detail": f"File {path} exists={path.exists()}"}

    elif check == "file_contains":
        path = Path(step["path"])
        if not path.exists():
            return {"passed": False, "detail": f"File {path} does not exist"}
        content = path.read_text(encoding="utf-8")
        expected = step.get("expected", "")
        return {
            "passed": expected.lower() in content.lower(),
            "detail": f"Content contains '{expected}': {expected.lower() in content.lower()}",
        }

    elif check == "response_contains":
        # This is checked against the last response
        return {"passed": None, "detail": "checked against last response"}

    elif check == "response_not_empty":
        return {"passed": None, "detail": "checked against last response"}

    return {"passed": None, "detail": f"Unknown check: {check}"}


def run_tool_reality_experiment():
    """Run tool reality test experiment."""
    results = {
        "experiment": "Tool Reality Test",
        "description": "Test complete tool tasks end-to-end",
        "tasks": [],
        "summary": {},
    }

    total_steps = 0
    passed_steps = 0
    failed_steps = 0
    task_successes = 0

    for task in TOOL_TASKS:
        print(f"\n  Task: {task['name']}")
        task_result = {
            "id": task["id"],
            "name": task["name"],
            "steps": [],
            "status": "in_progress",
        }

        last_response = ""
        all_passed = True

        for step in task["steps"]:
            total_steps += 1
            step_result = {"action": step["action"]}

            if step["action"] == "chat":
                print(f"    Chat: {step['prompt'][:60]}...", end="", flush=True)
                start = time.time()
                resp = call_orbit_chat(step["prompt"], timeout=60)
                latency = (time.time() - start) * 1000

                if "error" not in resp:
                    last_response = resp.get("response", resp.get("text", ""))
                    step_result["success"] = True
                    step_result["latency_ms"] = round(latency, 1)
                    step_result["response_preview"] = last_response[:200]
                    print(f" OK ({latency:.0f}ms)")
                else:
                    step_result["success"] = False
                    step_result["error"] = resp["error"]
                    all_passed = False
                    print(f" ERROR: {resp['error'][:80]}")

            elif step["action"] == "verify":
                print(f"    Verify: {step.get('check', '?')}...", end="", flush=True)

                # Special handling for response-based checks
                if step["check"] in ("response_contains", "response_not_empty"):
                    if step["check"] == "response_contains":
                        keywords = step.get("keywords", [])
                        matched = sum(1 for kw in keywords if kw.lower() in last_response.lower())
                        passed = matched == len(keywords)
                        step_result["passed"] = passed
                        step_result["detail"] = f"Matched {matched}/{len(keywords)} keywords"
                    else:
                        passed = len(last_response.strip()) > 0
                        step_result["passed"] = passed
                        step_result["detail"] = f"Response length: {len(last_response)}"
                else:
                    vr = verify_step(step)
                    step_result.update(vr)
                    passed = vr.get("passed", False)

                if passed:
                    passed_steps += 1
                    print(f" PASS")
                else:
                    failed_steps += 1
                    all_passed = False
                    print(f" FAIL: {step_result.get('detail', '?')}")

            task_result["steps"].append(step_result)
            time.sleep(0.5)

        task_result["status"] = "success" if all_passed else "failed"
        if all_passed:
            task_successes += 1
        results["tasks"].append(task_result)

    results["summary"] = {
        "total_tasks": len(TOOL_TASKS),
        "successful_tasks": task_successes,
        "task_success_rate": round(task_successes / max(1, len(TOOL_TASKS)) * 100, 1),
        "total_steps": total_steps,
        "passed_steps": passed_steps,
        "failed_steps": failed_steps,
        "step_success_rate": round(passed_steps / max(1, total_steps) * 100, 1),
    }

    return results


if __name__ == "__main__":
    result = run_experiment("Tool Reality Test", run_tool_reality_experiment)
    if "summary" in result:
        s = result["summary"]
        print(f"\nTask success rate: {s['task_success_rate']}% ({s['successful_tasks']}/{s['total_tasks']})")
        print(f"Step success rate: {s['step_success_rate']}% ({s['passed_steps']}/{s['total_steps']})")
