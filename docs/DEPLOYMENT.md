# Deployment

## Topologies

| Env | DB | Rate limits | How |
|---|---|---|---|
| Local dev | SQLite `backend/data/sentinelai.db` | in-process | `scripts/dev.sh` / uvicorn on **8123**, frontend `npm run dev` on 3000 |
| Local compose (Postgres/Redis, no TLS) | Postgres 16 | in-process per container | `docker compose up --build` |
| **Production (this repo)** | **Neon** free-tier Postgres (never expires) | in-process (add `SENTINEL_REDIS_URL` before scaling) | **backend → Render**, **frontend → Vercel**, TLS on both |
| Production (alternative) | Managed Postgres | Redis (`SENTINEL_REDIS_URL`) | images + Alembic + reverse proxy (TLS) |

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
4. **Migrations** — schema in production comes **only** from Alembic. The
   backend image runs `alembic upgrade head` at container start (the
   `CMD` in `infra/Dockerfile.backend`, mirroring compose's `command`);
   `create_all` is disabled in the production lifespan, so that step is load
   bearing. You can also run it explicitly: `./scripts/migrate.sh upgrade head`.
5. **Topology: one public origin.** The browser only ever talks to the Next
   server; `frontend/middleware.ts` forwards `/api/*`, `/health`, `/ready`
   and `/metrics` to the backend over the private network. So:
   - Run `SENTINEL_API_ORIGIN` as a **server-side, runtime-only** env var on
     the frontend service. Middleware reads it on every request, so it needs no
     build-time value, e.g. `SENTINEL_API_ORIGIN=http://backend:8000` inside
     Compose, or the API service's HTTPS URL on a PaaS.
     It is deliberately *not* read by `rewrites()` in `next.config.ts`: Next
     evaluates those once during `next build` and freezes the result into
     `.next/routes-manifest.json`, so a build without the variable (the normal
     Docker case) bakes in the `http://127.0.0.1:8123` fallback and every
     proxied path 500s at runtime.
   - Terminate HTTPS once, proxy to the frontend, forward `X-Request-ID`.
   - **Do not** set `NEXT_PUBLIC_API_URL` to an absolute origin. The backend
     ships no CORS middleware, so a direct browser→API call is cross-origin
     and will be blocked. Leave it unset to stay on the same-origin proxy.
   - Keep cookies `Secure` + `SameSite` appropriate for a single host;
     set `SENTINEL_SESSION_COOKIE_SECURE=true`.
6. **Frontend build**: `docker build -f infra/Dockerfile.frontend .` —
   `SENTINEL_API_ORIGIN` is **not** required at build time; `middleware.ts`
   reads it when the server runs (see step 5). Only the runner stage's `ENV`
   matters, and it can be overridden at run time without a rebuild.
   `NEXT_PUBLIC_*` vars *would* be inlined at build time, which is why the
   proxy default (`API_BASE = ""`) is used instead.
7. **Workers**: uvicorn single-process by default; if scaling replicas, put
   `SENTINEL_REDIS_URL` in place first (rate-limit counters become shared),
   and run migrations exactly once per release — strip the
   `alembic upgrade head &&` prefix from the image `CMD` so every replica
   does not migrate concurrently.
8. **Probes**: `/health` (liveness), `/ready` (DB + config checks; use for
   readiness/load-balancer), `/metrics` (basic process metrics).
9. **Ports**: both containers honour `$PORT` (Render/Cloud Run/Railway inject
   it) and default to 8000 (API) / 3000 (console) when it is unset.

## The split topology this repo deploys: Neon + Render + Vercel

Three free services, each doing one job:

| Piece | Provider | Why it is free *forever* |
|---|---|---|
| Database | **Neon** (free tier) | No expiry. 512 MB storage, ~190 compute hours/mo, scales to zero when idle |
| Backend API | **Render** (free web service) | No expiry, but **spins down after 15 min idle** (~60 s wake) |
| Frontend console | **Vercel** (Hobby) | No expiry. 100 GB bandwidth/mo |

This split exists because of one fact: **Render's free Postgres expires after
30 days**, which silently kills a deployment you thought was permanent. Neon's
free Postgres does not. The app already spoke Postgres, so the switch is a
connection string — no code change, no migration of the data model.

### Why the frontend proxy makes Vercel possible

The browser only ever talks to the **Vercel** origin. `frontend/middleware.ts`
(server-side, runs on Vercel) forwards `/api/*`, `/health`, `/ready` and
`/metrics` to the **Render** API using `SENTINEL_API_ORIGIN`. Consequences:

- No CORS anywhere — the backend ships no CORS middleware, and it never needs
  any, because the browser never calls it directly.
- Session + CSRF cookies stay first-party (set on the Vercel origin), so
  `SameSite`/`Secure` behave exactly as they do locally.
- `SENTINEL_API_ORIGIN` is read **per request at runtime**, not at build time,
  so you can repoint the frontend at a different backend without rebuilding it.
  This is why the proxy lives in `middleware.ts` and not `next.config.ts`
  `rewrites()` (which is frozen into `.next/routes-manifest.json` by
  `next build`).

### Step by step

**1. Create the Neon database (you, ~3 minutes)**

1. Go to <https://neon.tech> → **Sign up** (free, no credit card; GitHub sign-in works).
2. On first launch, choose **Skip and build your own** (or accept the defaults).
3. Name the project `sentinelai`, keep region **AWS us-west-2 (Oregon)** to
   match the Render region — same-region keeps queries fast.
4. Pick the **Free** plan → **Create project**.
5. Neon shows you a connection string. **Copy the one labelled
   "Pooled connection"** only if you are connecting from a serverless
   function; for Render (a long-running container) use the **direct** one —
   host looks like `ep-xxxx-us-west-2.aws.neon.tech`, **not** `...-pooler...`.
   Paste it somewhere safe; you need it in step 3.

**2. Deploy the backend on Render (I can do this via API, or you via dashboard)**

- Blueprint route: Render → **New → Blueprint** → this repo → `render.yaml`
  provisions `sentinelai-api` only.
- After creation, set **Environment → `SENTINEL_DATABASE_URL`** to your Neon
  string (it is `sync: false` in the blueprint, so you must supply it).
- Render generates `SENTINEL_AUTH_SECRET` for you. Never commit a value.

**3. Deploy the frontend on Vercel (you, ~4 minutes)**

Detailed steps are in README §14.

**4. Verify both**

```
https://<api>.onrender.com/ready     → "database": "ok"
https://<web>.vercel.app/            → login page loads
https://<web>.vercel.app/ready       → the API's JSON, proxied
```

### Free-tier limits that matter (verified Oct 2026)

- **Render**: 512 MB / 0.1 CPU, spin-down after 15 min, 750 instance-hours per
  workspace per month (exhaustion suspends free services until next month).
- **Neon**: free plan expires **never**, but compute scales to zero after ~5 min
  idle — first query after that takes 1–3 s.
- **Vercel Hobby**: 100 GB bandwidth, function duration capped (middleware
  proxying a cold Render instance may time out on the very first hit; retry).
- No credit card required for any of the three.

## Verified on the authoring host (no Docker)

| Step | Result |
|---|---|
| `ruff check . ../ai` | clean |
| `pytest` (backend + ai) | **117 passed** (coverage of `app` = 79.7%) |
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
- **Frontend**: rebuild and rolling restart (repoint `SENTINEL_API_ORIGIN` if
  the backend address changed).
- **DB backup**: `pg_dump -Fc` on a schedule (compose: run inside the `db`
  service); SQLite: stop the app and copy the file. Keep `audit/export`
  snapshots alongside backups as the tamper-detection anchor.

## Local Windows notes

- Backend port **8123** everywhere (8000 is commonly occupied on dev machines).
- PowerShell + live server: inline JSON quoting breaks — write the body to a
  file and use `--data-binary '@file'`, or use `Invoke-RestMethod -SessionVariable s`.
- Clean-slate local DB: stop the server, delete `backend/data/sentinelai.db*`,
  restart (dev/test envs recreate the schema and re-seed demo data).
