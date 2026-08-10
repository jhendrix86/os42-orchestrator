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

## Rule going forward

Never add a new engine URL, action name, or assumed contract to this repo
without first checking the real engine's actual router code — or, if you're
the one making a contract real, update `../HANDOFF.md`/`../OS42_REPAIR_PLAN.md`
so the next session doesn't have to rediscover it. Guessing is exactly how
the drift above happened, twice (once building it, and HANDOFF.md's own
Stage 3 status was already stale by the time this reconciliation checked it).
