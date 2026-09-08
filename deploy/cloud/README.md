# deploy/cloud/ — free-tier cloud deploy package

`OS42_ROADMAP.md` **step 13** (stretch: free-tier cloud presence), prepared
2026-09-03. **Nothing here is applied.** No account, no credential, no
`docker push`, no `fly deploy` has run. This is the "one command when you
say go" bundle for putting **`os42-orchestrator` alone** on a free web
tier as a proof-of-life.

**Start with [`RUNBOOK.md`](./RUNBOOK.md).** It has the pre-flight check,
the exact Render steps (primary), the Fly.io steps (if you want the state
snapshot to survive restarts), a Postgres plan (future — the code for it
doesn't exist yet), and a one-glance checklist.

| File | What it is |
|---|---|
| [`RUNBOOK.md`](./RUNBOOK.md) | The procedure. Read this. |
| [`Dockerfile`](./Dockerfile) | Py3.12 slim image. Build context = repo root: `docker build -f deploy/cloud/Dockerfile .` |
| [`render.yaml`](./render.yaml) | Render Blueprint, `plan: free`. Secrets left blank by design. |
| [`fly.toml`](./fly.toml) | Fly.io alternative with a 1 GB volume for the JSON snapshot. |
| [`.env.cloud.example`](./.env.cloud.example) | Every env var the app reads + what to set it to. No real values. |

Scope is deliberately small — see `RUNBOOK.md` §1 and §7 for what is and
isn't included, and `OS42_ROADMAP.md` step 13 for why.
