# Phase I Completion: Extending Reconciliation to Marketing + Revenue Engines

**Status**: COMPLETE
**Date**: 2026-08-11
**Deliverables**: two new real-verified workflow templates (`create_lead_nurture_email_workflow`, `create_customer_subscription_workflow`), a real bug fix in `WorkflowExecutor`, `test_phase_i_reconciliation.py`

## Why This Phase Exists

Per `OS42_REPAIR_PLAN.md`'s "Plan update (2026-08-10)" recommended order, item 4 was "extend os42-orchestrator's Phase H reconciliation to the remaining 9 engines." Phase H's own same-day follow-up had already checked the two *pre-existing* unverified templates (`create_daily_optimization_workflow`, `create_audience_growth_workflow`) against `analytics-engine` and `marketing-automation-engine`'s real router code and concluded, honestly, that neither is meaningfully reconcilable today — the endpoints they'd need (`identify_winners`, `create_nurture`, `segment_audience`, `track_campaign`, etc.) don't exist anywhere in the fleet, and the one endpoint that does exist for either (`campaigns/{id}/launch`) is itself a server-side stub.

So "extending reconciliation" couldn't mean re-checking those two templates again — that would just reconfirm the same conclusion. Instead, this phase builds **new** templates around endpoints that genuinely are real today, on the two engines Stage 1/2 already made functional (not mock stubs): marketing-automation-engine's real lead/campaign/email flow (real SendGrid sending, built 2026-08-08/09) and revenue-operations-engine's real customer/subscription flow (a real proxy to baselayer's income_engine, built 2026-08-09). This is the same verify-against-real-router-code discipline Phase H established, applied to engines nothing in this repo had touched before.

## What Was Built

### 1. `create_lead_nurture_email_workflow()` (new, `app/models/workflows.py`) ✓

4 steps, all verified against real marketing-automation-engine router code (`leads.py`, `campaigns.py`, `email.py`):
`POST /leads/create` → `POST /campaigns/create` → `POST /email/create` → `POST /email/{id}/send`.

All four are real: the first three each persist a real database row; the fourth genuinely calls SendGrid per recipient and honestly reports failure without a configured `SENDGRID_API_KEY`, matching content-engine's distribution/execute honesty contract. Sending with no explicit recipient list (this workflow's default) sends to every lead on file, which always includes the lead the workflow itself just created.

`campaigns/{id}/launch` was deliberately **not** used — it's a real, callable path, but its own server-side implementation is a stub, and launching isn't required to send an email campaign under a draft campaign.

### 2. `create_customer_subscription_workflow()` (new, `app/models/workflows.py`) ✓

2 steps, verified against real revenue-operations-engine router code (`customers.py`, `subscriptions.py`):
`POST /customers/` → `POST /subscriptions/create`.

`POST /customers/` persists a real `Customer` row. `POST /subscriptions/create` does not write locally — it's a thin, honest proxy to baselayer's income_engine (`app/services/baselayer_client.py`); against the real engine it reports a clear "not configured" failure until a real baselayer service account exists (per `../HANDOFF.md`'s "Credentials / accounts status"), not a fabricated success.

One real routing detail worth flagging: the customer-create route is registered as `"/"` under the `/customers` prefix, so the action string must be `"customers/"` with a trailing slash — `"customers"` without it hits FastAPI's 307 redirect-slash behavior instead of the real handler (confirmed by reading the route decorator directly, not guessed).

### 2b. Real bug found and fixed while testing: `WorkflowExecutor.disconnect()` never reset `self.client` ✓

Writing `test_phase_i_reconciliation.py`'s second test surfaced a real bug, not a test-authoring mistake: `app/main.py` holds `workflow_executor = WorkflowExecutor(ENGINE_URLS)` as a **module-level singleton**, connected on app startup and disconnected on app shutdown via the FastAPI lifespan. `WorkflowExecutor.disconnect()` called `self.client.aclose()` but never set `self.client = None` — so a second `connect()` call (a second app-lifespan cycle against the same singleton) saw `self.client` was still non-`None` and skipped creating a fresh one, silently reusing an already-closed `httpx.AsyncClient`. Every call through it then failed with `"Cannot send a request, as the client has been closed."`

Fixed in `app/services/workflow_executor.py`: `disconnect()` now sets `self.client = None` after closing (when it owns the client). This wouldn't manifest in a real single-process deployment (the lifespan normally runs once), but is a real correctness bug in the connect/disconnect contract itself, and was surfaced entirely by real execution — the exact "verify by running it, not by reading it" discipline this whole project is built on.

### 3. `test_phase_i_reconciliation.py` (new) ✓

Same real-subprocess pattern Phase F introduced and Phase H reused: starts a real `mock_engines.py` subprocess, points one `ENGINE_URLS` entry at it, creates + executes the workflow through the real HTTP API (`POST /workflows/create`, `POST /workflows/{id}/execute`), and asserts every step completed without a `status: failed` result. `mock_engines.py`'s existing catch-all handler (any path, generic success response) needed no changes — it already answers whatever new action paths a workflow's steps call.

Two test functions, both passing:
1. `create_lead_nurture_email_workflow()` against a mocked marketing engine — first time this template has ever executed.
2. `create_customer_subscription_workflow()` against a mocked revenue engine — first time this template has ever executed; this is the one that caught the `disconnect()` bug above before the fix.

**Regression check** — full existing suite still green after the fix: all 13 prior test files (including `test_phase_h_reconciliation.py`) plus `pytest tests/`, run via `run_all_tests.py`, 14/14.

## What Remains Unreconciled (unchanged from Phase H, not attempted here)

- `create_daily_optimization_workflow()` / `create_audience_growth_workflow()` — confirmed by Phase H's own follow-up to have no meaningful real backing; not re-attempted here, see their docstrings.
- `DecisionExecutor.ACTION_ENGINE_MAP`'s 5 actions (`scale_budget`, `adjust_frequency`, `change_format`, `change_channel`, `adjust_timing`) — still nothing real to call anywhere in the fleet, already flagged by Phase H, unchanged.
- `monitoring`, `notification`, `integration`, `support`, `governance`, `sales`, `analytics` (as a standalone workflow target, distinct from content-engine's own analytics router) — still not referenced by any workflow template in this repo. Not a wrong assumption to correct (same conclusion Phase H reached) — there's simply no workflow yet that needs them. Building one would mean inventing a business process first, not fixing a contract.

## Verification Checklist

- [x] Every new step verified against real router source (path, prefix, request/response field names), not assumed
- [x] Honest failure modes noted where real (SendGrid unconfigured, baselayer unconfigured) rather than glossed over
- [x] Both new workflows execute successfully end-to-end against `mock_engines.py` for the first time
- [x] A real bug found via actual execution (not code reading) was fixed, not worked around
- [x] All prior-phase tests still pass unmodified after the fix
- [x] No new engine URL, action name, or contract added without checking real router code first (per `CLAUDE.md`'s rule)
