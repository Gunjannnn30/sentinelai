# SentinelAI

**AI governance & security platform** — an LLM gateway with policy guardrails,
tamper-evident audit logging, routing with cost/capability constraints,
analytics, and offline evaluations. Monorepo: FastAPI backend (`backend/`) +
Next.js frontend (`frontend/`).

```
client ──▶ FastAPI gateway ──▶ guardrails (PII / secrets / injection)
                     │                    │ block, mask, or warn
                     │                    ▼
                     │          policy engine (JSON conditions, versions)
                     │                    ▼
                     │          router (capability, cost, latency, priority)
                     │                    ▼
                     │          provider adapter (mock | openai | anthropic | …)
                     ▼
        request record + security events + hash-chained audit log
```

## What's implemented

- **Gateway** — `POST /api/v1/chat/completions` with auth, per-org rate limits,
  request-size guard, guardrails, policy evaluation, model routing, provider
  adapters, token/cost accounting, structured audit trail.
- **Guardrails** — PII (SSN, credit card, email, phone) detection + irreversible
  masking, API-key/JWT detection (block), prompt-injection scoring
  (instruction override, secrets exfiltration, hierarchy manipulation, safety
  bypass). Never fabricates provider output: failures surface as typed errors.
- **Policies** — versioned JSON-condition policies with `allow | warn | mask |
  block` actions, org/project scope, role scoping, and a preview endpoint.
- **Audit** — hash-chained event log (`prev_hash`/`hash`), per-org sequence
  numbers, verification endpoint, JSON/CSV-style export. Prompt/response content
  is **off by default** (`SENTINEL_STORE_PROMPT_CONTENT=false`) and masked when
  stored.
- **Analytics** — overview, costs, security, and per-model rollups (daily
  `usage_metrics` aggregation).
- **Evaluations** — datasets (cases) + runs across multiple models with
  per-case status, latency, tokens, cost, and metric JSON; baselines supported.
- **Admin** — providers, models, members/roles (owner/admin/developer/viewer),
  teams, projects, org settings, audit endpoints.
- **Frontend** — login/register, playground with block/warn outcomes, request
  history, policies, audit viewer, analytics, evaluations, settings, onboarding.
- **Ops** — `/health`, `/ready`, `/metrics`; Alembic migration; Docker Compose;
  GitHub Actions CI (backend lint+tests+coverage+alembic, frontend
  typecheck+lint+tests+build).

## Honest status / deviations from the spec

- **Provider SDKs are replaced by direct REST calls via `httpx`** (no vendor
  SDK dependency); adapters mirror the OpenAI/Anthropic/Gemini REST shapes.
- **No real provider keys exist in this repository.** The default `mock`
  provider is deterministic and every response it produces is labeled
  `demo: true`.
- **Local dev runs SQLite + an in-process rate limiter** (no Docker/Postgres/
  Redis on the authoring host). `docker-compose.yml` provides Postgres 16 +
  Redis 7 + both apps, but **it was authored, not executed on this host** —
  treat first `docker compose up` as a verification step (see
  docs/DEPLOYMENT.md).
- `SENTINEL_APP_ENV` accepts only `development | production | test`.

## Quickstart (local, SQLite)

Backend (Python 3.11+):

```bash
python -m venv .venv
.venv/Scripts/pip install -e "backend[dev]"       # Windows; use .venv/bin/pip elsewhere
cp .env.example .env                             # local defaults are fine
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8123
```

or `./scripts/dev.sh` (bash). API docs: http://127.0.0.1:8123/docs

Frontend (Node 20+):

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://127.0.0.1:8123 npm run dev   # http://127.0.0.1:3000
```

> Port **8000 is intentionally avoided** (commonly occupied); the documented
> backend port is **8123** everywhere (scripts, docs, `.env`, compose).

## Configuration

All backend settings are read **only** from `SENTINEL_`-prefixed environment
variables (see `.env.example`). Unprefixed names are silently ignored — a
footgun the CI and tests pin against. Key ones:

| Variable | Default | Notes |
|---|---|---|
| `SENTINEL_APP_ENV` | `development` | `development \| production \| test` |
| `SENTINEL_AUTH_SECRET` | *(required in prod)* | signs session cookies; rotate per env |
| `SENTINEL_DATABASE_URL` | `sqlite:///./data/sentinelai.db` | Postgres in compose |
| `SENTINEL_REDIS_URL` | *(empty = in-process)* | optional rate-limit backend |
| `SENTINEL_SESSION_COOKIE_SECURE` | `false` | `true` behind TLS |
| `SENTINEL_STORE_PROMPT_CONTENT` | `false` | audit content off by default |
| `SENTINEL_SEED_DEMO_DATA` | `true` | first-boot demo org/user; demo rows flagged |
| `SENTINEL_ALLOW_DEV_LOGIN` | `true` | **must be `false` in production** |
| `SENTINEL_*_API_KEY` | *(empty)* | never commit keys |

## Tests & checks

```bash
# backend (from backend/)
../.venv/Scripts/python -m ruff check .      # lint
../.venv/Scripts/python -m pytest            # 113 tests, ~8s  (coverage 79.6%)

# live smoke (backend must be running)
../.venv/Scripts/python scripts/smoke.py     # 6/6 checks

# frontend (from frontend/)
npm run lint && npm test && npm run build
```

CI runs the same gates on every push/PR touching `backend/` or `frontend/`.

## Repository layout

```
backend/
  app/api/v1/        # HTTP layer (auth, gateway, policies, requests, evals,
                     # analytics, admin, ops)
  app/core/          # config, security (scrypt/sessions/CSRF), errors, logging
  app/db/            # engine/session, SQLAlchemy models
  app/services/      # request_service pipeline, audit, ratelimit, deps, seed
  app/schemas/       # Pydantic request/response models
  alembic/           # migrations (authoritative in production)
  tests/             # pytest suite (113)
ai/                  # framework-free domain library (imported by backend):
  gateway/           # pipeline.run_pipeline
  guardrails/        # pii, injection, output_guard, policy_engine
  routing/           # fail-closed model routing engine
  providers/         # mock/openai/anthropic/gemini/ollama adapters (httpx)
  evaluation/        # deterministic eval metrics
frontend/            # Next.js App Router (TS strict, Tailwind, Recharts)
infra/               # Dockerfiles
scripts/             # dev.sh, migrate.sh, smoke.py
docs/                # ARCHITECTURE, SECURITY, API, DATABASE, THREAT_MODEL,
                     # EVALUATION, DEPLOYMENT, IMPLEMENTATION_PLAN
.github/workflows/   # backend.yml, frontend.yml
docker-compose.yml   # Postgres + Redis + backend(8123) + frontend(3000)
```

## Documentation

| Doc | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, request lifecycle, module map |
| [docs/SECURITY.md](docs/SECURITY.md) | Auth, RBAC, secrets, isolation, controls |
| [docs/API.md](docs/API.md) | Endpoint catalog, envelopes, conventions |
| [docs/DATABASE.md](docs/DATABASE.md) | Tables, relations, migrations |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | Assets, actors, threats → controls |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Eval datasets/runs/metrics |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Compose, prod checklist, ops |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Milestones + verified status |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |

## License

Proprietary / unlicensed sample — no warranty.
