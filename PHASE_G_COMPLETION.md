# Phase G Completion: CI & Test Consolidation

**Status**: COMPLETE
**Date**: 2026-08-10
**Deliverables**: `run_all_tests.py`, `.github/workflows/tests.yml`, reconciled `requirements.txt`

## Why This Phase Exists

Not functionality — housekeeping that became necessary because the prior six phases were successful. By Phase F this repo had 11 independent test files (`test_dashboard.py` through `test_phase_f_live_integration.py`), each deliberately designed to run as its own fresh process (see any phase's completion doc for why — mostly module-level singletons needing a clean slate). Useful in isolation, but there was no single command to run "the whole suite," and nothing ran it automatically. Eleven files you have to remember to run by hand isn't a test suite, it's a checklist.

## What Was Built

### 1. `run_all_tests.py` (new) ✓

- Auto-discovers every `test_*.py` file at repo root (`Path.glob`, not a hardcoded list — a new `test_phase_*.py` file is picked up automatically) plus `pytest tests/`
- Runs each as its own subprocess (matching how they're already meant to be run), prints a pass/fail summary, exits non-zero if anything failed

### 2. `.github/workflows/tests.yml` (new) ✓

- Runs `run_all_tests.py` on every push and PR to `main`, on a stock `ubuntu-latest` runner
- Verified green against GitHub's actual infrastructure (not just assumed from local passes) — run [31351806280](https://github.com/jhendrix86/os42-orchestrator/actions/runs/31351806280), 24s, all 12 green

### 3. `requirements.txt` reconciled ✓

- Every pin was stale — `fastapi==0.104.1` when the entire test suite has actually been run against `0.139.2` all along, and similarly for `uvicorn`, `pydantic`, `httpx`, `structlog`, `pytest`, `pytest-asyncio`, `python-dotenv`. Flagged as tech debt back in `PHASE_C_COMPLETION.md` and left alone until CI made the drift actually matter: a fresh `pip install -r requirements.txt` on a clean machine (exactly what CI does) would have pulled the old, never-actually-tested versions.
- Also dropped a bogus `asyncio` line — it's a stdlib module in Python 3; the PyPI package by that name is an unrelated Python 2 backport shim.
- Verified in an isolated venv (not just "should be fine"): fresh install of the new pins, zero dependency conflicts, full 12/12 green suite, *before* pushing.

## Verification

- `python run_all_tests.py` locally: 12/12 green
- Same command in a from-scratch venv against the reconciled `requirements.txt`: clean install, 12/12 green
- Actual GitHub Actions run on push: 12/12 green in 24s

## Key Technical Decisions

1. **Auto-discovery over a hardcoded list.** A maintained list of test files drifts the moment someone adds a new one and forgets to register it. `glob("test_*.py")` can't drift.
2. **Fixed the version pins now, not later.** Once CI exists, a stale pin isn't just inaccurate documentation anymore — it's what actually gets installed and tested on every push. Left unreconciled, CI would have been testing a fastapi version nothing in this repo has ever actually run against.
3. **Verified in an isolated venv before pushing, not just "the pins look reasonable."** The whole point of this phase is trustworthy automated verification — shipping unverified pins into a brand-new CI setup would undermine that on day one.

## Next Steps

Doesn't change what's still open elsewhere — see `PHASE_F_COMPLETION.md`'s Next Steps (real engine repos remain the biggest gap) and `PHASE_D_COMPLETION.md`'s (scheduler budget, database persistence). This phase just means all of it now gets checked automatically going forward.
