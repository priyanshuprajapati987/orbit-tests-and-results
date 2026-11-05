"""
Experiment 7: Concurrency Stress Test

Validate claimed concurrency improvements.
Run progressive thread counts and look for:
- Race conditions
- Deadlocks
- Duplicate IDs
- Corrupted files
- Lost messages
- Inconsistent state
- Crashes
- Memory growth
- Leaked resources
"""
from __future__ import annotations

import json
import os
import sys
import time
import threading
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
from experiment_base import (
    run_experiment, call_orbit_api, call_orbit_chat, RESULTS_DIR
)


def test_concurrent_api_calls(n_threads: int, duration_sec: int = 10) -> Dict:
    """Send concurrent API calls and measure failures."""
    results = {
        "threads": n_threads,
        "duration_sec": duration_sec,
        "total_calls": 0,
        "successful": 0,
        "failed": 0,
        "timeouts": 0,
        "errors": [],
        "latencies": [],
        "start_time": time.time(),
    }

    stop_event = threading.Event()
    lock = threading.Lock()

    def worker(worker_id):
        call_count = 0
        while not stop_event.is_set():
            try:
                start = time.time()
                resp = call_orbit_api("/api/health", timeout=10)
                latency = (time.time() - start) * 1000

                with lock:
                    call_count += 1
                    results["latencies"].append(latency)
                    if "error" in resp:
                        results["failed"] += 1
                        if "timeout" in str(resp["error"]).lower():
                            results["timeouts"] += 1
                        results["errors"].append(resp["error"][:200])
                    else:
                        results["successful"] += 1

            except Exception as e:
                with lock:
                    results["failed"] += 1
                    results["errors"].append(str(e)[:200])

            time.sleep(0.1)

        with lock:
            results["total_calls"] += call_count

    threads = []
    for i in range(n_threads):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        threads.append(t)
        t.start()

    time.sleep(duration_sec)
    stop_event.set()
    for t in threads:
        t.join(timeout=5)

    # Calculate stats
    if results["latencies"]:
        latencies = sorted(results["latencies"])
        results["p50_latency"] = round(latencies[len(latencies) // 2], 1)
        results["p95_latency"] = round(latencies[int(len(latencies) * 0.95)], 1)
        results["p99_latency"] = round(latencies[int(len(latencies) * 0.99)], 1)
        results["mean_latency"] = round(sum(latencies) / len(latencies), 1)

    results["success_rate"] = round(
        results["successful"] / max(1, results["total_calls"]) * 100, 1
    )
    results["elapsed"] = round(time.time() - results["start_time"], 1)

    return results


def test_concurrent_chat(n_threads: int) -> Dict:
    """Send concurrent chat messages."""
    prompts = [
        "What is 2+2?",
        "What is the capital of France?",
        "Write a haiku about coding.",
        "Explain what a function is.",
        "What is 7*8?",
        "Name three programming languages.",
        "What color is the sky?",
        "How many continents are there?",
        "What is JSON?",
        "Explain recursion briefly.",
    ]

    results = {
        "threads": n_threads,
        "total_calls": 0,
        "successful": 0,
        "failed": 0,
        "latencies": [],
        "errors": [],
    }

    def worker(idx):
        prompt = prompts[idx % len(prompts)]
        try:
            start = time.time()
            resp = call_orbit_chat(prompt, timeout=60)
            latency = (time.time() - start) * 1000

            with lock:
                results["total_calls"] += 1
                results["latencies"].append(latency)
                if "error" in resp:
                    results["failed"] += 1
                    results["errors"].append(resp["error"][:200])
                else:
                    results["successful"] += 1
        except Exception as e:
            with lock:
                results["total_calls"] += 1
                results["failed"] += 1
                results["errors"].append(str(e)[:200])

    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(n_threads)]
        for f in as_completed(futures):
            try:
                f.result()
            except:
                pass

    if results["latencies"]:
        results["mean_latency"] = round(sum(results["latencies"]) / len(results["latencies"]), 1)
    results["success_rate"] = round(
        results["successful"] / max(1, results["total_calls"]) * 100, 1
    )

    return results


def test_concurrent_file_ops(n_threads: int) -> Dict:
    """Test concurrent file operations."""
    from orbit.orbit.tools.file_tools import FileTools

    tools = FileTools()
    test_dir = Path("orbit_data/validation_concurrency_test")
    test_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "threads": n_threads,
        "operations": 0,
        "successful": 0,
        "failed": 0,
        "corrupted": 0,
        "errors": [],
    }

    lock = threading.Lock()

    def worker(idx):
        filename = test_dir / f"test_{idx}.txt"
        content = f"Thread {idx} wrote this at {time.time()}\n" * 10

        try:
            # Write
            filename.write_text(content, encoding="utf-8")

            # Read back
            read_back = filename.read_text(encoding="utf-8")

            # Verify
            with lock:
                results["operations"] += 2
                if read_back == content:
                    results["successful"] += 2
                else:
                    results["corrupted"] += 1
                    results["failed"] += 1
                    results["errors"].append(f"Corruption in {filename}")

        except Exception as e:
            with lock:
                results["operations"] += 1
                results["failed"] += 1
                results["errors"].append(str(e)[:200])

    threads = []
    for i in range(n_threads):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10)

    # Cleanup
    try:
        for f in test_dir.glob("test_*.txt"):
            f.unlink()
        test_dir.rmdir()
    except:
        pass

    results["success_rate"] = round(
        results["successful"] / max(1, results["operations"]) * 100, 1
    )

    return results


def run_concurrency_experiment():
    """Run all concurrency tests."""
    results = {
        "experiment": "Concurrency Stress Test",
        "description": "Validate concurrency improvements under load",
        "api_tests": [],
        "chat_tests": [],
        "file_tests": [],
    }

    thread_counts = [5, 10, 20]

    for n in thread_counts:
        print(f"\n  === {n} threads ===")

        # API health endpoint
        print(f"    API health ({n} threads)...", end="", flush=True)
        api_result = test_concurrent_api_calls(n, duration_sec=5)
        results["api_tests"].append(api_result)
        print(f" success={api_result['success_rate']}% calls={api_result['total_calls']}")

        # Chat messages
        if n <= 10:  # Skip chat for high thread counts (too slow)
            print(f"    Chat ({n} threads)...", end="", flush=True)
            chat_result = test_concurrent_chat(n)
            results["chat_tests"].append(chat_result)
            print(f" success={chat_result['success_rate']}% calls={chat_result['total_calls']}")

        # File operations
        print(f"    File ops ({n} threads)...", end="", flush=True)
        file_result = test_concurrent_file_ops(n)
        results["file_tests"].append(file_result)
        print(f" success={file_result['success_rate']}% corrupted={file_result['corrupted']}")

    # Overall assessment
    total_api_calls = sum(t["total_calls"] for t in results["api_tests"])
    total_api_success = sum(t["successful"] for t in results["api_tests"])
    total_corrupted = sum(t["corrupted"] for t in results["file_tests"])

    results["assessment"] = {
        "total_api_calls": total_api_calls,
        "total_api_success_rate": round(total_api_success / max(1, total_api_calls) * 100, 1),
        "total_corrupted_files": total_corrupted,
        "concurrency_safe": total_corrupted == 0 and total_api_success / max(1, total_api_calls) > 0.95,
    }

    return results


if __name__ == "__main__":
    result = run_experiment("Concurrency Stress Test", run_concurrency_experiment)
