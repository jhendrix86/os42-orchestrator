# Phase C Completion: Multi-Tenancy

**Status**: COMPLETE
**Date**: 2026-08-09
**Deliverables**: Tenant registry + API-key auth, tenant_id isolation across workflows/metrics/decisions, tenant provisioning API

## What Was Built

### 1. Tenant Model & Registry ✓
- `Tenant` dataclass (`app/models/tenant.py`): tenant_id, name, api_key, plan, created_at
- `TenantRegistry` (`app/services/tenancy.py`): in-memory directory keyed by both tenant_id and api_key
- A `default` tenant is auto-seeded at startup (env-overridable) so Phase A/B code and tooling keep working without every caller needing to provision a tenant first

### 2. API-Key Authentication ✓
- `get_current_tenant` FastAPI dependency resolves the caller from the `X-API-Key` header, 401s on missing/invalid keys
- `require_admin` dependency guards tenant provisioning via `X-Admin-Key` (env-overridable, `hmac.compare_digest` to avoid timing leaks)
- Applied at the router level for `/optimization/*` (blanket enforcement) and per-route for `/workflows/*` and `/tenants/*`

### 3. Tenant Provisioning API ✓
- `POST /tenants` (admin only) — provisions a tenant, returns its API key once
- `GET /tenants` (admin only) — lists all tenants (never returns api_key)
- `GET /tenants/me` — a tenant looks up its own record from its own key

### 4. Data Isolation ✓
Every place that previously kept a flat `workflow_id -> data` map now keys by `tenant_id -> workflow_id -> data`, so two tenants can use the identical workflow_id without ever seeing each other's data:
- `MetricsAggregator.workflow_metrics`
- `OptimizationEngine.execution_history`
- `app.state.active_workflows` / `app.state.workflow_results` (main.py)

`MetricPoint`, `PerformanceAnalysis`, and `OptimizationDecision` all carry a `tenant_id` field (default `"default"` so Phase B's own test script, `test_phase_b.py`, keeps working unmodified). Every service-layer method that reads or writes this data takes an explicit `tenant_id` keyword, and every HTTP route now resolves it from the authenticated tenant rather than trusting a caller-supplied value.

### 5. Routes Updated ✓
- `/workflows/create`, `/workflows/{id}`, `/workflows` — now require `X-API-Key`, scoped to the caller's tenant
- All 8 `/optimization/*` endpoints — now require `X-API-Key`, scoped to the caller's tenant
- `/status`, `/dashboard/metrics`, `/dashboard/activity` — remain unauthenticated system-wide operator views, updated to aggregate across the new nested per-tenant structure instead of assuming a flat dict
- `/health`, `/`, `/services`, `/dashboard/*` HTML — unchanged, no tenant data involved

## Test Results

**test_phase_c.py** (service layer, no HTTP):
- Two tenants register with distinct API keys; duplicate tenant_id rejected
- Two tenants record 48 metric points each under the *same* `workflow_id` ("pillar-001") — each only ever sees its own 48, a third unknown tenant sees 0, flat audit log still has all 96
- Same workflow_id analyzed independently per tenant: 5.25% vs 3.46% conversion rate
- Same workflow_id produces different optimization decisions per tenant: tenant A (high conversion) → `SCALE_BUDGET`, tenant B (declining) → `PAUSE`
- Execution history and `should_run_workflow()` correctly isolated per tenant
- Workflow sequencing only ranks the calling tenant's own workflows

**test_phase_c_api.py** (real HTTP endpoints via TestClient):
- No API key → 401; bad API key → 401; tenant provisioning without admin key → 401
- Admin provisions two tenants via `POST /tenants`; each gets a distinct key; `/tenants/me` resolves correctly
- Tenant A creates workflow `http-pillar-001`; tenant B gets 404 for that same ID; `GET /workflows` returns 0 for B, 1 for A
- Tenant A records a metric on `http-pillar-001`; tenant B sees `metric_count: 0` for the identical workflow_id

**Regression check** — full existing suite still green after the refactor:
- `test_phase_b.py` (unmodified call sites, relies on the `tenant_id="default"` fallback)
- `test_e2e_standalone.py`
- `pytest tests/` (3 passed)
- `test_dashboard.py`

## Incidental Fix

Discovered while verifying: the installed FastAPI/Starlette (0.139.2, newer than the `0.104.1` pinned in requirements.txt) no longer runs lifespan startup for a bare `TestClient(app)` — it must be used as `with TestClient(app) as client:`. This made `test_dashboard.py` fail on `app.state.system_status` even with zero Phase C changes applied. Fixed by switching to the context-manager form in both `test_dashboard.py` and the new `test_phase_c_api.py`. Unrelated to multi-tenancy; not touched further (requirements.txt pin left as-is).

## Code Structure

```
os42-orchestrator/
├── app/
│   ├── models/
│   │   └── tenant.py (new, 24 lines)
│   │       - Tenant dataclass
│   ├── services/
│   │   ├── tenancy.py (new, 100 lines)
│   │   │   - TenantRegistry, get_current_tenant, require_admin
│   │   ├── metrics_aggregator.py (modified)
│   │   │   - tenant_id on MetricPoint/PerformanceAnalysis
│   │   │   - workflow_metrics re-keyed tenant_id -> workflow_id -> points
│   │   └── optimization_engine.py (modified)
│   │       - tenant_id on OptimizationDecision
│   │       - execution_history re-keyed tenant_id -> workflow_id -> decisions
│   ├── routes/
│   │   ├── tenants.py (new, 40 lines)
│   │   │   - POST/GET /tenants (admin), GET /tenants/me
│   │   └── optimization.py (modified)
│   │       - X-API-Key required on all 8 endpoints
│   └── main.py (modified)
│       - X-API-Key required on /workflows/*
│       - active_workflows / workflow_results nested per tenant
├── test_phase_c.py (new, 220 lines) — service-layer isolation
├── test_phase_c_api.py (new, 150 lines) — HTTP-layer auth + isolation
└── test_dashboard.py (fixed) — TestClient lifespan usage

Git History (this phase):
- (pending commit): Phase C: Multi-Tenancy
```

## Key Technical Decisions

1. **Nested dicts over composite keys**: `tenant_id -> workflow_id -> data` rather than a `f"{tenant}:{workflow}"` string key. Isolation is structural — a lookup for tenant A's data literally cannot reach tenant B's bucket — rather than relying on every caller getting string formatting right.
2. **`tenant_id` defaults to `"default"` at the service layer, but is never optional at the HTTP layer**: internal dataclasses/methods default to `"default"` so Phase B's existing test script needed zero changes. Every route, by contrast, resolves `tenant_id` from the authenticated `X-API-Key` — callers can never pass an arbitrary tenant_id over HTTP.
3. **Router-level `dependencies=[Depends(get_current_tenant)]` + per-route `Depends()` parameter**: blanket-enforces auth on every `/optimization/*` route even if a future route forgets to declare it, while FastAPI's dependency caching means the tenant is only resolved once per request.
4. **Admin key separate from tenant keys**: provisioning (`POST/GET /tenants`) requires `X-Admin-Key`, distinct from any tenant's `X-API-Key`, so a compromised tenant key can't be used to mint new tenants.
5. **Dashboard and `/status` stay tenant-agnostic**: these are operator-facing, system-wide views (not customer-facing), so they were left unauthenticated but updated to correctly sum across all tenants' nested data.

## Verification Checklist

- [x] tenant_id added to MetricPoint, PerformanceAnalysis, OptimizationDecision
- [x] Metrics isolated by tenant in all aggregator queries
- [x] Per-tenant workflow recommendations (`recommend_workflow_sequence` scoped)
- [x] Per-tenant decision history (`get_execution_history`, `should_run_workflow` scoped)
- [x] Per-tenant API key authorization (X-API-Key on all tenant-data routes)
- [x] Per-tenant workflow storage (`/workflows/*` in main.py)
- [x] Identical workflow_id across two tenants proven not to leak, at both the service layer and over real HTTP
- [x] Existing Phase A/B tests still pass unmodified (aside from the unrelated TestClient fix)

## What's Ready for Integration

1. **Real tenant onboarding**: `POST /tenants` with `X-Admin-Key` issues a working API key immediately
2. **Engines calling back in**: any engine recording metrics via `/optimization/metrics/record` now must carry the tenant's `X-API-Key`
3. **Multi-tenant dashboards**: a per-tenant dashboard view could reuse the same `get_current_tenant` dependency; the current dashboard remains a system-wide ops view by design

## Technical Debt / Notes

- Tenant registry is in-memory only (matches the rest of the orchestrator's Phase B tech debt — no persistence layer yet). Restarting the process forgets all provisioned tenants except the seeded default.
- Admin key and default tenant key are dev-mode defaults (`os42_dev_admin_key`, `os42_dev_default_key`) unless overridden via `OS42_ADMIN_KEY` / `OS42_DEFAULT_API_KEY` / `OS42_DEFAULT_TENANT_ID` env vars — must be overridden before any non-local deployment.
- No API key rotation or revocation yet.
- No per-tenant rate limiting or usage quotas yet (mentioned as a natural Phase D concern given "autonomous scaling" already touches budget).
- `requirements.txt` still pins fastapi==0.104.1 while the local environment actually has 0.139.2 installed; worth reconciling before this leaves a single dev machine.

## Next Steps (Phase D - Full Autonomy)

Per PHASE_A_COMPLETION.md's original roadmap:
1. Strategic decision making
2. Goal-based workflow selection
3. Autonomous scaling and optimization (now with per-tenant budget context available from Phase C)
4. Scope TBD — likely also the point to add real persistence (tenant registry, metrics, decisions all currently in-memory)
