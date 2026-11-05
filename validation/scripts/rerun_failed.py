"""Re-run the 3 experiments that failed on harness bugs (E2, E4, E7).

- E2: missing typing annotations (fixed via `from __future__ import annotations`)
- E4: cp1252 console crash on emoji (run with PYTHONIOENCODING=utf-8)
- E7: `orbit.orbit.*` import needed project root on sys.path (fixed in base)

Merges results into validation/results/all_results.json + writes rerun log.
"""

import importlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from experiment_base import RESULTS_DIR

TARGETS = [
    ("experiment_2_multi_agent", "Queen / Multi-Agent Value", "run_multi_agent_experiment"),
    ("experiment_4_learning", "Learning Effectiveness", "run_learning_experiment"),
    ("experiment_7_concurrency", "Concurrency Stress Test", "run_concurrency_experiment"),
]

ALL_FILE = RESULTS_DIR / "all_results.json"


def main() -> None:
    out = {}
    if ALL_FILE.exists():
        out = json.loads(ALL_FILE.read_text(encoding="utf-8"))

    for mod_name, disp, func in TARGETS:
        print(f"\n=== RERUN: {disp} ===", flush=True)
        t0 = time.time()
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, func)
            res = mod.run_experiment(disp, fn)
            res["elapsed_seconds"] = round(time.time() - t0, 1)
            res["rerun"] = True
            out[disp] = res
            print(f"  status={res.get('status')} elapsed={res['elapsed_seconds']}s", flush=True)
        except Exception as e:
            import traceback

            traceback.print_exc()
            out[disp] = {"error": str(e), "status": "failed", "rerun": True}
            print(f"  FAILED: {e}", flush=True)
        # incremental save so partial progress survives
        ALL_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"  saved -> {ALL_FILE}", flush=True)

    print("\nRERUN BATCH COMPLETE", flush=True)


if __name__ == "__main__":
    main()
