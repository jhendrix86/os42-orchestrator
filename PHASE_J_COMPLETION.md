# Phase J Completion: Extending Reconciliation to the 5 Stage-4-Real Engines

**Status**: CODE COMPLETE — mock-harness test written, live end-to-end verification handed to the Acer/Nexus session (no Python toolchain on HP-14)
**Date**: 2026-08-30
**Box**: HP-14 (`hp-14` / hostname `DESKTOP-9LVP180`), roadmap Step 9
**Deliverables**: four new real-verified workflow templates in `app/models/workflows.py`, `test_phase_j_reconciliation.py`, `CLAUDE.md` Phase J addendum, this doc

## Why This Phase Exists

Roadmap Step 9 ("Extend os42-orchestrator's reconciliation"): once Step 5's
engines have real endpoints, extend Phase I's real-verified-workflow-template
pattern to them, and re-check `DecisionExecutor.ACTION_ENGINE_MAP`'s 5
unbacked actions.

Phase H reconciled `content-engine`; Phase I added `marketing-automation-engine`
and `revenue-operations-engine`. This phase covers the **five engines the
2026-08-12/15 "6 remaining mock engines made real" work made functional and
the 2026-08-29 Nexus stale-image rebuild confirmed are actually deployed
(not just real in source)**: `notification`, `integration`, `sales`,
`customer-support`, `analytics`. Before 2026-08-29 their running containers
were still serving mock code, so a template built against their source
couldn't be trusted to match the live fleet; now it can.

## Provenance note

A prior HP-14 session drafted the four templates + `test_phase_j_reconciliation.py`
and left them uncommitted (working tree only, no `CLAUDE.md` addendum — which
the test's own docstring referenced). This session re-verified every step
against the current sibling-repo router code from scratch (below), wrote the
missing `CLAUDE.md` addendum + this doc, and committed. Nothing in the
templates was trusted on the prior session's say-so.

## What Was Built

Four new factory functions in `app/models/workflows.py`, each a strict
linear step sequence using the established `add_step(engine, action, params,
step_id=)` + `$steps.<id>.<field>` path-templating pattern.

### 1. `create_support_escalation_workflow()` — support + notification ✓

`POST /tickets/create` → `POST /tickets/$steps.create_ticket.id/escalate`
→ `POST /notifications/send`.

Verified against `customer-support-engine/app/routers/tickets.py` and
`notification-engine/app/routers/notifications.py` (both files' own
docstrings: "real DB-backed CRUD"):
- `POST /tickets/create` (prefix `/tickets`) persists a real `Ticket` +
  get-or-creates a `Customer` by email. Payload fields
  `customer_name / customer_email / subject / message / priority` match
  `CreateTicketRequest` exactly. `priority` ∈ `TicketPriority`
  = critical/high/medium/low (`app/models/ticket.py`).
- `POST /tickets/{id}/escalate` takes **no body** and only sets
  `status = TicketStatus.ESCALATED` — it notifies nobody. That is why this
  workflow has a distinct third step; the escalate call is not a formality.
- `POST /notifications/send` (prefix `/notifications`): `channels` is a
  `List[NotificationChannel]` (enum has `email`), real delivery is attempted
  on `channels[0]` via `app/services/delivery/dispatch.py` with an honest
  per-channel success/failure. `recipient / recipient_type / subject /
  message` match `SendNotificationRequest`.

### 2. `create_integration_sync_workflow()` — integration ✓

`POST /integrations/create` → `POST /integrations/$steps.create_integration.id/sync`.

Verified against `integration-engine/app/routers/integrations.py` +
`app/services/sync_engine.py`:
- `POST /integrations/create`: `config` is a **required** dict;
  `integration_type` ∈ `IntegrationType` = crm/marketing/analytics/
  productivity/custom. Template passes `integration_type="custom"` and
  `config={"sync_url": ...}`.
- `POST /integrations/{id}/sync` creates a real `SyncJob` and runs it via
  `run_sync_job()`, which makes a **genuine outbound GET** to
  `integration.config["sync_url"]` (`direction="pull"` → GET). No per-vendor
  SDK exists for any provider this schema anticipates, so "real" = a real
  HTTP call to whatever was configured. It returns `SyncStatus.FAILED` (but
  still HTTP 200) with `"no 'sync_url' configured"` when config carries none
  — the template always supplies one for exactly this reason.

### 3. `create_analytics_report_workflow()` — analytics ✓

`POST /reports/` → `POST /reports/$steps.create_report.id/generate`.

Verified against `analytics-engine/app/routers/reports.py`:
- The create route is `@router.post("/")` under prefix `/reports`, so the
  action string is `"reports/"` **with the trailing slash** — `"reports"`
  without it hits FastAPI's 307 redirect, not the handler (same gotcha
  Phase I hit with `customers/`). Confirmed by reading the decorator.
- Payload `name / report_type / metric_names / period_days` matches
  `CreateReportRequest` (`report_type` default `"metrics_summary"`).
- `POST /reports/{id}/generate` computes a real aggregate over recorded
  `Metric` rows and stores the numbers in `extra_metadata` — it does **not**
  claim a PDF/CSV at a fake `output_url` (no file-gen infra in this engine).
  Empty `metric_names` or an empty period → a real report with zero results,
  not a failure.

### 4. `create_lead_conversion_workflow()` — sales ✓

`POST /leads/create` → `POST /leads/$steps.create_lead.id/convert`.

Verified against `sales-engine/app/routers/leads.py`:
- `POST /leads/create`: `name / email / estimated_value` match
  `CreateLeadRequest` (rest optional).
- `POST /leads/{id}/convert`: body is `ConvertLeadRequest` with `deal_name`
  and `stage_id` both optional (the whole body defaults to
  `ConvertLeadRequest()`), so a `{}` params dict is valid. Convert creates a
  real `Deal` row in the pipeline (`app/models/pipeline.py`), updates the
  lead's status/stage, and defaults the deal name to
  `f"{lead.company or lead.name} Deal"` and the stage to the pipeline's
  first real stage when omitted.

### `test_phase_j_reconciliation.py` (new)

Same real-subprocess harness as Phase F/H/I, generalized so one workflow can
redirect **two** `ENGINE_URLS` entries at once (test 1 spans support +
notification). Each test starts a real `mock_engines.py`, points the
relevant engine URL(s) at it, then drives the real HTTP API
(`POST /tenants` → `POST /workflows/create` → `POST /workflows/{id}/execute`)
and asserts `execution.status == "completed"` with no `status: "failed"`
step result. `mock_engines.py`'s existing catch-all (`POST /{action:path}`
→ `{"status":"ok","id":"mock-…"}`) already answers every new action path and
supplies the `id` field the `$steps.*.id` templating needs — no change to it.

**This test was NOT run on HP-14** — the box has no Python/Node installed and
only ~6.7 GB free disk, too tight to responsibly stand up a venv. It is
written to the exact pattern of the passing Phase H/I tests. The Acer session
(integration verifier, has SSH deploy access to Nexus) will rebuild
`os42-orchestrator` on Nexus and run the four templates **against the live
engines** — the check `mock_engines.py` structurally cannot give.

## `DecisionExecutor.ACTION_ENGINE_MAP` — re-checked, no change

Grepped the **current** `marketing-automation-engine` and `content-engine`
routers for the 5 unbacked actions (`scale_budget`, `adjust_frequency`,
`change_channel`, `adjust_timing`, `change_format`). None exists. The real
marketing routes are all "do-the-thing" actions
(`campaigns/{id}/launch`, `social/{id}/publish`, `email/{id}/send`) — none is
"adjust a parameter of a running thing". `campaigns/create` takes a `budget`
field but there is no scale-an-existing-campaign endpoint.

One near-miss, **deliberately not force-mapped**: `content-engine`'s
`POST /content/{id}/repurpose` is real, but it is content transformation
(one pillar → N derivative formats) needing a `{content_id}` path param + its
own body — it does not fit `DecisionExecutor`'s flat `POST {engine}/{action}`
+ decision-payload contract. Mapping `CHANGE_FORMAT` → it would be inventing
a contract, exactly the 2026-08-10 drift. `ACTION_ENGINE_MAP` left as-is
(flagged; honest `status: "failed"` until real engine-side work lands).

## What Remains Unreconciled (not attempted here)

- `create_daily_optimization_workflow()` / `create_audience_growth_workflow()`
  — confirmed by Phase H/I to have no meaningful real backing; unchanged.
- `monitoring`, `governance` — no workflow template references them yet;
  same as Phase I's conclusion, there's no business process that needs one
  today. Not a wrong contract to fix — a workflow to invent.
- Live end-to-end run of the four Phase J templates — handed to Acer/Nexus.

## Verification Checklist

- [x] Every new step verified against **current** sibling-repo router source (path, prefix, request field names, enum values), not assumed or trusted from the prior draft
- [x] Honest failure modes noted where real (notification delivery unconfigured, integration `sync_url` unreachable) rather than glossed over
- [x] `ACTION_ENGINE_MAP`'s 5 unbacked actions re-checked against current routers; near-miss documented and correctly declined
- [x] Test written to the passing Phase H/I pattern
- [ ] Templates execute end-to-end — **pending Acer's live run on Nexus** (no Python on HP-14)
- [x] `CLAUDE.md` updated with the Phase J addendum + table its own test referenced
- [x] No new engine URL, action name, or contract added without checking real router code first
