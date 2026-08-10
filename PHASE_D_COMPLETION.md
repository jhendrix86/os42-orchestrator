# Phase D Completion (Part 1): Decision Execution

**Status**: COMPLETE (this slice — see Scope note below)
**Date**: 2026-08-09
**Deliverables**: DecisionExecutor service, recommend+apply endpoint, per-workflow decision audit trail

## Scope Note

Phase D was left explicitly "TBD" in PHASE_A_COMPLETION.md's original roadmap ("Strategic decision making / Goal-based workflow selection / Autonomous scaling and optimization / TBD pending Stage 3-4 results"). Rather than guess at that whole surface, this pass covers one concrete, previously-flagged gap: **OptimizationEngine decisions were generated and recorded but nothing ever acted on them** ("Decision execution not implemented" — PHASE_B_COMPLETION.md tech debt). Goal-based workflow selection and a real persistence layer remain open for a later pass.

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

## Test Results

**test_phase_d.py** — 4 test groups, all passing:
1. **PAUSE/RESUME**: directly flips `workflow["status"]`, confirmed no engine call happens (`engine_called is None`), confirmed a missing workflow record doesn't crash
2. **Engine call success**: `SCALE_BUDGET` against a fake in-process ASGI "engine" (via `httpx.ASGITransport`, no real network) — confirms the right endpoint (`marketing/scale_budget`) is hit with a payload containing `workflow_id`, `tenant_id`, and the decision's own parameters (`budget_increase_percent: 50`)
3. **Engine call failure**: `SCALE_BUDGET` against an intentionally unreachable port — confirms `status: "failed"` is returned, not an exception
4. **Full HTTP flow** via `TestClient` against the real `/optimization/optimize/{id}/apply` endpoint, with real (unreachable) `ENGINE_URLS`:
   - Declining-conversion workflow → `PAUSE` decision → `execution.status: "applied"` → `GET /workflows/{id}` shows `status: "paused"` and one `applied_decisions` entry
   - High-conversion workflow → `SCALE_BUDGET` decision → `execution.status: "failed"` (marketing engine isn't running) — endpoint still returns 200, proving the failure is absorbed rather than propagated as a 500
   - Apply against a `workflow_id` that was never created via `/workflows/create` → still 200, no crash

**Regression check** — full existing suite still green: `test_phase_b.py`, `test_phase_c.py`, `test_phase_c_api.py`, `test_dashboard.py`, `test_e2e_standalone.py`, `pytest tests/` (3 passed).

## Code Structure

```
os42-orchestrator/
├── app/
│   ├── config.py (new, 22 lines)
│   │   - ENGINE_URLS (moved out of main.py)
│   ├── services/
│   │   └── decision_executor.py (new, 145 lines)
│   │       - ACTION_ENGINE_MAP, ExecutionResult, DecisionExecutor
│   ├── routes/
│   │   └── optimization.py (modified)
│   │       - POST /optimize/{workflow_id}/apply
│   └── main.py (modified)
│       - imports ENGINE_URLS from app.config instead of defining it
│       - create_workflow() initializes applied_decisions: []
├── test_phase_d.py (new, 230 lines)

Git History (this phase):
- (pending commit): Phase D (part 1): Decision execution
```

## Key Technical Decisions

1. **PAUSE/RESUME never touch the network.** Whether the orchestrator keeps scheduling a workflow is purely its own bookkeeping — `should_run_workflow()` already existed for this in Phase B, it just never updated the actual workflow record until now.
2. **A per-call `DecisionExecutor` + `httpx.AsyncClient`, not a shared singleton.** Applying a decision is a low-frequency action (not a hot path), and this keeps the client's lifecycle trivial to reason about — construct, use, close — rather than needing app-lifespan wiring like the still-unused `WorkflowExecutor` has half-set-up. Explicitly called out as a tradeoff, not free.
3. **Engine failures are data, not exceptions.** With zero of the 11 sibling engines actually running in this environment, "engine unreachable" is the common case today, not an edge case — the endpoint has to degrade gracefully or every apply call would 500.
4. **Action → engine mapping is invented, matching the rest of the DSL.** No sibling engine repo defines a `/scale_budget` contract yet — same maturity level as `workflows.py`'s existing step definitions (`content/repurpose`, `revenue/create_offer`, etc.), which were never real either. Real engine integration is still future work across the whole orchestrator, not specific to this phase.
5. **`app/config.py` split-out was necessary, not incidental.** The new apply endpoint lives in `routes/optimization.py` and needs `ENGINE_URLS`; importing it from `main.py` would be circular since `main.py` already imports the optimization router.

## Verification Checklist

- [x] OptimizationDecisions can be applied, not just recorded
- [x] PAUSE/RESUME correctly update workflow state
- [x] Engine-owned actions call the correct engine with the correct payload (proven against a fake engine)
- [x] Engine unreachability degrades gracefully (proven against both a closed port and the real, not-running sibling engines)
- [x] Applied decisions are auditable per workflow (`applied_decisions` on the workflow record)
- [x] Tenant isolation from Phase C still holds on the new endpoint
- [x] All prior-phase tests still pass

## Technical Debt / Notes

- No automatic/scheduled invocation yet — `/apply` has to be called explicitly (by a human, a script, or eventually a scheduler). Autonomous *triggering* (a background loop calling apply for the tenant's `recommend_workflow_sequence()` output on a timer) is a natural next increment, not built here.
- `ACTION_ENGINE_MAP` endpoint names are invented, pending real engine contracts.
- Still in-memory throughout (workflows, metrics, decisions, applied_decisions) — a restart forgets everything, as previously noted in Phase B/C tech debt.
- No retry/backoff on failed engine calls; a failed apply simply reports failure and stops.

## Next Steps

Remaining open items from the original Phase D roadmap:
1. **Real persistence** — tenant registry, metrics, decisions, and now applied_decisions are all still in-memory
2. **Goal-based workflow selection** — a tenant states an objective, orchestrator picks/sequences workflows toward it
3. **Autonomous triggering** — a scheduler that calls the new `/apply` endpoint on its own cadence, using `recommend_workflow_sequence()` to decide what to run next
