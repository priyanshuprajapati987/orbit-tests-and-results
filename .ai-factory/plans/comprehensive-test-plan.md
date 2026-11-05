# ORBIT — Comprehensive Test Plan (No Skips)

Goal: Run every test without skipping; honest pass/fail report.

## Strategy
1. Collect all test files (221)
2. Run with `-p no:cacheprovider --no-header -q`
3. Remove skip markers where env allows (install missing deps)
4. Track failures in a report; fix one by one
5. Re-run until 0 failures, 0 skips (where feasible)

## Install missing optional deps
- ffmpeg (for audio tests)
- openpyxl (already present check)
- sounddevice

## Commands
```bash
py -m pytest tests/ -v --tb=short --durations=10
```

## Success criteria
- 0 failed
- 0 skipped (or documented reason)
- Full report saved to .ai-factory/reports/test-report.md
