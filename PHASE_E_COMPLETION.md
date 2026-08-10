# Phase E Completion: Workflow Execution

**Status**: COMPLETE
**Date**: 2026-08-09
**Deliverables**: `WorkflowExecutor` wired into the live HTTP API for the first time, `POST /workflows/{id}/execute`

## Why This Phase Exists

Not on any prior roadmap — found while working through Phase D. `WorkflowExecutor` (`app/services/workflow_executor.py`) has existed since Phase A with a complete implementation: sequential step execution, `$steps.step_id.field` parameter resolution, per-step `on_error` handling. But `POST /workflows/create` never called it — it only ever stored the workflow's metadata (`status: "pending"`) and returned. Every "end-to-end" test that existed before this phase (`test_e2e_standalone.py`, `tests/test_content_pillar_workflow.py`) hand-simulated engine responses in the test itself, never touching `WorkflowExecutor` or making a real HTTP call through it. The module docstring's own claim — "runs real business workflows: content creation → distribution → monetization → analysis" — was true only in a test harness, never in the live API.

This phase closes that gap.

## What Was Built

### 1. `WorkflowExecutor` now test-injectable ✓
- `WorkflowExecutor.__init__(engine_urls, client=None)` — a caller can inject an `httpx.AsyncClient`; `connect()`/`disconnect()` respect it (create/close only if the executor owns the client). Same pattern as `DecisionExecutor` in Phase D part 1.

### 2. `WorkflowExecutor` wired into `main.py`'s lifespan ✓
- A module-level `workflow_executor = WorkflowExecutor(ENGINE_URLS)` singleton, `connect()`ed at startup and `disconnect()`ed at shutdown — the connect/disconnect methods existed since Phase A and were simply never called by anything until now.

### 3. `POST /workflows/{workflow_id}/execute` (new) ✓
- Looks up the tenant's existing workflow record, runs its `definition` through `workflow_executor.execute_workflow()`, records the full result as `last_execution` on the workflow record.
- 404 if the workflow was never created.
- **Deliberately does not touch `status`.** `status` is the pause/resume optimization-lifecycle field from Phase D (`DecisionExecutor` sets it to `"paused"`/`"active"`); execution outcome (`"completed"`/`"failed"` for *this run*) lives entirely in the separate `last_execution` field. A workflow can be paused for scheduling purposes and still have its steps run on demand via this endpoint, and running it doesn't implicitly un-pause it. See Key Technical Decisions for why these needed to be kept apart.
- Engine calls are best-effort, same philosophy as every other engine-calling code path since Phase D: an unreachable engine (the default in this dev environment — verified against real `ENGINE_URLS`) produces `execution.status: "failed"` in a 200 response, never a 500.
- `POST /workflows/create` itself is **completely unchanged** — still just registers metadata. Execution is opt-in via this new endpoint.

## Test Results

**test_phase_e_workflow_execution.py** — 5 test groups, all passing:

1. **Multi-step execution with real parameter resolution**: a 2-step workflow against a fake in-process ASGI engine (`httpx.ASGITransport`) — step 2's `$steps.create_pillar.id` resolves to step 1's actual returned `id` and the resolved value genuinely reaches the second HTTP call. This is the first test in the repo to prove parameter resolution works through the real code path rather than a hand-rolled simulation.
2. **`on_error: "continue"`**: a failing step doesn't abort the workflow — recorded as `{"status": "failed", ...}`, later steps still run.
3. **`on_error: "stop"` (the default)**: a failing step aborts the workflow immediately — `status: "failed"`, later steps never execute.
4. **HTTP lifecycle**: executing an unregistered `workflow_id` → 404; executing against the real (unreachable) `ENGINE_URLS` → 200 with `execution.status: "failed"`, not a 500; `last_execution` populated, `status` field untouched (`"pending"`).
5. **Execution doesn't disturb pause/resume**: a workflow paused via a real `PAUSE` decision (declining metrics → `/optimization/optimize/{id}/apply`) stays `status: "paused"` after being executed via the new endpoint — proving the two lifecycles (optimization pause state vs. one-shot execution outcome) are genuinely independent, not just documented as such.

**Regression check** — full existing suite still green, zero changes needed anywhere else: `test_phase_d_goals.py`, `test_phase_d_persistence.py`, `test_phase_d_scheduler.py`, `test_phase_d.py`, `test_phase_c.py`, `test_phase_c_api.py`, `test_phase_b.py`, `test_dashboard.py`, `test_e2e_standalone.py`, `pytest tests/` (3 passed). `POST /workflows/create`'s behavior is byte-for-byte unchanged, so nothing that calls it needed updating.

## Code Structure

```
os42-orchestrator/
├── app/
│   ├── services/
│   │   └── workflow_executor.py (modified)
│   │       - __init__(engine_urls, client=None), connect()/disconnect() respect an injected client
│   └── main.py (modified)
│       - workflow_executor = WorkflowExecutor(ENGINE_URLS) module-level singleton
│       - lifespan: connect() at startup, disconnect() at shutdown
│       - POST /workflows/{workflow_id}/execute
└── test_phase_e_workflow_execution.py (new, 260 lines)

Git History (this phase):
- (pending commit): Phase E: Workflow execution
```

## Key Technical Decisions

1. **A separate `execute` endpoint, not making `create_workflow` execute synchronously.** The first design considered was having `POST /workflows/create` run the workflow immediately and move it into `workflow_results` on completion — but that directly conflicts with the existing Phase D model, where `workflow_id` is a stable, ongoing handle you keep re-optimizing (`PAUSE`/`RESUME`/`SCALE_BUDGET` assume the workflow record stays in `active_workflows` indefinitely). Making creation immediately archive the record would mean `DecisionExecutor`'s and the scheduler's `active_workflows` lookups stop finding it, silently breaking the entire Phase D optimization loop for every workflow. Splitting "register this workflow" (unchanged) from "run its steps" (new) avoids that collision entirely and cost nothing in regression risk — confirmed by every Phase C/D test passing unmodified.
2. **`last_execution`, not overloading `status`.** Same collision as above, one level down: `status` already means "paused/active" to the whole optimization system. Execution outcome needed its own field so a workflow's DSL steps can be (re-)run without ever touching what `PAUSE`/`RESUME` set. Verified directly (Test 5): pause, execute, still paused.
3. **Synchronous execution, not a background task.** Considered making execution fire-and-forget (return immediately, poll for completion) to avoid blocking the HTTP response on potentially-slow engine calls. Rejected for now: connection failures to unreachable localhost engines resolve in ~1-2s here (measured), not the full 30s client timeout, and a background-task design would need deterministic completion signaling for tests (polling/sleeping) that a synchronous call doesn't. Revisit if/when real engines exist and might genuinely be slow — see Technical Debt.
4. **Client injection mirrors `DecisionExecutor`'s existing pattern exactly**, rather than inventing a new testing seam. Consistency: anyone who already understands how Phase D's engine-calling tests work can read this file's tests without relearning anything.

## Verification Checklist

- [x] `WorkflowExecutor.execute_workflow()` is reachable from the live HTTP API for the first time since Phase A
- [x] `$steps.x.y` parameter resolution proven against a real (fake) engine, not simulated
- [x] `on_error: "continue"` vs `"stop"` both proven to behave as designed through the real executor
- [x] Unreachable engines degrade gracefully over HTTP (200 + `execution.status: "failed"`, never a 500)
- [x] Execution and the pause/resume optimization lifecycle proven independent, not just documented as such
- [x] `POST /workflows/create`'s existing behavior fully preserved (every Phase C/D test using it still passes unmodified)
- [x] All prior-phase tests still pass

## Technical Debt / Notes

- Still synchronous/blocking within the request — fine while engines are unreachable-and-fast-to-fail or nonexistent; once real engines exist and might be slow or do real work, this should become an async/background execution model with a way to poll status, rather than holding the HTTP connection open.
- No retry on a failed step; same as every other engine-calling code path in this repo so far (Decision execution in Phase D has the identical limitation).
- `workflow["steps"]` (set to `[]` at creation, a pre-existing Phase A field, separate from `definition["steps"]`) remains unpopulated — pre-existing, not touched by this phase, and superseded by `last_execution["results"]` for anything that actually needs step-level detail now.
- No endpoint to list or clear execution history beyond the single `last_execution` — re-executing overwrites it. A tenant wanting a full execution history per workflow would need that added.
- Like every engine-calling feature in this repo, `ACTION_ENGINE_MAP`-style endpoint names (here: whatever `action` a step specifies, e.g. `/create`, `/repurpose`) are invented, pending real engine contracts.

## Next Steps

- **Real engine integration** remains the single biggest unblock across the whole orchestrator (flagged in every phase since A) — this phase makes the orchestrator *capable* of driving real engines the moment one exists with a matching contract, but none do yet.
- **Async execution + status polling**, once real engines might actually be slow enough to matter.
- The Phase D "Next Steps" items (per-tick scheduler budget using goal-weighted ordering, real database persistence) remain open and are unaffected by this phase.
