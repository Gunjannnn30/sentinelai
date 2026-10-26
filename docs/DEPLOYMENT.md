# Deployment

## Topologies

| Env | DB | Rate limits | How |
|---|---|---|---|
| Local dev | SQLite `backend/data/sentinelai.db` | in-process | `scripts/dev.sh` / uvicorn on **8123**, frontend `npm run dev` on 3000 |
| Local compose (Postgres/Redis, no TLS) | Postgres 16 | in-process per container | `docker compose up --build` |
| Production | Managed Postgres | Redis (`SENTINEL_REDIS_URL`) | images + Alembic + reverse proxy (TLS) |

## Docker Compose

```bash
docker compose up --build
# frontend  http://localhost:3000
# backend   http://localhost:8123  (API, /docs, /health, /ready, /metrics)
```

Services: `db` (postgres:16-alpine, healthcheck), `redis` (redis:7-alpine),
`backend` (runs **`alembic upgrade head` before uvicorn**, port 8000→8123),
`frontend` (Next.js, 3000). Volumes: `pgdata`, `redisdata`, `backend_data`.

> **Honest status:** Docker was not available on the authoring host, so this
> stack is *authored but unverified here*. First `docker compose up` is a
> verification step — check `/ready` (database: `ok`) and the frontend page.
> The images mirror the repo layout (`/srv/sentinelai/{backend,ai}`) because
> `app.core.bootstrap` resolves the top-level `ai` package from three levels
> above `backend/app/core`.

## Production checklist

1. **Images**: build `infra/Dockerfile.backend` and `infra/Dockerfile.frontend`
   from the repo root as context (`docker build -f infra/Dockerfile.backend .`).
2. **Secrets** — set, never commit:
   - `SENTINEL_AUTH_SECRET` — 128+ bits of random (`openssl rand -hex 32`),
     unique per environment. Startup fails fast in `production` if missing.
   - Provider keys `SENTINEL_OPENAI_API_KEY` / `ANTHROPIC` / `GEMINI` via your
     secret manager; leave empty to run mock-only.
3. **Environment**:
   ```
   SENTINEL_APP_ENV=production
   SENTINEL_DATABASE_URL=postgresql+psycopg://user:pass@db-host:5432/sentinel
   SENTINEL_REDIS_URL=redis://redis-host:6379/0
   SENTINEL_SESSION_COOKIE_SECURE=true
   SENTINEL_ALLOW_DEV_LOGIN=false
   SENTINEL_SEED_DEMO_DATA=false
   SENTINEL_STORE_PROMPT_CONTENT=false
   ```
4. **Migrations** — schema in production comes **only** from Alembic:
   `./scripts/migrate.sh upgrade head` (compose already runs this in its
   `command`). Never rely on `create_all` (disabled in production lifespan).
5. **Reverse proxy / TLS** — terminate HTTPS, proxy to the backend, forward
   `X-Request-ID`, and set the frontend `NEXT_PUBLIC_API_URL` to the
   **browser-reachable** API origin (build arg). Keep cookies Secure+SameSite.
6. **Frontend build**: `docker build -f infra/Dockerfile.frontend --build-arg
   NEXT_PUBLIC_API_URL=https://api.example.com .` — env vars prefixed
   `NEXT_PUBLIC_*` are inlined at build time, not runtime.
7. **Workers**: uvicorn single-process by default; if scaling replicas, put
   `SENTINEL_REDIS_URL` in place first (rate-limit counters become shared) and
   run migrations exactly once per release.
8. **Probes**: `/health` (liveness), `/ready` (DB + config checks; use for
   readiness/load-balancer), `/metrics` (basic process metrics).

## Verified on the authoring host (no Docker)

| Step | Result |
|---|---|
| `ruff check . ../ai` | clean |
| `pytest` (backend + ai) | **113 passed** (coverage of `app` = 79.6%) |
| `alembic upgrade head` → `alembic current` → `alembic check` | head applied, "No new upgrade operations detected" |
| Live uvicorn + `scripts/smoke.py` | **6/6 PASS** (register → success chat `demo=true` → blocked credential prompt → audit chain ok) |
| Frontend gates | `tsc --noEmit` clean, `npm run lint` clean, `npm test` **26/26**, `next build` 15/15 routes |
| Playwright e2e (live stack) | **1 passed** (register → chat → blocked → requests history → audit chain verify → analytics), stable across 3 runs |

Not executable here: `docker compose up`, GitHub Actions runs. Both are
authoritative-shaped (pinned actions, pinned image tags) and CI re-runs the
same commands as above.

## Upgrades & rollback

- **Backend**: build new image → `alembic upgrade head` → rolling restart.
  Migrations in this repo are forward-only by convention; for a rollback,
  restore from backup (additive expand/contract migrations are the pattern for
  zero-downtime schema changes).
- **Frontend**: rebuild with the right `NEXT_PUBLIC_API_URL`, rolling restart.
- **DB backup**: `pg_dump -Fc` on a schedule (compose: run inside the `db`
  service); SQLite: stop the app and copy the file. Keep `audit/export`
  snapshots alongside backups as the tamper-detection anchor.

## Local Windows notes

- Backend port **8123** everywhere (8000 is commonly occupied on dev machines).
- PowerShell + live server: inline JSON quoting breaks — write the body to a
  file and use `--data-binary '@file'`, or use `Invoke-RestMethod -SessionVariable s`.
- Clean-slate local DB: stop the server, delete `backend/data/sentinelai.db*`,
  restart (dev/test envs recreate the schema and re-seed demo data).
