# os42-orchestrator

Central coordination layer for the OS42 engineering fleet — the piece that
runs multi-step business workflows across the standalone `*-engine`
services (content, marketing, sales, revenue-ops, etc.) and, on a
background schedule, decides whether to pause/resume/re-sequence them
based on real performance data.

Part of the larger OS42 fleet at `CascadeProjects/` (see the root
`OS42_ROADMAP.md` and `HANDOFF.md` for fleet-wide status — those are the
authoritative, actively-maintained docs, not this README).

## What's real here today

- **`WorkflowExecutor`** — runs a workflow's DSL steps against the real
  engines over HTTP, with `$steps.x.y` result templating between steps.
  Verified against content-engine, marketing-automation-engine, and
  revenue-operations-engine, plus 4 workflow templates (support,
  integration, analytics, sales).
- **`AutonomousScheduler`** — a background loop (interval:
  `OS42_SCHEDULER_INTERVAL_SECONDS`, default 300s) that re-evaluates every
  tenant's active workflows and applies whatever `OptimizationEngine`
  decides.
- **`OptimizationEngine`** — 6 metric-driven rules over a
  `PerformanceAnalysis` snapshot, producing one of 8 possible actions with
  a confidence score and per-tenant decision history.
- **`DecisionExecutor`** — turns a decision into either
  orchestrator-internal state (`PAUSE`/`RESUME` — real) or an outbound
  engine call. The other 6 actions (`SCALE_BUDGET`, `CHANGE_FORMAT`, etc.)
  map to engine endpoints that don't exist yet fleet-wide and honestly
  report `status: "failed"` rather than being force-mapped to a near-miss
  route — see `CLAUDE.md` for why.
- **`MetricsAggregator`** — real conversion/engagement/trend math, but
  currently only fed by `POST /optimization/metrics/record` /
  `/optimization/metrics/batch`, which nothing in the fleet calls yet
  (tracked as Stage 5 gap G1 in the root `STAGE5_PLAN.md`).
- **`TenantRegistry`** (`app/services/tenancy.py`) — enforces per-tenant
  isolation on this repo's own metrics/decisions/workflows/goals. Answers
  a different question than `unkey-auth` (which just validates "is this
  key valid") — see `CLAUDE.md` before assuming one should replace the
  other.

## Running it

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`app/config.py`'s `ENGINE_URLS` holds the real port map for every peer
engine (env-overridable, e.g. `CONTENT_ENGINE_URL`). `/docs` is disabled
unless `DEBUG=true` (see `SECURITY_REVIEW.md` at the fleet root).

## Testing

```bash
pytest -q
```

Tests are organized by build phase (`test_phase_b.py` ... `test_phase_j_reconciliation.py`,
plus `test_phase_f_live_integration.py`, which needs real engines
reachable to pass — see each `PHASE_*_COMPLETION.md` for what each phase
actually verified).

## Before you touch ports, engine contracts, or auth

Read `CLAUDE.md` in this repo first — it documents real drift that was
found and fixed on 2026-08-10 (wrong ports, invented action paths with no
real backing, a tenancy-vs-unkey-auth false equivalence) so it doesn't get
repeated.
