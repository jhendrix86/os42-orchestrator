# Phase D Completion (Parts 1, 2 & 3): Decision Execution + Autonomous Scheduling + Persistence

**Status**: COMPLETE (this slice — see Scope note below)
**Date**: 2026-08-09
**Deliverables**: DecisionExecutor service, recommend+apply endpoint, per-workflow decision audit trail, background AutonomousScheduler with status/pause/resume control, opt-in snapshot persistence surviving real process restarts

## Scope Note

Phase D was left explicitly "TBD" in PHASE_A_COMPLETION.md's original roadmap ("Strategic decision making / Goal-based workflow selection / Autonomous scaling and optimization / TBD pending Stage 3-4 results"). Rather than guess at that whole surface, this pass covers three concrete, previously-flagged gaps in sequence:

1. **Decisions were generated and recorded but nothing ever acted on them** ("Decision execution not implemented" — PHASE_B_COMPLETION.md tech debt) → Part 1, `DecisionExecutor`.
2. **Applying a decision required a human (or external script) to call the new endpoint by hand** → Part 2, `AutonomousScheduler`.
3. **Everything was in-memory only — a restart forgot every tenant, metric, decision, and workflow** (flagged in every prior phase's tech debt) → Part 3, snapshot persistence.

Goal-based workflow selection (using `recommend_workflow_sequence()`'s prioritization in the scheduler, rather than ticking every workflow equally) remains open for a later pass.

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

### 7. Snapshot persistence (new, `app/services/persistence.py`) ✓

- **Opt-in via `OS42_PERSISTENCE_PATH`.** Unset (the default, and the case for every test in this repo except the new persistence tests) → `save_snapshot()`/`load_snapshot()` are true no-ops, and the orchestrator behaves byte-for-byte like every prior phase.
- When set: `load_snapshot()` runs at the top of `main.py`'s lifespan, before the scheduler starts, restoring tenants, metrics, decisions, and workflow records into the (normally empty) module-level singletons and `app.state`.
- `save_snapshot()` runs on the scheduler's `on_tick` hook (so a crash loses at most one tick interval's worth of data) and again on clean shutdown.
- Writes are atomic (`write to .tmp` then `os.replace()`, which is atomic on both POSIX and Windows) so a crash mid-write can't corrupt the snapshot file.
- Added `TenantRegistry.restore()` and `OptimizationEngine.restore()` — small, explicit methods for inserting an already-fully-formed `Tenant`/`OptimizationDecision` from a snapshot, kept separate from `register()`/`analyze_and_optimize()` so loading never re-generates an api_key or re-runs analysis.
- Explicitly a **snapshot, not a transaction log or a real database** — see Technical Debt below.

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

**test_phase_d_persistence.py** — 3 test groups, all passing. Unlike every other test file in this repo, this one spawns genuinely separate Python subprocesses for the "before" and "after" sides of each round trip — two objects in the same process would share already-populated singletons and prove nothing about surviving a real restart:

1. **Service-layer restart**: process A builds a tenant + metric + decision directly against `MetricsAggregator`/`OptimizationEngine`/`TenantRegistry` and calls `save_snapshot()`; a completely separate process B constructs brand-new empty instances and calls `load_snapshot()` — same tenant_id, same api_key (exact round trip, not regenerated), same metric count, same decision action
2. **Full HTTP restart**: process A spins up the real app via `TestClient` with `OS42_PERSISTENCE_PATH` set, provisions a tenant, creates a workflow, records a metric, then exits (triggering the lifespan's shutdown save) — process B spins up a *fresh* `TestClient(app)` pointed at the same snapshot file and successfully calls `GET /workflows` with the tenant's original API key, seeing the exact workflow process A created
3. **Disabled by default**: with no env var set (true for every other test in the repo), `persistence.PERSISTENCE_PATH is None`, and both `save_snapshot()`/`load_snapshot()` return `None`/`False` without touching disk

**Regression check** — full existing suite still green with zero changes needed: `test_phase_d_scheduler.py`, `test_phase_d.py`, `test_phase_b.py`, `test_phase_c.py`, `test_phase_c_api.py`, `test_dashboard.py`, `test_e2e_standalone.py`, `pytest tests/` (3 passed).

## Code Structure

```
os42-orchestrator/
├── app/
│   ├── config.py (22 lines)
│   │   - ENGINE_URLS (moved out of main.py)
│   ├── services/
│   │   ├── decision_executor.py (145 lines)
│   │   │   - ACTION_ENGINE_MAP, ExecutionResult, DecisionExecutor
│   │   ├── autopilot.py (40 lines)
│   │   │   - optimize_and_apply() - shared by the HTTP route and the scheduler
│   │   ├── scheduler.py (modified)
│   │   │   - TickSummary, AutonomousScheduler, now with an on_tick hook
│   │   ├── persistence.py (new, 165 lines)
│   │   │   - build_snapshot/save_snapshot/load_snapshot, opt-in via OS42_PERSISTENCE_PATH
│   │   ├── tenancy.py (modified)
│   │   │   - TenantRegistry.restore() for loading a snapshot's tenants
│   │   └── optimization_engine.py (modified)
│   │       - OptimizationEngine.restore() for loading a snapshot's decisions
│   ├── routes/
│   │   └── optimization.py (modified)
│   │       - POST /optimize/{workflow_id}/apply, now calling autopilot.optimize_and_apply()
│   └── main.py (modified)
│       - imports ENGINE_URLS from app.config instead of defining it
│       - create_workflow() initializes applied_decisions: []
│       - lifespan loads a snapshot (if configured), then starts/stops an AutonomousScheduler
│       - GET /scheduler/status, POST /scheduler/pause, POST /scheduler/resume
├── test_phase_d.py (230 lines) - decision execution
├── test_phase_d_scheduler.py (195 lines) - autonomous scheduling
└── test_phase_d_persistence.py (new, 240 lines) - snapshot persistence across real restarts

Git History (this phase):
- 0fbd98c: Phase D (part 1): Decision execution
- d94f87d: docs: Phase D (part 1) completion report
- 2e42a72: Phase D (part 2): Autonomous scheduling
- d23a2a6: docs: Phase D (part 2) completion report
- (pending commit): Phase D (part 3): Persistence
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
10. **Persistence is opt-in, not the default.** Defaulting to "always persist to some file" would mean every test in this repo needs to manage a DB file's lifecycle. Instead `OS42_PERSISTENCE_PATH` unset (true everywhere except the three new persistence tests) makes `save_snapshot`/`load_snapshot` unconditional no-ops — zero risk to seven other test files that know nothing about persistence.
11. **A JSON snapshot, not a database.** The scale here (single dev instance, in-memory data structures already fit comfortably in memory) doesn't justify SQLite/Postgres and a migration story yet. A snapshot is trivially inspectable (`cat` the file), and `restore()` methods keep the load path from needing to reach into each service's private internals.
12. **Piggybacking the scheduler's `on_tick` for periodic saves, instead of a second timer.** The scheduler already runs on exactly the cadence a periodic save should use; adding a second independent timer would be duplicate machinery for no benefit. The hook is generic (`Callable[[TickSummary], None]`) so the scheduler itself stays persistence-agnostic.
13. **`restore()` methods, not reusing `register()`/`analyze_and_optimize()`.** Loading a snapshot needs to insert an *already-decided* fact (this exact tenant, with this exact api_key and created_at; this exact past decision) without re-running any of the logic that produces new ones — reusing the normal write paths would regenerate api_keys and misdate `created_at`.

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
- [x] State (tenants, metrics, decisions, workflows) survives a genuine process restart, proven at both the service layer and over real HTTP
- [x] Persistence is a true no-op when not configured (proven directly, and by every other test file needing zero changes)
- [x] All prior-phase tests still pass

## Technical Debt / Notes

- `ACTION_ENGINE_MAP` endpoint names are invented, pending real engine contracts.
- No retry/backoff on failed engine calls; a failed apply simply reports failure and the next scheduler tick will just try again.
- The scheduler ticks every active workflow of every tenant on the same fixed interval — no per-workflow cadence, no backoff for workflows that keep failing to reach an engine, no prioritization by `recommend_workflow_sequence()`'s scoring (it re-evaluates everything, unconditionally, every tick). Good enough for a single orchestrator instance at prototype scale; would need real scheduling logic before this runs against dozens of tenants with many workflows each.
- Single in-process scheduler only — running more than one orchestrator instance would tick the same workflows redundantly from each instance (no distributed lock). Fine until there's a reason to run more than one instance.
- **Persistence is a snapshot, not a transaction log.** A hard crash between saves (worst case: one `OS42_SCHEDULER_INTERVAL_SECONDS` interval) loses whatever changed since the last save. No concurrent-writer safety beyond the atomic rename (fine for one orchestrator process; would race with a second one writing the same path).
- The whole snapshot is rewritten on every save (no incremental/delta writes) — at real scale (many tenants, long metric history) this would eventually need to become an actual database rather than "serialize everything to JSON every 5 minutes."
- Metrics and decisions accumulate forever with no retention/pruning, in memory and in the snapshot alike — long-running processes would need a cutoff policy eventually.

## Next Steps

Remaining open item from the original Phase D roadmap:

1. **Goal-based workflow selection** — a tenant states an objective, orchestrator picks/sequences workflows toward it. The most immediately actionable slice: make the scheduler call `recommend_workflow_sequence()` and prioritize/skip accordingly instead of ticking every workflow equally every pass.
