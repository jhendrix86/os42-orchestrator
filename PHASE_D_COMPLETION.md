# Phase D Completion (Parts 1 & 2): Decision Execution + Autonomous Scheduling

**Status**: COMPLETE (this slice — see Scope note below)
**Date**: 2026-08-09
**Deliverables**: DecisionExecutor service, recommend+apply endpoint, per-workflow decision audit trail, background AutonomousScheduler with status/pause/resume control

## Scope Note

Phase D was left explicitly "TBD" in PHASE_A_COMPLETION.md's original roadmap ("Strategic decision making / Goal-based workflow selection / Autonomous scaling and optimization / TBD pending Stage 3-4 results"). Rather than guess at that whole surface, this pass covers two concrete, previously-flagged gaps in sequence:

1. **Decisions were generated and recorded but nothing ever acted on them** ("Decision execution not implemented" — PHASE_B_COMPLETION.md tech debt) → Part 1, `DecisionExecutor`.
2. **Applying a decision required a human (or external script) to call the new endpoint by hand** → Part 2, `AutonomousScheduler`.

Goal-based workflow selection and a real persistence layer remain open for a later pass.

## What Was Built

### 1. `app/config.py` (new) ✓
- `ENGINE_URLS` moved out of `main.py` into its own module so `routes/optimization.py` can reach it without importing `main.py` (which imports `routes/optimization.py` — would otherwise be circular)

### 2. `DecisionExecutor` (new, `app/services/decision_executor.py`) ✓
- `PAUSE` / `RESUME` are orchestrator-internal: they flip `workflow["status"]` directly, no engine involved — this is purely "should the orchestrator keep scheduling this workflow_id"
- All other actions are routed to the engine that owns them via `ACTION_ENGINE_MAP`:

  | Action | Engine | Endpoint |
  |---|---|---|
  | `SCALE_BUDGET` | marketing | `/scale_budget` |
  | `INCREASE_FREQUENCY` / `DECREASE_FREQUENCY` | marketing | `/adjust_frequency` |
  | `CHANGE_FORMAT` | content | `/change_format` |
  | `CHANGE_CHANNEL` | marketing | `/change_channel` |
  | `ADJUST_TIMING` | marketing | `/adjust_timing` |

- Engine calls are best-effort: a connection failure (very much the norm right now — none of the 11 sibling engines are actually running) is caught and reported as `status: "failed"` with a detail string, never raised. Same philosophy as `WorkflowExecutor`'s existing per-step error handling.
- Returns an `ExecutionResult` (`applied` / `failed` / `skipped`, which engine was called, a human-readable detail, timestamp)

### 3. `POST /optimization/optimize/{workflow_id}/apply` (new) ✓
- Generates a fresh decision via `analyze_and_optimize` **and** immediately applies it in one call — the actual "close the loop" step
- Looks up the tenant's workflow record (if one exists) via `request.app.state`, passes it to the executor, and appends `{decision, result}` to that workflow's new `applied_decisions` list
- Works even when no workflow was ever created for that `workflow_id` (executor still runs, just can't update local status)
- Tenant-scoped like every other `/optimization/*` route (Phase C's `X-API-Key` auth applies unchanged)

### 4. Workflow records now carry `applied_decisions` ✓
- Initialized to `[]` in `create_workflow` (main.py)
- Visible via the existing `GET /workflows/{id}` — no new read endpoint needed

### 5. `app/services/autopilot.py` (new) ✓

- `optimize_and_apply()` — the recommend-then-act logic, extracted out of the HTTP route so both the endpoint and the scheduler call the exact same code path and can't drift apart

### 6. `AutonomousScheduler` (new, `app/services/scheduler.py`) ✓

- Background `asyncio` loop started in `main.py`'s lifespan, ticking immediately on startup and then every `interval_seconds` (env: `OS42_SCHEDULER_INTERVAL_SECONDS`, default 300s)
- Each tick snapshots `app.state.active_workflows` and calls `optimize_and_apply()` for every workflow of every tenant — this is what makes the system actually autonomous rather than needing something external to call `/apply`
- `pause()` / `resume()` gate whether ticks *apply* decisions, without tearing down the loop; `stop()` cancels it outright (used on app shutdown)
- `GET /scheduler/status` (public, system-wide — running/paused/interval/tick_count/last_tick summary)
- `POST /scheduler/pause` / `POST /scheduler/resume` (admin-gated via `X-Admin-Key`, same guard as tenant provisioning)

## Test Results

**test_phase_d.py** — 4 test groups, all passing:

1. **PAUSE/RESUME**: directly flips `workflow["status"]`, confirmed no engine call happens (`engine_called is None`), confirmed a missing workflow record doesn't crash
2. **Engine call success**: `SCALE_BUDGET` against a fake in-process ASGI "engine" (via `httpx.ASGITransport`, no real network) — confirms the right endpoint (`marketing/scale_budget`) is hit with a payload containing `workflow_id`, `tenant_id`, and the decision's own parameters (`budget_increase_percent: 50`)
3. **Engine call failure**: `SCALE_BUDGET` against an intentionally unreachable port — confirms `status: "failed"` is returned, not an exception
4. **Full HTTP flow** via `TestClient` against the real `/optimization/optimize/{id}/apply` endpoint, with real (unreachable) `ENGINE_URLS`:
   - Declining-conversion workflow → `PAUSE` decision → `execution.status: "applied"` → `GET /workflows/{id}` shows `status: "paused"` and one `applied_decisions` entry
   - High-conversion workflow → `SCALE_BUDGET` decision → `execution.status: "failed"` (marketing engine isn't running) — endpoint still returns 200, proving the failure is absorbed rather than propagated as a 500
   - Apply against a `workflow_id` that was never created via `/workflows/create` → still 200, no crash

**test_phase_d_scheduler.py** — 4 test groups, all passing:

1. **One tick, two tenants**: seeds a declining workflow for tenant-x and a scaling workflow for tenant-y, runs exactly one `tick()`, confirms both get processed independently — tenant-x's workflow flips to `status: "paused"`, tenant-y's gets an engine-call attempt (reported `failed` since no engine is registered in the test) — and both get an `applied_decisions` entry
2. **start()/stop() run on a real timer**: 0.05s interval, ≥3 ticks observed in 0.3s of real sleep, then `stop()` confirmed to actually halt ticking (count unchanged after)
3. **pause()/resume()**: paused scheduler stays `running` but produces zero ticks; resuming lets it tick again
4. **HTTP**: `GET /scheduler/status` is public and reports `running: true` on a live app (started via the real lifespan); `POST /scheduler/pause` without `X-Admin-Key` → 401; with the admin key, pause/resume correctly flip `status.paused`

**Regression check** — full existing suite still green: `test_phase_d.py`, `test_phase_b.py`, `test_phase_c.py`, `test_phase_c_api.py`, `test_dashboard.py`, `test_e2e_standalone.py`, `pytest tests/` (3 passed).

## Code Structure

```
os42-orchestrator/
├── app/
│   ├── config.py (new, 22 lines)
│   │   - ENGINE_URLS (moved out of main.py)
│   ├── services/
│   │   ├── decision_executor.py (new, 145 lines)
│   │   │   - ACTION_ENGINE_MAP, ExecutionResult, DecisionExecutor
│   │   ├── autopilot.py (new, 40 lines)
│   │   │   - optimize_and_apply() - shared by the HTTP route and the scheduler
│   │   └── scheduler.py (new, 155 lines)
│   │       - TickSummary, AutonomousScheduler
│   ├── routes/
│   │   └── optimization.py (modified)
│   │       - POST /optimize/{workflow_id}/apply, now calling autopilot.optimize_and_apply()
│   └── main.py (modified)
│       - imports ENGINE_URLS from app.config instead of defining it
│       - create_workflow() initializes applied_decisions: []
│       - lifespan starts/stops an AutonomousScheduler
│       - GET /scheduler/status, POST /scheduler/pause, POST /scheduler/resume
├── test_phase_d.py (230 lines) - decision execution
└── test_phase_d_scheduler.py (new, 195 lines) - autonomous scheduling

Git History (this phase):
- 0fbd98c: Phase D (part 1): Decision execution
- d94f87d: docs: Phase D (part 1) completion report
- (pending commit): Phase D (part 2): Autonomous scheduling
```

## Key Technical Decisions

1. **PAUSE/RESUME never touch the network.** Whether the orchestrator keeps scheduling a workflow is purely its own bookkeeping — `should_run_workflow()` already existed for this in Phase B, it just never updated the actual workflow record until now.
2. **A per-call `DecisionExecutor` + `httpx.AsyncClient`, not a shared singleton.** Applying a decision is a low-frequency action (not a hot path), and this keeps the client's lifecycle trivial to reason about — construct, use, close — rather than needing app-lifespan wiring like the still-unused `WorkflowExecutor` has half-set-up. Explicitly called out as a tradeoff, not free.
3. **Engine failures are data, not exceptions.** With zero of the 11 sibling engines actually running in this environment, "engine unreachable" is the common case today, not an edge case — the endpoint has to degrade gracefully or every apply call would 500.
4. **Action → engine mapping is invented, matching the rest of the DSL.** No sibling engine repo defines a `/scale_budget` contract yet — same maturity level as `workflows.py`'s existing step definitions (`content/repurpose`, `revenue/create_offer`, etc.), which were never real either. Real engine integration is still future work across the whole orchestrator, not specific to this phase.
5. **`app/config.py` split-out was necessary, not incidental.** The new apply endpoint lives in `routes/optimization.py` and needs `ENGINE_URLS`; importing it from `main.py` would be circular since `main.py` already imports the optimization router.
6. **`autopilot.optimize_and_apply()` is shared, not duplicated.** The HTTP endpoint and the scheduler both need "decide, then act" — pulling it into one function means they literally cannot drift into different behavior over time.
7. **The scheduler re-evaluates every active workflow on every tick, unconditionally** — it does not gate on `should_run_workflow()` first. A paused workflow still gets re-analyzed each tick, which is what allows it to autonomously come back with `RESUME` once its metrics recover; gating on the *previous* decision would make PAUSE permanent until a human intervened, defeating the point of continuous autonomous reassessment.
8. **`pause()`/`resume()` gate application, not the loop itself.** Stopping the whole `asyncio.Task` on pause would mean losing tick timing and needing to recreate it on resume; instead the loop keeps running on schedule and simply skips calling `optimize_and_apply` while paused — cheaper and simpler to reason about.
9. **A snapshot copy at the top of each `tick()`.** `optimize_and_apply()` awaits inside the loop (the engine HTTP call), which yields control back to the event loop — during which a concurrent request (e.g. `POST /workflows/create`) really can mutate `app.state.active_workflows` mid-iteration in this single-threaded-but-interleaved async architecture. Copying the tenant/workflow dicts before iterating avoids a `RuntimeError: dictionary changed size during iteration`.

## Verification Checklist

- [x] OptimizationDecisions can be applied, not just recorded
- [x] PAUSE/RESUME correctly update workflow state
- [x] Engine-owned actions call the correct engine with the correct payload (proven against a fake engine)
- [x] Engine unreachability degrades gracefully (proven against both a closed port and the real, not-running sibling engines)
- [x] Applied decisions are auditable per workflow (`applied_decisions` on the workflow record)
- [x] Tenant isolation from Phase C still holds on the new endpoint
- [x] A background scheduler ticks on its own cadence and applies decisions without manual triggering
- [x] Scheduler correctly isolates tenants within a single tick (proven with two tenants, two different outcomes, one tick)
- [x] Scheduler can be paused/resumed/stopped cleanly, admin-gated where it matters
- [x] All prior-phase tests still pass

## Technical Debt / Notes

- `ACTION_ENGINE_MAP` endpoint names are invented, pending real engine contracts.
- Still in-memory throughout (workflows, metrics, decisions, applied_decisions, scheduler tick history) — a restart forgets everything, as previously noted in Phase B/C tech debt.
- No retry/backoff on failed engine calls; a failed apply simply reports failure and the next scheduler tick will just try again.
- The scheduler ticks every active workflow of every tenant on the same fixed interval — no per-workflow cadence, no backoff for workflows that keep failing to reach an engine, no prioritization by `recommend_workflow_sequence()`'s scoring (it re-evaluates everything, unconditionally, every tick). Good enough for a single orchestrator instance at prototype scale; would need real scheduling logic before this runs against dozens of tenants with many workflows each.
- Single in-process scheduler only — running more than one orchestrator instance would tick the same workflows redundantly from each instance (no distributed lock). Fine until there's a reason to run more than one instance.

## Next Steps

Remaining open items from the original Phase D roadmap:

1. **Real persistence** — tenant registry, metrics, decisions, and applied_decisions are all still in-memory
2. **Goal-based workflow selection** — a tenant states an objective, orchestrator picks/sequences workflows toward it (the scheduler currently treats every workflow equally rather than using `recommend_workflow_sequence()`'s prioritization)
