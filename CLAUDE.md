# os42-orchestrator — read this before touching ports, engine contracts, or auth

This repo is part of the larger OS42 fleet at `C:\Users\Jonat\CascadeProjects\`.
It was built across several sessions using its own self-referential
"Phase A-G" labels (see `PHASE_A_COMPLETION.md` through `PHASE_G_COMPLETION.md`)
— but those phases were never cross-checked against the REAL sibling engines
until a reconciliation pass on 2026-08-10 found real, significant drift. That
happened because whatever set up context for the sessions that built Phases
A-G only surfaced this repo's own internal docs, never the root-level
cross-session continuity files below. Don't repeat that.

**Before assuming anything about the other engines (ports, endpoint paths,
auth), read these two files at the CascadeProjects root — they are the
authoritative, actively-maintained status docs, not this repo:**

1. `../HANDOFF.md` — "read this first if you're a new AI/human picking this
   up cold." Has the real port map, current Stage status, and traps found
   the hard way (some overlap with the list below, but it's kept more current).
2. `../OS42_REPAIR_PLAN.md` — the live Tier/Stage repair checklist for the
   engine fleet.

## What was found wrong (2026-08-10 reconciliation)

- 6 of 11 `app/config.py` `ENGINE_URLS` ports were wrong — pointed at a
  different, live engine instead of the intended one, rather than failing
  cleanly.
- `pricing-intelligence-system` isn't an HTTP service at all — it's a CLI
  batch-job runner (`argparse`, `docker compose run --monitor`). It was
  wrongly listed as an HTTP peer to call.
- Every one of the DSL's invented action paths (`/create`, `/repurpose`,
  `/scale_budget`, etc. — see `app/models/workflows.py` and
  `app/services/decision_executor.py`'s `ACTION_ENGINE_MAP`) was wrong as a
  literal route. Real engines use resource-scoped REST paths
  (`POST /content/{id}/repurpose`, `POST /campaigns/{id}/launch`). Several
  invented actions — `scale_budget`, `adjust_frequency`, `change_format`,
  `change_channel`, `adjust_timing`, `create_offer`, `create_nurture`,
  `update_strategy` — have **no real implementation anywhere in the fleet**.
  Not a path bug: nothing to call yet, full stop.
- **Correction, same day**: this file originally claimed this repo's tenant/
  API-key auth (`app/services/tenancy.py`) "duplicates" `unkey-auth` and
  should be replaced by it. On closer inspection that's wrong — don't do it.
  `unkey-auth` answers one question, is this key valid (fail-open if
  unconfigured); `TenantRegistry` answers a different one, which tenant's
  data does this request see, and enforces isolation across this repo's own
  metrics/decisions/workflows/goals. None of the 3 engines piloted on
  `unkey-auth` (content, marketing, revenue) have any per-tenant data
  isolation of their own — Stage 4 hasn't started fleet-wide. Replacing
  `TenantRegistry` would delete real, working functionality nothing else in
  the fleet provides, to adopt a mechanism that solves a narrower problem.
  Outbound auth (this orchestrator calling the engines) already got real
  `UNKEY_API_KEY`/`engine_auth_headers()` support in the Phase H fix - that
  part was correct and stays. It's specifically *inbound* auth (clients
  calling this orchestrator) that should NOT be swapped to unkey-auth.

## Resolved: WorkflowExecutor vs. baselayer/core_loop (2026-08-10)

The Phase H completion doc left open whether `app/services/workflow_executor.py`'s
`WorkflowExecutor` should be replaced by `baselayer/backend/src/baselayer/core_loop`'s
more mature `WorkflowEngine`/`WorkflowExecutor`/`WorkflowScheduler` trio (real
DB persistence, dependency-graph parallel execution, exponential/linear/fixed
retry/backoff, cron scheduling). Researched properly (not guessed) and
**resolved: keep this repo's `WorkflowExecutor` as-is.** Don't migrate it.

Why, concretely:

- baselayer's one step type that could call an external HTTP service
  (`type: webhook`) is a stub in both `engine.py` and `executor.py` — the
  comment literally says `# In real implementation, this would use httpx or
  aiohttp` and never does. Grepping the whole `core_loop/` subsystem for
  `httpx|requests\.|aiohttp` turns up only that dead comment. It cannot call
  a named sibling engine over HTTP at all today.
- It has no equivalent of `$steps.step_id.field` parameter resolution or the
  action-path templating (`content/$steps.create_pillar.id/repurpose`) that
  `create_content_pillar_workflow` depends on for 4 of its 5 steps. Step
  data flow there is just a raw `context` dict handed to a (stub) handler.
- Its `Workflow`/`WorkflowExecution` models have **no `tenant_id` column at
  all** — weaker tenant isolation than what this repo already enforces on
  every route via `app.state.active_workflows[tenant_id][workflow_id]`.
  Migrating would mean pointing multi-tenant traffic at a system with no
  tenant column to isolate it.
- Its two real advantages (dependency-graph parallel steps, cron scheduling)
  solve a problem `create_content_pillar_workflow` — the one real, verified
  workflow — doesn't have: it's a strict 5-step linear pipeline, not a DAG.

Net: migrating would mean rebuilding this repo's two load-bearing
capabilities (HTTP-calling, `$steps.x.y` templating) from scratch inside a
system that has neither today and has weaker tenant isolation than what
would be left behind. If real parallel steps, retries, or cron scheduling
are ever needed, add them narrowly to `WorkflowExecutor`/`AutonomousScheduler`
(baselayer's backoff-calculation pattern is worth borrowing) rather than
adopting an engine whose HTTP-calling primitive doesn't exist yet.

## Phase J reconciliation (2026-08-30, HP-14) — the 5 Stage-4-real engines

Extended Phase H/I's real-verified-workflow-template pattern to the five
engines the 2026-08-12/15 "6 remaining mock engines made real" work + the
2026-08-29 stale-image rebuild made genuinely trustworthy: **notification,
integration, sales, customer-support, analytics**. Four new templates in
`app/models/workflows.py`, each step verified against the *current* router
code in the sibling repo (not guessed), test in
`test_phase_j_reconciliation.py` (same mock-engine harness as Phase F/H/I —
proves the orchestrator's HTTP mechanics + `$steps.x.y` path templating;
real end-to-end against the live fleet is the Acer session's follow-up on
Nexus):

| template | engines | real routes verified against |
|----------|---------|------------------------------|
| `create_support_escalation_workflow` | support + notification | `POST /tickets/create` → `POST /tickets/{id}/escalate` (`customer-support-engine/app/routers/tickets.py`; escalate only flips `status=ESCALATED`, notifies nobody — the 3rd step exists for that reason), `POST /notifications/send` (`notification-engine/app/routers/notifications.py`; `channels` is `List[NotificationChannel]`, real delivery attempted on channel[0]) |
| `create_integration_sync_workflow` | integration | `POST /integrations/create` (`config` is required; `integration_type` ∈ crm/marketing/analytics/productivity/custom) → `POST /integrations/{id}/sync` (`integration-engine/app/services/sync_engine.py` makes a real GET to `config["sync_url"]`; honest FAIL if none — template always supplies one) |
| `create_analytics_report_workflow` | analytics | `POST /reports/` **(trailing slash — real route is `@router.post("/")` under prefix `/reports`; no-slash gets a 307)** → `POST /reports/{id}/generate` (`analytics-engine/app/routers/reports.py`; computes a real aggregate over `Metric` rows, stores numbers in `extra_metadata`, no fake `output_url`) |
| `create_lead_conversion_workflow` | sales | `POST /leads/create` → `POST /leads/{id}/convert` (`sales-engine/app/routers/leads.py`; convert creates a real `Deal` row + transitions the lead, `deal_name`/`stage_id` both optional with sensible defaults) |

**`DecisionExecutor.ACTION_ENGINE_MAP`'s 5 unbacked actions — re-checked, still nothing to point at.**
Grepped current `marketing-automation-engine` and `content-engine` routers:
no `scale_budget` / `adjust_frequency` / `change_channel` / `adjust_timing` /
`change_format` endpoint exists. The real marketing routes are all
"do-the-thing" actions (`campaigns/{id}/launch`, `social/{id}/publish`,
`email/{id}/send`) — none is "adjust a parameter of a running thing".
`campaigns/create` accepts a `budget` field, but there's no
scale-an-existing-campaign endpoint, so `SCALE_BUDGET` still has nothing.
**One near-miss, deliberately NOT force-mapped:** `content-engine`'s
`POST /content/{id}/repurpose` is real, but it's a content-transformation
endpoint (one pillar → N derivative formats) needing a `{content_id}` path
param + its own body — it does not fit `DecisionExecutor`'s flat
`POST {engine}/{action}` + decision-payload calling contract. Mapping
`CHANGE_FORMAT` → it would be inventing a contract, exactly what the
2026-08-10 drift was. `ACTION_ENGINE_MAP` left as-is (flagged, honest
`status: "failed"` until real engine-side work adds these).

## Rule going forward

Never add a new engine URL, action name, or assumed contract to this repo
without first checking the real engine's actual router code — or, if you're
the one making a contract real, update `../HANDOFF.md`/`../OS42_REPAIR_PLAN.md`
so the next session doesn't have to rediscover it. Guessing is exactly how
the drift above happened, twice (once building it, and HANDOFF.md's own
Stage 3 status was already stale by the time this reconciliation checked it).
