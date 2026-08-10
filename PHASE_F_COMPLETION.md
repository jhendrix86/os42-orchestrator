# Phase F Completion: Live Integration

**Status**: COMPLETE
**Date**: 2026-08-09
**Deliverables**: `mock_engines.py` (a runnable reference engine), the first test in this repo proving genuine end-to-end success rather than graceful failure

## Why This Phase Exists

Every test in this repo, across every prior phase, proves the orchestrator handles an *unreachable* engine gracefully — because none of the 11 sibling engine repos (content-engine, marketing-automation-engine, ...) implement anything the orchestrator can actually call yet. That's been true since Phase A. It means every "it works" claim so far has really meant "it fails safely," never "it succeeds." `mock_engines.py` is a small, honest stand-in: it doesn't simulate real business logic, it just genuinely listens on a real port and answers real HTTP requests, so the orchestrator's actual success path (not just its failure path) gets exercised for the first time.

## What Was Built

### 1. `mock_engines.py` (new, repo root) ✓

- A tiny standalone FastAPI service (`python mock_engines.py`, default port 9000, override via `MOCK_ENGINES_PORT`)
- One catch-all route (`POST /{action:path}`) answers *any* action any engine might be asked for with a generic canned success response (`{"status": "ok", "id": "mock-...", "received": <echoed payload>, ...}`) plus a few generically-useful fields (`formats`, `distribution_results`, `reach`, `offer_id`, `tracking_id`) that some workflow steps pull via `$steps.x.y`
- `GET /health` for readiness polling
- Point any/all of the `*_ENGINE_URL` env vars at it and the real orchestrator (`python -m app.main`) will actually succeed against it — this is meant to be run by hand for local dev/demo, not just by the test below

### 2. `test_phase_f_live_integration.py` (new) ✓

- The only test in this repo that starts a **genuinely separate OS process** (`subprocess.Popen`, real port, polled via `/health`) rather than an in-process ASGI fake (`httpx.ASGITransport`, used by every engine-calling test since Phase D)
- Sets every `*_ENGINE_URL` env var to point at it before importing anything from `app.*` (env vars are read at import time by `app/config.py`)
- Drives the real orchestrator through `TestClient` against this real subprocess

## Test Results

**test_phase_f_live_integration.py** — 2 test groups, both passing, both proving *success* for the first time:

1. **Workflow execution succeeds for real**: a 3-step workflow (`content/create` → `content/repurpose` → `marketing/distribute`) run via `POST /workflows/{id}/execute` (Phase E) completes with `status: "completed"` — every prior test of this endpoint could only prove `status: "failed"` gracefully, since nothing was ever listening. Also re-confirms `$steps.create_pillar.id` parameter resolution carries the *real* returned id from mock_engines.py into step 2's actual outbound HTTP payload — not a fake/simulated value.
2. **Decision execution succeeds for real**: a `SCALE_BUDGET` decision applied via `POST /optimization/optimize/{id}/apply` (Phase D part 1) returns `execution.status: "applied"`, `engine_called: "marketing"` — every prior test of this endpoint could only prove `status: "failed"`.

**Regression check** — full existing suite still green, zero changes needed anywhere else: `test_phase_e_workflow_execution.py`, `test_phase_d_goals.py`, `test_phase_d_persistence.py`, `test_phase_d_scheduler.py`, `test_phase_d.py`, `test_phase_c.py`, `test_phase_c_api.py`, `test_phase_b.py`, `test_dashboard.py`, `test_e2e_standalone.py`, `pytest tests/` (3 passed). This phase adds nothing to `app/` itself — no production code changed, only a new dev tool and a new test.

## Code Structure

```
os42-orchestrator/
├── mock_engines.py (new, 75 lines)
│   - Catch-all reference engine, run standalone or from the test below
└── test_phase_f_live_integration.py (new, 175 lines)
    - Spawns mock_engines.py as a real subprocess, proves real success

Git History (this phase):
- (pending commit): Phase F: Live integration against a real engine
```

## Key Technical Decisions

1. **A genuine subprocess over a real socket, not `httpx.ASGITransport`.** Every engine-calling test since Phase D uses an in-process ASGI fake for speed and simplicity - which is exactly right for testing the orchestrator's *own* logic (parameter resolution, error handling, decision mapping), but it can never prove the orchestrator actually works over a real network connection to a real, separately-running process, because it never leaves the same Python interpreter. This phase exists specifically to close that particular gap, so it deliberately pays the cost of a real subprocess + real TCP.
2. **One catch-all route, not eleven differentiated engine contracts.** Building a semantically-faithful mock of each of the 11 sibling engines (each with its own real business logic) is a much bigger undertaking than what this phase needs to prove, and would just be guessing at contracts that don't exist yet anyway (see every phase's tech debt notes on invented `ACTION_ENGINE_MAP`/DSL contracts). A generic success response is honest about what it is - a reachability and mechanics proof, not a functional simulation - while still being genuinely useful for local dev/demo.
3. **`mock_engines.py` lives at repo root as a standalone script, not under `app/`.** It's a dev tool you run by hand alongside the orchestrator, not orchestrator internals - same category as `test_dashboard.py`/`test_e2e_standalone.py`'s standalone-script convention, not a service the orchestrator imports or depends on.
4. **No production code changed.** Unlike every other phase, this one is purely additive - a dev tool and a test. `app/` is untouched, which is also why the regression check needed zero updates anywhere.

## Verification Checklist

- [x] A workflow can genuinely complete successfully end-to-end (not just fail gracefully) for the first time in this repo's test history
- [x] A decision can genuinely apply successfully end-to-end for the first time
- [x] Parameter resolution (`$steps.x.y`) proven to carry a real value from a real HTTP response into a real subsequent HTTP call
- [x] The proof uses a genuinely separate OS process over a real network connection, not an in-process fake
- [x] Zero changes to `app/` - this phase adds capability without touching production code
- [x] All prior-phase tests still pass

## Technical Debt / Notes

- `mock_engines.py` answers every action identically regardless of what it actually means - it cannot catch a workflow that's semantically wrong (e.g., asking `marketing` to do something only `content` should), only that the HTTP mechanics work. Real engines, whenever they exist, will have real (and stricter) contracts.
- Not wired into CI or any other test file - it's invoked only by `test_phase_f_live_integration.py`, on demand.
- Binds a real port (9123 for the test, 9000 by default when run by hand) - if that's ever in use on a given machine, the test's `wait_for_health` will time out and fail clearly rather than hang silently, but the port isn't configurable per-test-run today.

## Next Steps

This phase doesn't change what's still open elsewhere:

- **Real engine repos** are still the biggest gap - `mock_engines.py` proves the orchestrator *can* succeed against something, not that any of the 11 sibling repos actually exist as working services yet.
- The Phase D "Next Steps" items (per-tick scheduler budget using goal-weighted ordering, real database persistence) remain open.
- Phase E's async-execution note (revisit synchronous execution once real engines might be slow) remains open.
