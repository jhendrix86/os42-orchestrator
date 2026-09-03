# os42-orchestrator — free-tier cloud deploy RUNBOOK

**Status: PREPARED, NOT EXECUTED.** Nothing in `deploy/cloud/` has been
applied to any cloud account. No account was created, no credential was
handled. This is the one-command-when-you-say-go package for
`OS42_ROADMAP.md` step 13 ("free-tier cloud presence"), scoped exactly as
that step demands: a proof-of-life for the single most self-contained
service, not a home for the fleet.

Prepared 2026-09-03 (G7 session) at the request of the coordinating
session. See `HANDOFF.md` step 13.

---

## 1. What gets deployed

Just **`os42-orchestrator`** — one FastAPI web service. Chosen because it
already has CI, has the fewest dependencies (7 pure-Python packages, no DB
driver), and its only persistence is an opt-in JSON snapshot. No other
fleet engine is deployed; the orchestrator's engine-URL config points at a
dead port on purpose (per-call connection failures are caught — `/status`
and the scheduler loop degrade cleanly).

**What works in the cloud:** `/health`, `/`, `/status`, `/docs`, tenant
CRUD, workflow CRUD, `/dashboard/*`, `/scheduler/status`, the optimization
endpoints, the background `AutonomousScheduler` loop (ticks every 300s and
emits a `RESUME` no-op because no metrics are fed — expected, see
`STAGE5_PLAN.md` finding 1).

**What doesn't:** any workflow `execute` step that actually calls an engine
(nothing to reach). That's fine for proof-of-life.

## 2. Files in this directory

| File | Purpose |
|---|---|
| `Dockerfile` | Python 3.12 slim image. Build context = **repo root**. |
| `render.yaml` | Render Blueprint (free web service). Primary path. |
| `fly.toml` | Fly.io alternative — supports a persistent volume for the snapshot. |
| `.env.cloud.example` | Every env var the app reads, with what to set. |
| `RUNBOOK.md` | This file. |

## 3. Pre-flight (once, ~2 min, no signup)

```bash
cd /path/to/CascadeProjects/os42-orchestrator

# 3.1 Prove the image builds and boots locally.
docker build -f deploy/cloud/Dockerfile -t os42-orchestrator:local .
docker run --rm -p 8050:8050 \
  -e OS42_ADMIN_KEY=local-test-admin \
  -e OS42_DEFAULT_API_KEY=local-test-key \
  os42-orchestrator:local
# in another shell:
curl -fsS localhost:8050/health   # -> {"service":"os42-orchestrator",...,"status":"healthy"}
curl -fsS localhost:8050/status   # -> engines listed, active_workflows: 0

# 3.2 Generate the two real secrets you'll paste in step 4/5.
python -c "import secrets;print('OS42_ADMIN_KEY      =','os42_admin_'+secrets.token_urlsafe(32))"
python -c "import secrets;print('OS42_DEFAULT_API_KEY=','os42_'+secrets.token_urlsafe(32))"
# Store these in a password manager now. They are shown once here and never again.
```

If 3.1 is green, the deploy will work. Stop here until you decide to go.

---

## 4. Path A — Render (recommended, simplest)

**Push-button, when you say go:**

1. **Account** (you, manual): sign in at <https://dashboard.render.com> with
   the GitHub account that owns `jhendrix86/os42-orchestrator`. Free plan,
   no card required for a free web service.

2. **Create the Blueprint:**
   - Dashboard → **New** → **Blueprint**.
   - Pick the `os42-orchestrator` repo. Render finds `render.yaml`
     automatically. *(If it only scans the root, either move/symlink
     `render.yaml` to the repo root or point the Blueprint at
     `deploy/cloud/render.yaml` in the dialog.)*
   - It shows one `web` service, plan `free`. **Apply**.

3. **Set the two secrets** (Blueprint leaves them blank on purpose):
   - Service → **Environment** → add `OS42_ADMIN_KEY` and
     `OS42_DEFAULT_API_KEY` with the values from step 3.2 → **Save**
     (triggers a redeploy).
   - CLI equivalent: `render env set OS42_ADMIN_KEY=... OS42_DEFAULT_API_KEY=... --service os42-orchestrator`

4. **Verify:**
   ```bash
   BASE=https://os42-orchestrator-XXXX.onrender.com   # from the Render dashboard
   curl -fsS $BASE/health
   curl -fsS $BASE/status
   curl -fsS $BASE/docs -o /dev/null -w '%{http_code}\n'   # 200
   # admin gate works (header is X-Admin-Key, checked via hmac.compare_digest
   # in app/services/tenancy.py require_admin; tenant header is X-API-Key):
   curl -fsS -X POST $BASE/scheduler/pause \
     -H "X-Admin-Key: <OS42_ADMIN_KEY>" -w '\n%{http_code}\n'   # 200
   curl -s  -X POST $BASE/scheduler/pause -w '\n%{http_code}\n'  # 401
   curl -fsS -X POST $BASE/scheduler/resume -H "X-Admin-Key: <OS42_ADMIN_KEY>"
   ```

5. **Done.** Auto-deploys on every push to `main`. Free-plan behaviour:
   sleeps after ~15 min idle, ~30–60s cold start, snapshot at `/tmp` wiped
   on each sleep/deploy (acceptable for a demo; see §5).

**Rollback:** Render dashboard → service → **Manual Deploy** → pick a prior
commit, or **Suspend**/**Delete** the service. No local state to clean up.

---

## 5. Path B — Fly.io (use if you want the snapshot to survive restarts)

1. **Account + CLI** (you, manual): `flyctl` installed
   (<https://fly.io/docs/flyctl/install/>), `fly auth login`. Free
   allowance covers one `shared-cpu-1x` / 256MB machine + a 1GB volume.

2. **Volume** (once):
   ```bash
   cd os42-orchestrator
   fly launch --no-deploy --copy-config --name os42-orchestrator   # reads fly.toml, creates the app
   fly volumes create os42_data --size 1 --region sea
   ```

3. **Secrets + deploy:**
   ```bash
   fly secrets set OS42_ADMIN_KEY=... OS42_DEFAULT_API_KEY=...
   fly deploy
   fly status
   curl -fsS https://os42-orchestrator.fly.dev/health
   ```

4. **Verify:** same curl block as §4.4 against the `.fly.dev` URL. Confirm
   snapshot persistence: `fly apps restart os42-orchestrator`, then re-GET a
   tenant you created — it should still be there (Render would have lost it).

**Rollback:** `fly deploy --image <prior>` or `fly apps destroy
os42-orchestrator`; `fly volumes destroy os42_data` to remove state.

---

## 6. Postgres plan (Neon / Supabase) — FUTURE, code does not exist yet

**Current reality:** the orchestrator has **no database layer** — no
driver, no ORM, no models. Its only persistence is
`app/services/persistence.py`: a single JSON snapshot written after each
scheduler tick and on shutdown, gated on `OS42_PERSISTENCE_PATH`. This is
explicitly flagged as tech debt in `PHASE_D_COMPLETION.md` ("a real
deployment would want an actual database and write-through persistence").

So a free Neon/Supabase database **would sit unused** until someone writes
the store. When that's worth doing, here's the shape:

### 6.1 Provision (5 min, when ready)
- **Neon** (<https://neon.tech>, free tier: 0.5 GB, autosuspend) or
  **Supabase** (<https://supabase.com>, free tier: 500 MB, pauses after 7
  days idle). Neon is the better fit — no unrelated auth/realtime stack,
  faster cold resume.
- Create a project in the **same region** as the web service (§ `region`
  in `render.yaml` / `primary_region` in `fly.toml`).
- Copy the **pooled** connection string (Neon: the `-pooler` host):
  `postgresql://USER:PASS@ep-xxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require`

### 6.2 Wire (config only, once the code in 6.3 exists)
- Add `DATABASE_URL` as a **secret** (not in any committed file):
  - Render: `render env set DATABASE_URL=... --service os42-orchestrator`,
    or uncomment the `databases:` block in `render.yaml` to use Render's
    own free Postgres instead of Neon.
  - Fly: `fly secrets set DATABASE_URL=...`
- Keep `OS42_PERSISTENCE_PATH` unset when `DATABASE_URL` is present.

### 6.3 Build the store (est. 1 small session, ~150–250 LOC + tests)
1. `requirements.txt` += `asyncpg==0.30.*` (or `psycopg[binary]`).
   SQLAlchemy is **not** needed for one blob table.
2. New `app/services/pg_persistence.py` exposing the **same contract** as
   `persistence.py` — `build_snapshot()` is already storage-agnostic and
   returns a JSON-safe dict; reuse it verbatim.
   - Table: `CREATE TABLE os42_snapshot (id int primary key default 1,
     saved_at timestamptz, payload jsonb, check (id = 1));`
   - `save_snapshot()` → `INSERT ... ON CONFLICT (id) DO UPDATE` with the
     `build_snapshot()` dict as `payload`.
   - `load_snapshot()` → `SELECT payload` and replay it through the exact
     same restore loops `persistence.py` already has (tenants → metrics →
     decisions → workflows).
3. In `app/main.py` lifespan: `if os.getenv("DATABASE_URL")` use the PG
   store, `elif os.getenv("OS42_PERSISTENCE_PATH")` use the file store,
   else in-memory. One `if/elif/else`, no other call sites change.
4. Tests: clone `test_phase_d_persistence.py`'s two-subprocess round-trip
   against a disposable Postgres (`docker run --rm postgres:16` in CI, or a
   Neon branch). Gate on `DATABASE_URL` so the default suite is untouched.
5. CI: nothing to change unless you want a PG job — the existing suite
   stays green because the store is opt-in.

**Blast radius:** additive. The file-snapshot and in-memory paths are
untouched, so this can't regress the current green CI.

---

## 7. What this deliberately does NOT do

- No account signup, no card, no credential entry — all of §4.1 / §5.1 are
  yours to do.
- No custom domain, no TLS config (platform-managed), no CDN.
- No engines, no Redis, no RabbitMQ, no MongoDB — none of the fleet's
  infra. The roadmap is explicit that no free tier hosts that, and this
  package doesn't pretend otherwise.
- No autoscaling — single instance by design (in-process scheduler + state).
- No secret values written to any file in the repo.

## 8. One-glance checklist

```
[ ] 3.1 docker build + run + curl /health green locally
[ ] 3.2 generated OS42_ADMIN_KEY and OS42_DEFAULT_API_KEY, stored safely
[ ] 4.1 Render account (or 5.1 Fly account + flyctl)
[ ] 4.2 Blueprint applied  (or 5.2 fly launch --no-deploy + volume)
[ ] 4.3 two secrets set in the dashboard  (or 5.3 fly secrets set)
[ ] 4.4 curl /health /status /docs against the public URL — all green
[ ] admin gate: POST /scheduler/pause  401 without X-Admin-Key, 200 with it
[ ] (optional) §6 Postgres — only after 6.3 code lands
```
