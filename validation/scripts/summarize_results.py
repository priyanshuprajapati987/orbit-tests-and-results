"""Summarize validation run_all results -> per-experiment verdict lines.

Usage: python validation/scripts/summarize_results.py [results_file]
Default: validation/results/all_results.json
"""

import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent / "results"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS_DIR / "all_results.json"
    if not path.exists():
        print(f"MISSING: {path}")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"file: {path}")
    print(f"experiments: {len(data)}")
    print("=" * 70)
    for name, res in data.items():
        if not isinstance(res, dict):
            print(f"{name}: {res!r}")
            continue
        if "error" in res:
            print(f"{name}: FAILED - {str(res['error'])[:100]}")
            continue
        status = res.get("status", "?")
        elapsed = res.get("elapsed_seconds", "?")
        summary = res.get("summary") or {}
        parts = [f"{k}={v}" for k, v in summary.items() if not isinstance(v, (dict, list))]
        print(f"{name}: status={status} elapsed={elapsed}s")
        for p in parts:
            print(f"    {p}")
        # extra detail keys commonly present
        for key in ("conclusion", "findings", "issues", "verdict"):
            if key in res:
                print(f"    {key}: {str(res[key])[:300]}")
    print("=" * 70)


if __name__ == "__main__":
    main()
