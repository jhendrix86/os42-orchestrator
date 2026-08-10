# Phase H Completion: Reconciliation with the Real Engine Fleet

**Status**: COMPLETE (mechanical fixes only — see Scope note)
**Date**: 2026-08-10
**Deliverables**: corrected engine ports, real-verified content pillar workflow, path-parameter templating, optional Unkey auth, `CLAUDE.md` + `HANDOFF.md` prevention measures

## Why This Phase Exists

Every phase through G was built inside os42-orchestrator's own self-referential "Phase A-G" labels, never cross-checked against the actual sibling engine fleet or the workspace's real cross-session continuity document (`HANDOFF.md`). Asked "are you still going by the original 5 phase plan," the honest answer turned out to be: there isn't one plan, there are two (`OS42_IMPLEMENTATION_PLAN.md` and the actually-active `OS42_REPAIR_PLAN.md`/`HANDOFF.md`), and this repo's work was disconnected from both.

A reconciliation pass (two research agents plus direct reads of real router code) found concrete, verifiable drift:

- 6 of 11 hardcoded `ENGINE_URLS` ports were wrong — pointed at a different, live engine instead of the intended one, rather than failing cleanly.
- `pricing-intelligence-system` was wrongly treated as an HTTP peer — it's a CLI batch-job runner with no FastAPI app at all.
- Every one of the DSL's 18 invented action paths was wrong as a literal route. Real engines use resource-scoped, ID-templated REST paths (`POST /content/{id}/repurpose`), not the flat action names this repo invented.
- The orchestrator's own tenant/API-key auth duplicates `unkey-auth`, a real package already wired into 3 engines.

Also found, genuinely good news: `OptimizationEngine`/`DecisionExecutor`/`AutonomousScheduler` (Phase D) have no equivalent anywhere else in the workspace — they solve business-metric-driven optimization, not infrastructure-failure retry (which is what `autonomy-events`/`baselayer` actually do). That work isn't wasted, just disconnected from real engine contracts until this phase.

## Scope Note

Per user direction, this phase covers the **mechanical fixes** — ports, dropping the invalid HTTP peer, remapping the handful of actions with real verified endpoints, and adding auth-header support so calls don't silently break once real credentials exist. Two bigger, more invasive questions were deliberately deferred, not resolved here:

1. **Replacing this repo's custom tenant auth with real `unkey-auth`** — bigger change, touches every route's auth dependency and the whole `Tenant` model.
2. **Whether `WorkflowExecutor` should keep existing** given `baselayer/core_loop`'s more mature, DB-persisted, dependency-graph workflow engine has real conceptual overlap (though at a different layer/scope) — a real architecture question, not a bug fix.

## What Was Built

### 1. Prevention (new) ✓

- `os42-orchestrator/CLAUDE.md` — auto-loaded by any future Claude Code session working in this directory; states the full list of what was wrong and the rule ("never add a new engine URL/action without checking real router code first").
- `HANDOFF.md` at the CascadeProjects root updated: corrected headline, added a 2026-08-10 Session Log entry, and fixed its own stale "Stage 3 not started" line (real work has landed per `baselayer` commit `5c51a88` and `STAGE3_COMPLETION_REPORT.md`, found during this reconciliation).
- Persistent memory updated (`always_read_handoff_first.md`) so a future session of mine checks `HANDOFF.md` before repeating this.

### 2. Corrected `app/config.py` ✓

- 6 of 11 ports fixed: content 8038→8040, monitoring 8044→8043, notification 8045→8037, integration 8040→8044, support 8037→8038, governance 8043→8033 (4 were already right: marketing, analytics, sales, revenue).
- `pricing` removed entirely — not a valid HTTP peer, confirmed by reading its actual `main.py` (`argparse` CLI, no FastAPI app, no `uvicorn`).
- Added `UNKEY_API_KEY` (opt-in, unset by default) and `engine_auth_headers()` — returns `{"Authorization": "Bearer ..."}` when configured, `{}` otherwise.

### 3. `WorkflowExecutor` action-path templating (new) ✓

- Real engine endpoints are resource-scoped by ID in the URL path (`/content/{id}/repurpose`), not just the request body — the DSL had no mechanism to substitute a resolved value into the action string itself, only into `params`.
- Added `_resolve_action_path()`: the same `$steps.step_id.field` syntax `_resolve_params` already used, now also applied to the `action` string before it's used to build the request URL.
- Wired `engine_auth_headers()` into `_call_engine`'s outbound POST.

### 4. `DecisionExecutor` auth wiring ✓

- Same `engine_auth_headers()` added to its outbound POST.
- `ACTION_ENGINE_MAP` left untouched but clearly annotated: none of its 5 actions (`scale_budget`, `adjust_frequency`, `change_format`, `change_channel`, `adjust_timing`) exist anywhere in the real fleet — flagged, not silently pointed at something else invented.

### 5. `app/models/workflows.py` — real, verified remapping ✓

- **`create_content_pillar_workflow()`** fully rewritten against real, directly-read router code (content-engine's `content.py`, `distribution.py`, `analytics.py`) — 5 steps, all real: `POST /content/generate` → `POST /content/{id}/repurpose` → `POST /distribution/publish` → `POST /distribution/{id}/execute` → `POST /analytics/content/{id}/track`. All five live on **content-engine**, not spread across content/marketing/analytics/revenue like the original invented version assumed. The monetization step is dropped — revenue-operations-engine has no offer-creation concept at all, it's a real Stripe-backed billing system; kept out rather than pointed at something invented.
- **`create_daily_optimization_workflow()`** and **`create_audience_growth_workflow()`** left unchanged but clearly flagged as unverified in their docstrings — neither is ever called anywhere in this repo, and their invented actions (`get_metrics`, `analyze_ab_tests`, `identify_winners`, `update_strategy`, `segment_audience`, `create_nurture`, `track_campaign`) have no real backing anywhere in the fleet either.

## Test Results

**test_phase_h_reconciliation.py** — 4 test groups, all passing:

1. **Action-path templating**: a 2-step workflow against a fake engine with a *real* FastAPI path parameter (`/content/{content_id}/repurpose`) — proves `$steps.create_pillar.id` resolves into the URL path and the fake engine's own path-param parsing genuinely receives it, not just a string-match check.
2. **`engine_auth_headers()`**: unconfigured → `{}`; configured → correct Bearer header.
3. **Ports**: all 10 `ENGINE_URLS` entries match the verified real port map exactly; `pricing` confirmed absent.
4. **The real content pillar workflow, executed for the first time ever**: `create_content_pillar_workflow()` — never imported or called anywhere in this repo before this test — run through the actual `POST /workflows/create` + `POST /workflows/{id}/execute` HTTP flow against `mock_engines.py` (Phase F's real subprocess pattern). All 5 real, verified steps complete successfully; the path-templated IDs (`content/mock-.../repurpose`, `distribution/mock-.../execute`, `analytics/mock-.../track`) are visible in the logs, confirming every resolution worked correctly in sequence.

**Regression check** — full existing suite still green: all 11 prior test files plus `pytest tests/` (`run_all_tests.py`, 13/13).

## Code Structure

```
CascadeProjects/
├── HANDOFF.md (modified) - headline, Stage 3 correction, new Session Log entry
└── os42-orchestrator/
    ├── CLAUDE.md (new) - read-this-first for future sessions in this repo
    ├── app/
    │   ├── config.py (modified)
    │   │   - 6 corrected ports, pricing removed, UNKEY_API_KEY + engine_auth_headers()
    │   ├── models/
    │   │   └── workflows.py (modified)
    │   │       - create_content_pillar_workflow() rewritten against real endpoints
    │   │       - other two templates flagged unverified, unchanged
    │   ├── routes/
    │   │   └── dashboard.py (modified) - dropped 'pricing' from the cosmetic services list
    │   └── services/
    │       ├── workflow_executor.py (modified)
    │       │   - _resolve_action_path(), engine_auth_headers() wired in
    │       └── decision_executor.py (modified)
    │           - engine_auth_headers() wired in, ACTION_ENGINE_MAP annotated
    └── test_phase_h_reconciliation.py (new, 240 lines)

Git History (this phase):
- 1d72c0d (CascadeProjects root): docs: Update handoff - orchestrator reconciliation
- 6a665ee: docs: Add CLAUDE.md
- (pending commit): Phase H: Reconciliation with the real engine fleet
```

## Key Technical Decisions

1. **Verify against real router code, not the research agents' summaries alone.** The agents' port/endpoint findings were used as a map of where to look, but every field name and request/response shape actually used in the DSL rewrite was confirmed by directly reading `content.py`, `distribution.py`, `analytics.py`, `campaigns.py` — repeating the original mistake (guessing contracts) while "fixing" it would have been worse than not fixing it.
2. **Action-path templating as a small, additive extension of the existing `$steps.x.y` syntax**, not a new DSL feature. Same regex-based single-level resolution as `_resolve_params` (deliberately not the deeper nested-field syntax the test fixtures' own hand-rolled resolver supports) — consistency with what this file already does, not an opportunity to also fix that pre-existing inconsistency, which is out of scope here.
3. **Dropped the monetization step rather than inventing a new mapping for it.** revenue-operations-engine's real API (customers/payments/subscriptions/invoices/dunning) has no offer concept at all — pointing it at any of those would be exactly the kind of guess that caused this whole reconciliation.
4. **Left `ACTION_ENGINE_MAP` and the other two workflow templates alone, annotated rather than "fixed."** Nothing real exists for those actions anywhere in the fleet — remapping them to something else invented would repeat the mistake under a new name. Honest "not yet possible" beats a plausible-looking wrong answer.
5. **`CLAUDE.md` over relying on memory or `HANDOFF.md` alone.** Both matter, but `CLAUDE.md` is auto-loaded by any Claude Code session working in this exact directory — the one prevention mechanism that can't be skipped by a future session that (like this one did) never thinks to look at the parent directory.

## Verification Checklist

- [x] All corrected ports verified against real `main.py`/`uvicorn.run()` calls, not assumed
- [x] `pricing-intelligence-system` confirmed to have no FastAPI app before removing it as a peer
- [x] Every remapped action verified against real router source, including request/response field names
- [x] Path-parameter templating proven against a real FastAPI path parameter, not a string-match shortcut
- [x] The real content pillar workflow executes successfully end-to-end for the first time in this repo's history
- [x] Actions with no real backing are flagged, not silently dropped or repointed at another guess
- [x] Prevention measures committed to both the shared `HANDOFF.md` and this repo's own `CLAUDE.md`
- [x] All prior-phase tests still pass unmodified

## Technical Debt / Notes

- `distribution/{id}/execute`'s real server-side behavior honestly reports failure when no platform credentials are configured (per content-engine's own docstring) — the reconciled DSL step will "succeed" against `mock_engines.py` but would legitimately fail against the real content-engine until WordPress/dev.to credentials are configured (per `HANDOFF.md`: none are yet).
- `campaigns/{id}/launch` (referenced only in the still-unverified `create_audience_growth_workflow`) is itself a server-side stub in the real engine ("In production, this would update status...") — even a correct remap would call something not fully real yet.
- The two deferred bigger questions (unkey-auth replacing this repo's tenant system; `WorkflowExecutor` vs. `baselayer/core_loop`'s overlap) remain genuinely open, not scoped or sized here.

## Next Steps

1. **Decide and execute the unkey-auth question** — replace this repo's custom `TenantRegistry`/`X-API-Key` system, or keep it as a separate concern from engine-calling auth (which now has its own, independent `UNKEY_API_KEY` support as of this phase).
2. **Decide the `WorkflowExecutor` vs. `baselayer/core_loop` question** — keep as a deliberately narrower, purpose-built runner for this orchestrator's own loop, or defer to/integrate with baselayer's more mature engine.
3. **Real credentials** (WordPress/dev.to/SendGrid/Unkey workspace) are a prerequisite for any of this to do real work against the real fleet instead of `mock_engines.py` — user-side, not dev-time, per `HANDOFF.md`.
