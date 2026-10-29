# SentinelAI

**An open-source AI governance & security platform.** A production-shaped
gateway that sits between your application and any LLM provider and decides —
per request — whether a prompt may proceed, what must be redacted, which model
it may reach, and what gets written to a tamper-evident audit trail.

If you are putting an LLM into a product and you need to answer *"who sent
what, which policy allowed it, which model answered, what did it cost, and has
anyone edited the log since?"* — this is that layer.

```
   your app ──▶ ┌────────────────────────── SentinelAI ──────────────────────────┐
                │  auth ─ rate limit ─ guardrails ─ policy ─ router ─ provider   │
                │                       │                                        │
                │                       ▼                                        │
                │     request record + security events + hash-chained audit log  │
                └─────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                          mock | OpenAI | Anthropic | Gemini | Ollama
```

- **Backend** — FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic (`backend/`)
- **Domain library** — framework-free AI logic, importable with zero web stack (`ai/`)
- **Frontend** — Next.js App Router + TypeScript (strict) + Tailwind (`frontend/`)
- **Docs** — nine documents under `docs/` covering architecture, security,
  threat model, API, database, evaluation, deployment, and the build plan

---

## Start here — read this first if any of these words are unfamiliar

**This section defines every term the rest of the README uses.** If you already
know what an LLM, a gateway and a database are, skip to the
[table of contents](#table-of-contents).

### What this project is, in plain words

Imagine you are adding a chat box to your website. The user types a question,
your server sends it to an AI company (OpenAI, Anthropic, Google), and the AI's
answer comes back. It works — until someone pastes their password into the
chat box, or a customer's credit card number, or a prompt that tricks the model
into ignoring its rules. Now your company has leaked a secret to a third party
and you cannot prove what happened.

**SentinelAI is the layer you put in the middle.** Your app talks to SentinelAI
instead of talking to the AI company directly. SentinelAI then, for *every
single request*:

1. **Checks it** — looks for passwords, credit cards, social security numbers,
   and attempts to trick the model.
2. **Hides what it finds** — replaces secrets with `***` *before* anything
   leaves your server, in a way that cannot be undone.
3. **Decides** — applies your rules ("block anything with an SSN", "never let
   the sales team use the expensive model") and either lets it through, warns,
   or blocks it outright.
4. **Picks a model** — chooses which AI actually answers, based on what the
   task needs and what it costs.
5. **Writes it down** — records every decision in a log that cannot be quietly
   edited after the fact.

If you have ever been asked *"who sent what, which rule allowed it, which model
answered, what did it cost, and has anyone tampered with the log?"* — this is
the component that answers all five.

### The vocabulary, one term at a time

| Term | What it actually means |
|---|---|
| **LLM** | *Large Language Model* — the AI itself, the thing that writes text. GPT, Claude and Gemini are LLMs. |
| **Provider** | The company that sells you access to an LLM: OpenAI, Anthropic, Google. You send HTTP requests to their servers. |
| **API** | *Application Programming Interface*. One program calling another over the internet. When this README says `POST /chat/completions`, that is an API endpoint — a specific URL that accepts a specific kind of request. |
| **HTTP method** | `GET` = fetch something (never changes data). `POST` = create/submit. `PUT` = replace. `DELETE` = remove. Browsers also call these "unsafe methods" because they change state. |
| **JSON** | The plain-text format APIs use to send structured data: `{"name": "Ada", "roles": ["admin"]}`. |
| **Gateway** | A middleman server. Your application talks to it; it talks to the provider. SentinelAI is a gateway — it sits between you and the AI company. |
| **Proxy** | A server that forwards a request on your behalf. Our frontend proxies API calls so the browser only ever talks to one address (see *CORS* below). |
| **Prompt** | The text you send to the LLM. |
| **Completion** | The text the LLM sends back. |
| **Policy** | A rule written as *data* rather than as buried code — e.g. *"block any prompt containing an SSN"*. Stored as JSON, versioned, so you can see what rule was in force on any given day. |
| **Guardrail** | An automatic safety check that runs before the model is called (and again on the way out). |
| **PII** | *Personally Identifiable Information* — anything that identifies a real human: name, email, phone, SSN, credit card. Leaking it to a third party is a legal problem, not just an embarrassing one. |
| **Mask** | Replacing a secret with `***`. SentinelAI's masking is **irreversible** — the original value never leaves your process, so there is nothing to leak. |
| **Audit log** | A permanent written record of every action taken, kept so you can answer "what happened?" weeks later. |
| **Hash chain** | Each log entry contains a fingerprint of the entry before it. Edit one entry and every entry after it no longer matches — so tampering *becomes detectable*, rather than merely being discouraged. |
| **Multi-tenancy** | One installation serving many separate customers (tenants), each seeing **only their own data**. |
| **Tenant / Org** | One customer organization inside the app. Everything is scoped to it. |
| **Role** | A permission level: `owner` > `admin` > `developer` > `viewer`. Higher ranks can do more. |
| **Session** | A signed cookie that tells the server "this browser is logged in as this person", so you don't retype your password on every click. |
| **Cookie** | A small piece of data a website asks your browser to remember and send back automatically on every visit. |
| **CSRF** | *Cross-Site Request Forgery* — an attack where a malicious website tricks your **already-logged-in** browser into sending a command to your app. Stopped by requiring a secret token the other site cannot read. |
| **CORS** | *Cross-Origin Resource Sharing* — the browser rule that stops website A from reading website B's data. SentinelAI avoids the whole problem by proxying instead (see below). |
| **SQLite** | A database that is just a single file on your disk. Zero setup — this is what local development uses. |
| **PostgreSQL ("Postgres")** | A proper database *server*. Used in production. |
| **Neon** | A company that hosts Postgres for you. Its free tier **never expires**, which is why this project uses it. |
| **Migration** | A numbered, version-controlled list of database schema changes, applied in order so every environment ends up with the same tables. Handled by **Alembic**. |
| **Alembic** | The tool that runs migrations for this project. |
| **Docker / container** | A sealed box that packages your app together with everything it needs to run, so it behaves identically on your laptop and in the cloud. |
| **Image** | The built, frozen contents of that box. |
| **FastAPI** | The Python web framework the backend is written in. |
| **Next.js / React** | The JavaScript framework behind the browser console you click around in. |
| **TypeScript** | JavaScript with a type checker attached — catches whole classes of mistakes before the code runs. |
| **Middleware** | Code that runs on *every* request **before** it reaches a page. Our API proxy lives here. |
| **Free tier** | The free version of a cloud service, usually with limits (memory, hours, storage) — and sometimes an expiry date. |
| **Free forever** | A free tier with **no expiry date**. Render's free *database* expires in 30 days; Neon's does not. That distinction is the entire reason for this project's deployment layout. |

### The three numbers you will see constantly

| Value | Meaning |
|---|---|
| **8123** | The backend's local port. (8000 is chosen instead by other tools on most machines, so this project uses 8123 everywhere — code, docs, scripts.) |
| **3000** | The frontend's local port. |
| **`SENTINEL_`** | Every backend setting is prefixed with this. A stray `DATABASE_URL` in your shell is deliberately ignored so it cannot hijack the app. |

### The one architectural idea worth understanding before you read on

The browser talks to **exactly one address**: the frontend. It never calls the
backend directly. Instead, `frontend/middleware.ts` — running on the server,
not in your browser — forwards API paths to the backend.

```
  your browser  ──▶  frontend (Next.js)  ──▶  backend (FastAPI)  ──▶  AI provider
   one address         middleware.ts            guardrails,
   one set of          forwards /api/*          policy, audit
   cookies             to the backend
```

Why bother? Because the backend deliberately has **no CORS support**. If the
browser called it directly, the browser would block the response. Proxying
sidesteps that entirely, and keeps the login cookies on a single origin (which
is also safer). Everything else in this README follows from that one decision.

---

## Table of contents

> **New to this?** Read [Start here](#start-here--read-this-first-if-any-of-these-words-are-unfamiliar)
> first — it defines every term used below.

1. [Why this exists](#1-why-this-exists)
2. [What it actually does](#2-what-it-actually-does)
3. [Request lifecycle](#3-request-lifecycle)
4. [Repository layout](#4-repository-layout)
5. [Quickstart (local, no Docker)](#5-quickstart-local-no-docker)
6. [Using the console](#6-using-the-console)
7. [HTTP API](#7-http-api)
8. [Configuration reference](#8-configuration-reference)
9. [Security model](#9-security-model)
10. [Database](#10-database)
11. [Evaluations](#11-evaluations)
12. [Testing](#12-testing)
13. [Docker Compose](#13-docker-compose)
14. [**Deploying live on the internet**](#14-deploying-live-on-the-internet)
15. [Continuous integration](#15-continuous-integration)
16. [Documentation index](#16-documentation-index)
17. [Troubleshooting](#17-troubleshooting)
18. [Design decisions & honest limitations](#18-design-decisions--honest-limitations)

---

## 1. Why this exists

Teams wiring an LLM into production usually end up with the same five gaps:

| Gap | What goes wrong | What SentinelAI does |
|---|---|---|
| **No guardrails** | PII, API keys and passwords are shipped to a third-party model | Detects and masks **before** the provider call; blocks on policy |
| **No policy layer** | Prompt rules live in scattered `if` statements, unversioned | JSON conditions with **version snapshots** and a dry-run preview |
| **No routing control** | Every call hits the most expensive model, or a model that can't do the task | Capability gate → cost/latency caps → priority → deterministic tie-break, **fail-closed** |
| **No audit trail** | You cannot prove what happened, or whether the log was edited | Per-org **hash-chained** log, independently verifiable, exportable |
| **No measurement** | Changes to prompts/policies are shipped blind | Analytics (cost, security, model mix) + offline **evaluation runs** with regression deltas |

Everything above ships working, tested, and documented — not as a scaffold.

---

## 2. What it actually does

### 2.1 Gateway
`POST /api/v1/chat/completions` accepts a normalized completion request and
runs the full pipeline. Responses carry `status`, `policy_outcome`, `findings`,
`content`, `usage`, `demo`, and a typed `error` — never fabricated text.

### 2.2 Guardrails (`ai/guardrails/`)
- **PII detection** — detectors for `ssn`, `card` (Luhn-checked), `email`,
  `phone`, `api_key`, `jwt`. `mask_pii()` is **irreversible**: the masked form
  is what leaves the process, so raw secrets never reach a provider.
- **Prompt injection scoring** — heuristics for *instruction override*,
  *secret exfiltration*, *hierarchy manipulation*, *safety bypass* →
  `injection_score` plus a category attached to the finding.
- **Output guard** — post-response egress checks on provider output.
- **Policy engine** — evaluates JSON conditions (`eq`, `ne`, `in`, `gte`, …)
  against the request context and selects a rule action.

### 2.3 Policy actions
| Action | Behaviour |
|---|---|
| `block` | Request ends as `blocked`, findings + audit events written, **no provider call at all** |
| `mask` | Prompt irreversibly masked **before** the provider call, request continues |
| `warn` | Passes through; findings attached to the record for review |

Policies are versioned — editing one snapshots the old version — and
`POST /api/v1/policies/preview` lets you dry-run a prompt against current
policy without spending a token.

### 2.4 Routing (`ai/routing/engine.py`) — fails closed
1. **Capability gate** — drops models lacking a required capability.
2. **Constraints** — max cost / max latency caps.
3. **Priority** — explicit ordering.
4. **Deterministic tie-break** — stable, so identical inputs route identically.

If **no** candidate survives, you get a **typed error** and *no provider call*.
There is no silent fallback to "whatever is available" — that is the single
most common way a "smart router" quietly becomes a liability.

### 2.5 Providers (`ai/providers/`)
`mock`, `openai`, `anthropic`, `gemini`, `ollama` — all implemented as direct
REST calls via `httpx` (no provider SDK dependency), with timeouts, bounded
retries, and typed upstream errors.

> **The mock provider is the only synthetic source and every one of its
> responses is labelled `demo: true`.** Nothing in this repo invents a
> provider response and passes it off as real.

### 2.6 Audit (`app/services/audit.py`)
Each event stores `seq`, `prev_hash`, `hash` over a canonical serialization,
scoped per organization. `GET /api/v1/admin/audit/verify` **recomputes the
whole chain** and tells you how many entries it checked; `GET
/api/v1/admin/audit/export` dumps it (default CSV) as your tamper-detection
anchor.

### 2.7 Analytics
`/analytics/overview`, `/costs`, `/security`, `/models` — spend over time,
block/warn rates, top findings, model mix. All computed from `usage_metrics`
and `security_events`, so the numbers are the same ones the audit log
records.

### 2.8 Evaluations (`ai/evaluation/` + `evals_api.py`)
Datasets of cases → runs executed **through the real gateway pipeline** →
deterministic metrics (`evaluate_case`, `summarize_results`,
`regression_delta`). Compare a run against a baseline to see whether a policy
or prompt change made things better or worse *before* shipping it.

### 2.9 Console (Next.js)
Eleven authenticated pages plus login — see [§6](#6-using-the-console).

---

## 3. Request lifecycle

```
POST /api/v1/chat/completions
  ├─ RequestContextMiddleware   assign X-Request-ID + one structured log line
  │                             per request; enforce CSRF double-submit on
  │                             cookie-authenticated unsafe methods
  ├─ RequestSizeMiddleware      413 before the body is ever buffered
  ├─ get_auth                   session cookie → org/user/role, re-validated
  │                             on EVERY request (no trusted cached claims)
  ├─ org rate limit             sliding window: in-process, Redis if configured
  ├─ request_service.run_pipeline → ai.gateway.pipeline.run_pipeline
  │   ├─ load org policies + model candidates (DB → plain objects)
  │   ├─ guardrails: pii.find/mask + injection.detect → findings + score
  │   ├─ policy_engine: conditions → action  (block | mask | warn)
  │   ├─ routing.route:  gate → constraints → priority → tie-break, FAIL CLOSED
  │   ├─ providers registry → adapter (timeout + bounded retries)
  │   └─ persist: request_record, security_events, usage_metrics,
  │               audit append_event (hash-chained)
  └─ ChatCompletionOut
```

**Fail-closed guarantees**
- No eligible model → typed error, no provider call.
- Upstream failure → `status=error` with a real category
  (`provider_error`, `provider_timeout`, `policy_blocked`, `rate_limited`, …),
  content untouched.
- `mock` is the only synthetic source, always `demo: true`.

---

## 4. Repository layout

```
sentinelai/
├── README.md                  ← you are here
├── SECURITY.md                vulnerability disclosure policy
├── .env.example               every setting, commented
├── docker-compose.yml         Postgres + Redis + backend + frontend
├── .github/workflows/         backend.yml, frontend.yml
│
├── ai/                        ★ top-level, framework-free domain library
│   ├── gateway/pipeline.py      run_pipeline — the §3 sequence (I/O injected)
│   ├── guardrails/              pii, injection, output_guard, policy_engine
│   ├── routing/engine.py        Candidate, RoutingConstraints, route()
│   ├── providers/               base protocol, registry, mock/openai/
│   │                            anthropic/gemini/ollama adapters
│   └── evaluation/metrics.py    evaluate_case, summarize, regression_delta
│
├── backend/                   FastAPI web application
│   ├── app/main.py              app factory, middleware, error handlers
│   ├── app/api/v1/              9 route modules (§7)
│   ├── app/services/            request_service, audit, ratelimit, deps, seed
│   ├── app/models/              SQLAlchemy 2 models
│   ├── app/schemas/             Pydantic DTOs (the only things crossing HTTP)
│   ├── app/core/                config, security, errors, logging, bootstrap
│   ├── alembic/                 migrations (head = 98827150dfb3)
│   └── tests/                   117 tests
│
├── frontend/                  Next.js console
│   ├── app/(app)/               11 authenticated pages
│   ├── app/login/               login / register
│   ├── components/              shadcn-style UI + feature components
│   ├── lib/api.ts               fetch wrapper, CSRF, error envelope
│   ├── e2e/governance.spec.ts   Playwright end-to-end flow
│   ├── next.config.ts           intentionally empty: no build-time rewrites
│   └── middleware.ts            same-origin proxy to the API (§7)
│
├── docs/                      9 documents (§16)
├── infra/                     Dockerfile.backend, Dockerfile.frontend
└── scripts/                   dev.sh, migrate.sh, smoke.py
```

### Why `ai/` is a separate top-level package
`backend/app` **→** `ai`, never the reverse. `ai` imports no FastAPI, no
SQLAlchemy, no database — its I/O is injected. That means guardrails, routing
and evaluation are unit-testable standalone (the pytest suite covers both
packages), and you can lift `ai/` into another service unchanged.

At runtime `app/core/bootstrap.py` resolves the top-level `ai` package by
walking three levels up from `backend/app/core`. **Docker images mirror that
layout** (`/srv/sentinelai/{backend,ai}`) — if you restructure the folders,
update that path or imports break.

---

## 5. Quickstart (local, no Docker)

Nothing here needs Docker, Postgres, Redis, or a single API key — the mock
provider carries the whole demo.

### Prerequisites
- **Python 3.11+** (`requires-python = ">=3.11"`)
- **Node 20+** (developed on Node 24 / npm 11)
- Git

### 5.1 Backend

```bash
cd backend
python -m venv .venv

# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install ".[dev]"
```

Configure (SQLite + mock provider are the defaults, so this is optional):

```bash
cp .env.example .env
```

Run it:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8123 --reload
```

Verify:

```bash
curl http://127.0.0.1:8123/health          # {"status":"ok",...}
curl http://127.0.0.1:8123/ready           # includes "database": "ok"
open  http://127.0.0.1:8123/docs           # interactive OpenAPI
```

> **Port 8123, not 8000.** 8000 is commonly occupied on dev machines; 8123 is
> used consistently in code, Compose, docs and CI comments.

### 5.2 Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**.

The browser talks **only** to :3000. `frontend/middleware.ts` forwards `/api/*`,
`/health`, `/ready` and `/metrics` to the backend (`SENTINEL_API_ORIGIN`,
default `http://127.0.0.1:8123`), so nothing is cross-origin and the session
cookies stay first-party. See [§7](#7-http-api) for why this matters.

> It is `middleware.ts` and deliberately **not** `rewrites()` in
> `next.config.ts`: Next evaluates `rewrites()` once during `next build` and
> freezes the result into `.next/routes-manifest.json`, so anything it reads
> from `process.env` is a build-time value. A Docker build stage that does not
> have `SENTINEL_API_ORIGIN` silently bakes the `http://127.0.0.1:8123`
> fallback into the image and every proxied path 500s at runtime. Middleware
> runs per request in the serving process, so the variable is read when it is
> actually used and can be changed without a rebuild.

### 5.3 One-shot script

```bash
./scripts/dev.sh          # starts both (POSIX shells)
```

### 5.4 First login

On first boot with an empty database and `SENTINEL_SEED_DEMO_DATA=true`
(the default), the app seeds a demo organization, user, policies and provider —
**every seeded row is flagged `is_demo_data`** and named "…(Demo)":

| Field | Value |
|---|---|
| Email | `demo@sentinelai.dev` |
| Password | `demo-password-123` |

**This account is development-only.** Set `SENTINEL_SEED_DEMO_DATA=false`
and `SENTINEL_ALLOW_DEV_LOGIN=false` before any shared deployment.

---

## 6. Using the console

| Page | What you do there |
|---|---|
| **`/` Overview** | Org KPIs: request volume, block/warn rate, spend, model mix |
| **`/playground`** | Send a real prompt through the full pipeline; see `status`, `policy_outcome`, findings, usage, and the `demo` flag |
| **`/requests`** + `/requests/[id]` | Filterable request history; drill into one request's findings, routing decision and timing |
| **`/policies`** | Create/edit versioned JSON policies; **preview** a prompt against them dry-run |
| **`/providers`** | Register providers/models; secret **references** only — never raw keys in the DB |
| **`/models`** | Catalog of available models and their capabilities/costs |
| **`/analytics`** | Cost, security and model charts (Recharts) |
| **`/audit`** | Walk the hash chain — **Verify chain** reports `checked N` — and export |
| **`/evaluations`** | Create datasets (≤500 embedded cases), launch runs, compare to baseline |
| **`/settings`** | Org settings, members and roles (owner/admin/developer/viewer) |
| **`/login`** | Sign in / create account (fresh org per registration) |

---

## 7. HTTP API

Base path: **`/api/v1`**. Interactive docs at **`/docs`**, ReDoc at
`/redoc`, spec at `/api/v1/openapi.json`. Full detail in
**[`docs/API.md`](docs/API.md)**.

### Route surface

| Area | Module | Endpoints |
|---|---|---|
| Ops | `ops` | `GET /health` · `GET /ready` · `GET /metrics` (also at root) |
| Auth | `auth` | `POST /register` · `POST /login` · `POST /dev-login` · `POST /logout` · `GET /me` · `POST /switch-org` |
| Gateway | `gateway` | `POST /chat/completions` · `GET /models` |
| Requests | `requests_api` | `GET /requests` · `GET /requests/{id}` |
| Policies | `policies_api` | `GET/POST /policies` · `GET/PUT/DELETE /policies/{id}` · `POST /policies/preview` |
| Analytics | `analytics_api` | `GET /analytics/overview` · `/costs` · `/security` · `/models` |
| Evals | `evals_api` | `GET/POST /datasets` · `GET /datasets/{id}` · `GET /datasets/{id}/cases` · `GET/POST /runs` · `GET /runs/{id}` |
| Admin | `admin_api` | providers · models · members · teams · projects · settings · `GET /admin/audit` · `/admin/audit/verify` · `/admin/audit/export` |

### Authentication & CSRF — read this before scripting against the API

- **Cookie based.** `sentinel_session` (HttpOnly, TTL
  `SENTINEL_SESSION_TTL_HOURS`, default 12h) plus a JS-readable `sentinel_csrf`.
- **Every unsafe request** (`POST`/`PUT`/`PATCH`/`DELETE`) must echo the CSRF
  cookie in the header **`X-CSRF-Token`**, or you get `403 csrf_failed`.
  This is enforced centrally in middleware, so no route can forget it.
- **No CORS.** The backend ships **no CORS middleware, by design**. From a
  script on the same host, call `http://127.0.0.1:8123` directly. From a
  browser, go through the Next proxy — do not set `NEXT_PUBLIC_API_URL` to an
  absolute origin unless you deliberately add permissive CORS.

**Scripting example (bash):**

```bash
BASE=http://127.0.0.1:8123/api/v1
JAR=$(mktemp)

# 1. register (or POST /auth/login) — response sets the cookies
curl -c "$JAR" -X POST "$BASE/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"org_name":"Acme","full_name":"Ada","email":"ada@acme.test","password":"correct-horse-battery"}'

# 2. pull the CSRF cookie out of the jar and echo it back
CSRF=$(awk '$6=="sentinel_csrf" {print $7}' "$JAR")

# 3. any unsafe call
curl -b "$JAR" -X POST "$BASE/chat/completions" \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
  -d '{"messages":[{"role":"user","content":"hello"}]}'
```

On **Windows PowerShell**, inline JSON quoting breaks — write the body to a
file and use `--data-binary '@file'`, or `Invoke-RestMethod -SessionVariable s`.

### Error envelope

Every error — validation, auth, 404, 405, unhandled — returns the same shape:

```json
{ "error": { "code": "csrf_failed", "message": "...", "details": {}, "request_id": "..." } }
```

`request_id` matches the `X-Request-ID` header and the audit/log entries, so a
user-reported error is traceable end to end.

### Behaviour notes that bite people
- A **blocked** chat returns **HTTP 200** with `policy_outcome: "block"` —
  policy denial is a *result*, not a transport error.
- `/admin/audit/export` defaults to **csv**.
- `POST /datasets` takes **embedded `cases[]`** (max 500), not an upload.
- Requests `q` is a request-ID **exact/prefix** match, not free text.

---

## 8. Configuration reference

All backend settings use the **`SENTINEL_` prefix** — unprefixed names are
silently ignored (so a stray `DATABASE_URL` in your shell can't hijack the
app). Copy `.env.example` → `.env`. `SENTINEL_APP_ENV` accepts only
`development | production | test`.

| Variable | Default | What it does |
|---|---|---|
| **Runtime** | | |
| `SENTINEL_APP_ENV` | `development` | Selects strictness; `production` fails fast on missing secrets and disables `create_all` |
| `SENTINEL_LOG_LEVEL` | `INFO` | Structured JSON log level |
| `SENTINEL_AUTH_SECRET` | dev literal | Signs session cookies. **128+ bits, unique per env.** Startup fails in production if unset |
| **Database** | | |
| `SENTINEL_DATABASE_URL` | `sqlite:///./data/sentinelai.db` | Postgres in Compose/prod: `postgresql+psycopg://user:pass@host:5432/db` |
| `SENTINEL_DATABASE_ECHO` | `false` | Log SQL |
| **Cache / rate limits** | | |
| `SENTINEL_REDIS_URL` | *(empty)* | Empty = **in-process** sliding window. Set this **before** scaling replicas, or limits are per-process |
| `SENTINEL_RATE_LIMIT_PER_MINUTE` | `60` | Per-org chat limit |
| `SENTINEL_LOGIN_RATE_LIMIT_PER_MINUTE` | `10` | Per-IP+email login limit |
| **Auth & session** | | |
| `SENTINEL_SESSION_COOKIE_SECURE` | `false` | **`true` behind TLS** |
| `SENTINEL_SESSION_TTL_HOURS` | `12` | Session lifetime |
| `SENTINEL_ALLOW_DEV_LOGIN` | `true` | Enables `POST /auth/dev-login`. **Must be `false` in production** |
| **Gateway** | | |
| `SENTINEL_GATEWAY_TIMEOUT_SECONDS` | `60` | Provider call timeout |
| `SENTINEL_GATEWAY_MAX_RETRIES` | `2` | Bounded retries |
| `SENTINEL_MAX_REQUEST_BYTES` | `65536` | 413 guard, enforced **before** buffering |
| **Privacy & retention** | | |
| `SENTINEL_STORE_PROMPT_CONTENT` | `false` | `true` stores **masked** prompt text on request records. Off by default |
| `SENTINEL_DEFAULT_RETENTION_DAYS` | `90` | Request retention |
| `SENTINEL_AUDIT_RETENTION_DAYS` | `365` | Audit retention |
| **Seed** | | |
| `SENTINEL_SEED_DEMO_DATA` | `true` | Seeds demo org/user when DB is empty. **`false` in production** |
| **Providers** | | |
| `SENTINEL_OPENAI_API_KEY` / `_BASE_URL` | empty / `https://api.openai.com/v1` | Leave keys empty to run **mock-only** |
| `SENTINEL_ANTHROPIC_API_KEY` / `_BASE_URL` | empty / `https://api.anthropic.com` | |
| `SENTINEL_GEMINI_API_KEY` / `_BASE_URL` | empty / Google | |
| `SENTINEL_OLLAMA_BASE_URL` | `http://localhost:11434` | Local models |
| **Frontend** | | |
| `SENTINEL_API_ORIGIN` | `http://127.0.0.1:8123` | **Server-side**: proxy target used by `frontend/middleware.ts`. Read from the environment **on every request**, so it can be changed without rebuilding the frontend. |
| `NEXT_PUBLIC_API_URL` | *(unset)* | Leave unset. Only set if the backend sends permissive CORS |

> **Never commit real keys.** `.env` is gitignored; providers are stored in the
> DB as **`secret_ref`** names resolved to `SENTINEL_*` env vars at call time,
> so no raw credential ever touches the database.

---

## 9. Security model

Full detail: [`docs/SECURITY.md`](docs/SECURITY.md) ·
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) · [`SECURITY.md`](SECURITY.md)
(disclosure policy).

- **Passwords** — `scrypt`, per-user salt.
- **Sessions** — signed cookies via `itsdangerous`, HttpOnly, TTL-bound,
  re-validated from the DB on **every** request (no trusted cached claims).
- **CSRF** — double-submit cookie + `X-CSRF-Token`, enforced in middleware for
  all cookie-authenticated unsafe methods.
- **Multi-tenancy** — every row carries `org_id`; queries are filtered by the
  org **from the session, never from the payload**. `app/services/deps.py` is
  the single chokepoint. Roles `owner > admin > developer > viewer` with
  minimum-rank checks (`ROLE_ORDER`).
- **Secrets** — never logged (structured-logger redaction is tested by
  `test_logging_redaction.py`), never stored in the DB, referenced by name.
- **Prompt content** — off by default (`SENTINEL_STORE_PROMPT_CONTENT=false`);
  when on, only the **masked** form is persisted.
- **Audit integrity** — hash chain, per-org sequence, verifiable and
  exportable; retention 365 days by default.
- **Supply chain** — pinned action SHAs/tags in CI, pinned image tags in
  Compose, no provider SDKs (plain `httpx`).
- **No CORS by design** — see [§7](#7-http-api).

---

## 10. Database

Details: [`docs/DATABASE.md`](docs/DATABASE.md).

- **SQLite** for local dev (`backend/data/sentinelai.db`, gitignored),
  **PostgreSQL 16** for Compose and production, both behind **SQLAlchemy 2**
  sync sessions. Sync is deliberate: the work is I/O-light and transaction
  boundaries stay obvious.
- **Schema source of truth**
  - Dev/test: `Base.metadata.create_all` at boot.
  - **Production: Alembic only.** `create_all` is disabled in the production
    lifespan. Apply with `./scripts/migrate.sh upgrade head`.
- Current head: **`98827150dfb3`** (single initial revision).
  CI runs `alembic upgrade head` then `alembic check` to catch drift.
- Core tables: `organizations`, `users`, `memberships`, `teams`, `projects`,
  `policies` (+ versions), `providers`, `models`, `request_records`,
  `security_events`, `usage_metrics`, `audit_events`,
  `eval_datasets`/`eval_cases`/`eval_runs`.
- **Rate limits** are *not* in the DB — in-process sliding window by default,
  Redis when `SENTINEL_REDIS_URL` is set.

**Resetting local data:** stop the server and delete all three SQLite files
together — `sentinelai.db`, `sentinelai.db-wal`, `sentinelai.db-shm`. Deleting
only `.db` leaves a stale WAL behind and the schema silently survives.

---

## 11. Evaluations

Details: [`docs/EVALUATION.md`](docs/EVALUATION.md).

- **Datasets** hold cases; `POST /api/v1/evals/datasets` takes `cases[]`
  inline (max 500 per call).
- **Runs** execute each case *through the real gateway pipeline* — so a run
  exercises guardrails, policy and routing exactly as production does.
- **Metrics are deterministic** — `evaluate_case`, `summarize_results`,
  `regression_delta` compare a run to a baseline and flag regressions. No LLM
  judges, no non-reproducible scoring.

Typical loop: run baseline → change a policy or prompt → run again → read the
regression delta → ship only if it improved.

---

## 12. Testing

Run from `backend/` (backend) and `frontend/` (JS).

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check . ../ai` | clean |
| Backend tests | `pytest` | **117 passed** (coverage of `app` = **79.7%**) |
| Migrations | `alembic upgrade head` → `alembic current` → `alembic check` | head applied, *No new upgrade operations detected* |
| Smoke | live uvicorn + `scripts/smoke.py` | **6/6 PASS** |
| Types | `npx tsc --noEmit` | 0 errors |
| Frontend lint | `npm run lint` | clean |
| Unit tests | `npm test` | **26/26** |
| Build | `npm run build` | **15/15 routes** |
| E2E | `npx playwright test` | **1 passed** |

**Backend test files** — `test_api.py`, `test_audit_chain.py`,
`test_guardrails.py`, `test_logging_redaction.py`, `test_pipeline.py`,
`test_policy_engine.py`, `test_routing.py` (+ `conftest.py`, `helpers.py`).

**Frontend tests** — `lib/api.test.ts`, `app/login/page.test.tsx`,
`components/playground/chat-result.test.tsx`,
`components/requests/requests-table.test.ts`.

**E2E** — `frontend/e2e/governance.spec.ts` runs against the **live stack**:
register → chat → blocked request → requests history → audit chain verify →
analytics. It registers a fresh organization per run and uses Playwright's
**bundled Chromium** (no `channel: 'chrome'`).

> Coverage gate in CI is `--cov-fail-under=79`, set just below the measured
> 79.6% so real regressions fail without flaking on rounding.

---

## 13. Docker Compose

```bash
docker compose up --build
# frontend  http://localhost:3000
# backend   http://localhost:8123  (API + /docs)
```

Services: `db` (postgres:16-alpine), `redis` (redis:7-alpine), `backend`
(runs **`alembic upgrade head` before uvicorn**), `frontend` (Next.js).
Volumes: `pgdata`, `redisdata`, `backend_data`.

The frontend is configured with `SENTINEL_API_ORIGIN=http://backend:8000` —
an **internal** address — so the browser still only talks to :3000.

> ⚠️ **Honest status:** Docker was not available on the authoring host, so
> this stack is *authored but not executed there*. The first
> `docker compose up --build` is a verification step: check `/ready`
> reports `"database": "ok"` and that the console loads. CI runs the same
> lint/test/migration commands as [§12](#12-testing).

---

## 14. Deploying live on the internet

Putting this online needs three things, and this repository uses a different
free provider for each — **on purpose**:

| You need | Provider used here | Why this one |
|---|---|---|
| A **database** | Neon (Postgres) | Its free tier **never expires** |
| Somewhere to run the **backend API** | Render | Runs Docker with no credit card |
| Somewhere to serve the **frontend** | Vercel | Free static/Next.js hosting, no expiry |

The app already ships everything required — a Dockerfile for the backend,
Alembic migrations, `/health` + `/ready` + `/metrics` probes, a
server-side proxy in `frontend/middleware.ts`, and a production env preset.

> **What I can and cannot do for you.** I can push the code, write the
> config, and give you exact commands. I **cannot** create a cloud account,
> enter a credit card, or sign into your provider — those need you. Steps 1–4
> below are written so your part is ~10 minutes of paste-able clicks. The one
> exception is a **Render API key**: given one, I can do the Render portion
> myself through the REST API — which is how the live API URL below was
> created.

---

### The topology this repository targets: three free services

Each piece does one job, and each free tier **never expires**:

| Piece | Provider | URL | Free tier (verified Oct 2026) |
|---|---|---|---|
| **Database** | [Neon](https://neon.tech) (Postgres 18) | — (you hold the connection string) | No expiry. 0.5 GB storage, ~190 compute-hours/mo, **scales to zero** when idle |
| **Backend API** | Render (web service, Docker) | https://sentinelai-api-ew0b.onrender.com | No expiry, but **spins down after 15 min idle** (~60 s to wake) |
| **Frontend console** | Vercel (Hobby) | https://sentinelai-iota-swart.vercel.app | No expiry. 100 GB bandwidth/mo |
| **Source** | GitHub | https://github.com/Gunjannnn30/sentinelai @ `master` | — |

**Why three services and not one?** Because of one fact that quietly ruins
"free forever" deployments: **Render's free Postgres expires after 30 days.**
On 2026-11-26 the database backing the old all-Render layout stops existing,
and the site with it. Neon's free Postgres has no such date. The app already
spoke Postgres, so switching costs one connection string — no code change and
no data-model migration.

**Why the browser only ever talks to Vercel:** the frontend runs
`frontend/middleware.ts` server-side on Vercel, forwarding `/api/*`,
`/health`, `/ready` and `/metrics` to the Render API using the
`SENTINEL_API_ORIGIN` environment variable. This is [§7](#7-http-api)'s proxy
pattern, unchanged. It means the backend still needs no CORS, and the session
and CSRF cookies stay first-party on the Vercel origin.

> ⚠️ **Honest caveat.** Vercel's middleware has an execution time limit. On the
> *first* request after the Render service has been asleep for a while (~60 s
> wake), the proxy may time out. A second click succeeds. This is a free-tier
> reality, not a bug in the code.

---

### Step 1 — Create the Neon database (~3 minutes, you)

No credit card is required.

1. Go to <https://neon.tech> and **Sign up** (GitHub sign-in works).
2. On the welcome screen choose **Skip / build your own**, name the project
   `sentinelai`, keep the region **Oregon (us-west-2)** so it sits beside the
   Render API.
3. Select the **Free** plan and press **Create project**.
4. In the **Connection Details** dialog, switch the type to **Direct**
   (host looks like `ep-xxxx-us-west-2.aws.neon.tech`).
   **Do not use the `...-pooler` address** — that is PgBouncer, a connection
   pooler that breaks Alembic migrations and psycopg's prepared statements
   against a single long-running container like Render's.
5. Copy the full URL. It looks like:
   `postgres://neondb_owner:AbC123xyz@ep-xxxx-us-west-2.aws.neon.tech/neondb?sslmode=require`
6. Paste it somewhere safe — you need it in Step 2. **This URL is a password.**
   Anyone with it can read your database. Never commit it to GitHub.

No backend code change is needed. `backend/app/core/config.py` already rewrites
a bare `postgres://` URL onto the psycopg v3 driver that the project ships, so
the string Neon gives you works as-is.

### Step 2 — Point the Render API at Neon (~2 minutes, you)

The backend service (`sentinelai-api`) already exists at
https://sentinelai-api-ew0b.onrender.com. You are changing only its database
environment variable.

1. Open <https://dashboard.render.com> and sign in.
2. In the left sidebar click **Blueprints** (or **Services**), find the
   SentinelAI API service, and open it.
3. Click **Environment** in the top tab bar.
4. Find the row named `SENTINEL_DATABASE_URL`. Click it, clear whatever is
   there, and paste your **Neon direct** URL from Step 1.
5. Press **Save**. Render shows a banner: *changes are not applied until you
   deploy.*
6. Click **Manual Deploy** → **Clear build cache & deploy**. Wait for the
   badge to turn **Live** (2–5 minutes on a cold build).

Because `render.yaml` marks `SENTINEL_DATABASE_URL` as `sync: false`, the
Blueprint deliberately does not touch it — the value you paste is the value
that stays.

**Verify the API before continuing.** Open
<https://sentinelai-api-ew0b.onrender.com/ready>. You must see:

```json
{"status": "ok", "database": "ok", "version": "...", ...}
```

`"database": "ok"` is the signal that Alembic ran against the empty Neon
database at container start and built the schema. If you see `database: "error"`
instead, the connection string is wrong or you used the `-pooler` host.

### Step 3 — Deploy the frontend on Vercel (~4 minutes, you)

No code change is needed; Vercel reads `frontend/middleware.ts` at request time.

1. Go to <https://vercel.com/new> and **import** the GitHub repository
   `Gunjannnn30/sentinelai`.
2. In the **Configure Project** screen, expand **Environment Variables** and add
   exactly one:
   - **Name:** `SENTINEL_API_ORIGIN`
   - **Value:** `https://sentinelai-api-ew0b.onrender.com`
3. Leave every other setting at its default. Vercel auto-detects Next.js and
   reads the Root Directory from the repo (`frontend` is already configured as
   the app directory in this project's setup — if the import screen asks for
   a Root Directory, set it to `frontend`).
4. Press **Deploy**. First build takes about 1–2 minutes.
5. When it finishes, Vercel gives you a URL like
   `https://sentinelai-xxxx.vercel.app`. Open it — the login page should load.

> ✅ **This repository is already deployed.** The live console is
> <https://sentinelai-iota-swart.vercel.app>. If you import the repo yourself
> you will get your *own* URL in the same format.

Leave `NEXT_PUBLIC_API_URL` **unset**. It is not read; the proxy reads
`SENTINEL_API_ORIGIN` at request time, so you can repoint the backend later
without rebuilding.

### Step 4 — Verify the whole path (~1 minute)

Run all four checks:

| Check | URL | Expected |
|---|---|---|
| API direct | `https://sentinelai-api-ew0b.onrender.com/ready` | `"database": "ok"` |
| Console loads | https://sentinelai-iota-swart.vercel.app | login page |
| Proxy works | https://sentinelai-iota-swart.vercel.app/ready | the API's own JSON, forwarded |
| CSRF still enforced | see the three-line curl below | `403 csrf_failed` |

That last one matters. CSRF protection lives in the **backend**, not in the
proxy, so routing through Vercel cannot weaken it.

Run it exactly — note that `POST /auth/login` is deliberately **exempt** from
CSRF (you have no session cookie yet), so it returns `200` and hands you a
`csrf_token`. The protection bites on every request *after* login:

```bash
# 1. Log in. Keep the cookies, capture the token it returns.
curl -c jar.txt -s -X POST https://sentinelai-iota-swart.vercel.app/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@sentinelai.dev","password":"demo-password-123"}' | jq -r .csrf_token

# 2. Try a state-changing call WITHOUT the token -> expect HTTP 403 csrf_failed
curl -b jar.txt -s -X POST https://sentinelai-iota-swart.vercel.app/api/v1/auth/logout
```

If step 2 prints `"code": "csrf_failed"` you have confirmed the whole path:
Vercel serving the app, the proxy forwarding to Render, Render reaching Neon,
and the backend still refusing to act on an unauthenticated write.

Then sign in as the seeded demo org — `demo@sentinelai.dev` /
`demo-password-123` — or register your own account from the login page.

**How the backend was provisioned** (for reference, not to repeat): scripted
against `https://api.render.com/v1` with a personal API key — `GET /owners`
for the workspace id, `POST /services` with `serviceDetails.runtime=docker`
pointing at `infra/Dockerfile.backend` (health check `/ready`), then
`PUT /services/{id}/env-vars` (note: that endpoint **replaces** the whole set,
it does not merge) and an explicit `POST /services/{id}/deploys`, polled until
`deploy.status == live`. Schema came from Alembic only — the backend image runs
`alembic upgrade head` on start, and `create_all` is disabled in the production
lifespan.

**Free-tier caveats, stated plainly:**

- **Neon** compute **scales to zero** after ~5 minutes idle. The first query
  after that takes 1–3 s. Storage never expires.
- **Render** spins down after 15 min idle (~60 s to wake) and is limited to
  512 MB RAM / 0.1 CPU. You get 750 free instance-hours per workspace per
  month; exhaust them and free services suspend until the next calendar month.
- **Vercel Hobby** caps bandwidth and function duration — see the middleware
  timeout caveat above.
- None of the three requires a credit card.

**Before treating this as real production:** set
`SENTINEL_SEED_DEMO_DATA=false` on Render, register your own owner account,
and rotate `SENTINEL_AUTH_SECRET` (rotating it invalidates every existing
session). See the [checklist](#141-production-checklist). **Revoke any Render
or Neon API key** you pasted into scripts once you are satisfied (Account
Settings → API Keys).

---

### 14.0 Production environment (required in every option)

```bash
# Generate a real secret — do NOT reuse the dev one
openssl rand -hex 32          # Windows: python -c "import secrets;print(secrets.token_hex(32))"
```

```dotenv
SENTINEL_APP_ENV=production
SENTINEL_AUTH_SECRET=<the value you just generated>
SENTINEL_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/sentinel
SENTINEL_REDIS_URL=redis://host:6379/0
SENTINEL_SESSION_COOKIE_SECURE=true
SENTINEL_ALLOW_DEV_LOGIN=false
SENTINEL_SEED_DEMO_DATA=false
SENTINEL_STORE_PROMPT_CONTENT=false
```

Startup **fails fast** in production if `SENTINEL_AUTH_SECRET` is missing —
that is intentional.

---

### Option A — VPS + Docker Compose (most control, ~$4–6/mo)

Best if you want the whole stack on one box you control. Works on any
provider: Hetzner, DigitalOcean, Vultr, OVH, AWS EC2 t4.micro, etc.

**1. Provision** a 1–2 GB Ubuntu 22.04/24.04 VM. Open only **22, 80, 443**.

**2. Install Docker:**
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

**3. Get the code:**
```bash
git clone https://github.com/Gunjannnn30/sentinelai.git && cd sentinelai
```

**4. Create `.env`** with the values from §14.0. Set
`SENTINEL_DATABASE_URL` to the Compose Postgres if you keep it in-house:
```bash
postgresql+psycopg://sentinel:sentinel@db:5432/sentinel
```

**5. Rotate the Compose secrets** — edit `docker-compose.yml`: change the
`db` passwords, and set `SENTINEL_AUTH_SECRET` from your generated value
(don't leave `change-me-before-staging`).

**6. Launch:**
```bash
docker compose up -d --build
docker compose ps          # all healthy
curl -s localhost:8123/ready
```

**7. TLS + reverse proxy** — put Caddy in front (automatic HTTPS, 6 lines):
```bash
sudo apt-get install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
yourdomain.com {
    reverse_proxy localhost:3000
}
api.yourdomain.com {
    reverse_proxy localhost:8123
}
EOF
sudo systemctl reload caddy
```
Caddy fetches certificates automatically. Point DNS A records at the VM first.

> **Why two hostnames?** The console proxies `/api/*` to the backend
> server-side, so you *can* serve everything from one hostname (proxy only
> `:3000`). Split them if you want the API callable directly by scripts.

**8. Verify**
- `https://yourdomain.com` loads the console
- `/playground` → send a prompt → see `demo: true` (mock) or a real response
- `/audit` → **Verify chain** → `checked N`
- `https://api.yourdomain.com/ready` → `"database": "ok"`

**9. Upgrades**
```bash
git pull
docker compose build backend frontend
./scripts/migrate.sh upgrade head     # schema comes ONLY from Alembic
docker compose up -d
```
Back up with `pg_dump -Fc` on a schedule, and keep `audit/export` snapshots
alongside — they're your tamper-detection anchor.

---

### Option B — Render Blueprint for the API (free, no server to manage)

Render is currently the only mainstream host that runs Docker on a
**no-credit-card** free tier. This repo's `render.yaml` is a Render Blueprint
that now provisions **the API service only** — the database is external
(Neon), because Render's free Postgres expires in 30 days. The live walkthrough
is at the [top of §14](#the-topology-this-repository-targets-three-free-services).

From a fresh Render account:

1. Create the Neon database (§14, Step 1) and copy its **direct** URL.
2. Push the repo to GitHub.
3. Render dashboard → **New → Blueprint** → select the repo.
4. When prompted, paste your **Neon** URL for **`SENTINEL_DATABASE_URL`**
   (it is `sync: false`, so Render will not generate one). Leave
   **`SENTINEL_OPENAI_API_KEY`** blank to stay mock-only.

Everything else is specified in the Blueprint: the backend Dockerfile, the
health check on `/ready`, `SENTINEL_AUTH_SECRET` (generated by Render, never
committed), and the full production posture
(`ALLOW_DEV_LOGIN=false`, `SESSION_COOKIE_SECURE=true`).

Migrations run **inside the container at start** (`alembic upgrade head`,
same as docker-compose), because production deliberately disables `create_all`
— without it the API would boot against an empty database and fail `/ready`.
Confirm after the first deploy that `/ready` reports `"database": "ok"`. If you
ever scale the API past one replica, run migrations once per release
out-of-band instead of letting every instance run them.

> ⚠️ **Free-tier caveats for the Render API (verified Oct 2026):**
> - **512 MB / 0.1 CPU** and **spin down after 15 min** of no traffic
>   (~60 s to wake on the next visit).
> - **750 free instance-hours per workspace per month**. Exhaust them and free
>   services suspend until the next calendar month.
> - No credit card needed. The database is Neon's — see §14 for its caveats.

---

### Option C — Fly.io / Railway / Cloud Run

All three work with the same two Dockerfiles:

- **Fly.io** — `fly launch` (detected from Dockerfile), `fly postgres create`,
  set `SENTINEL_DATABASE_URL`, `fly secrets set SENTINEL_AUTH_SECRET=…`,
  `fly deploy`. Set `SENTINEL_API_ORIGIN` to the internal service address.
- **Railway** — add both services from the repo root, add a Postgres plugin,
  set env vars, deploy.
- **Google Cloud Run** — deploy `infra/Dockerfile.backend` and
  `infra/Dockerfile.frontend` as two services; use Cloud SQL for Postgres.
  Cloud Run gives the frontend a public HTTPS URL automatically.

For all three: **set `SENTINEL_API_ORIGIN` to the backend's private/internal
address** (not a public URL) — that's the whole point of the proxy.

---

### 14.1 Production checklist

- [ ] `SENTINEL_APP_ENV=production`
- [ ] `SENTINEL_AUTH_SECRET` = fresh 128+ bits, unique to this env
- [ ] `SENTINEL_ALLOW_DEV_LOGIN=false`
- [ ] `SENTINEL_SEED_DEMO_DATA=false`
- [ ] `SENTINEL_SESSION_COOKIE_SECURE=true` (behind TLS)
- [ ] `SENTINEL_STORE_PROMPT_CONTENT=false`
- [ ] Postgres + `SENTINEL_REDIS_URL` set **before** scaling past 1 replica
- [ ] Schema applied **only** via `alembic upgrade head`, exactly once per release
- [ ] TLS terminated, cookies `Secure` + appropriate `SameSite`
- [ ] Demo account unreachable / DB re-seeded without it
- [ ] `/ready` wired as the readiness probe; `/health` as liveness
- [ ] Provider keys in a secret manager, never in the repo
- [ ] `pg_dump` backup scheduled; `audit/export` snapshot kept

---

## 15. Continuous integration

Two workflows, both path-filtered so unrelated changes don't run them:

- **`.github/workflows/backend.yml`** — Python 3.11, `pip install ".[dev]"`,
  `ruff check . ../ai`, `pytest --cov-fail-under=79`, then
  `alembic upgrade head` + `alembic check` to catch migration drift.
- **`.github/workflows/frontend.yml`** — Node, `npm ci`, `npm run lint`,
  `npm run typecheck`, `npm test`, `npm run build`.

> **Honest status:** GitHub Actions were authored but not executed on the
> authoring host. They re-run exactly the commands in [§12](#12-testing), all
> of which pass locally.

---

## 16. Documentation index

| Document | Read it for |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layering, module map, request lifecycle, the proxy contract |
| [`docs/API.md`](docs/API.md) | Every endpoint, request/response shapes, errors |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Auth, sessions, CSRF, tenancy, secret handling |
| [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) | Assets, adversaries, mitigations, residual risk |
| [`docs/DATABASE.md`](docs/DATABASE.md) | Schema, tables, retention, migration policy |
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | Datasets, runs, metrics, regression testing |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Topologies, Compose, production checklist, rollback |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | The 8-milestone build plan, all boxes ticked with evidence |
| [`SECURITY.md`](SECURITY.md) | How to report a vulnerability |

---

## 17. Troubleshooting

| Symptom | Cause & fix |
|---|---|
| Frontend loads, every API call fails | Backend not running on **8123**, or you set `NEXT_PUBLIC_API_URL` to an absolute origin. Leave it unset (proxy) — the backend has no CORS |
| `403 csrf_failed` | Unsafe request missing `X-CSRF-Token`. Echo the `sentinel_csrf` cookie value in that header |
| `ModuleNotFoundError: No module named 'ai'` | Run from `backend/`, or the repo layout moved — `app/core/bootstrap.py` resolves `ai` three levels above `backend/app/core` |
| `alembic check` reports drift | Stale SQLite WAL. Stop the server and delete `sentinelai.db`, `-wal` **and** `-shm` together, then `alembic upgrade head` |
| Port already in use | 8123/3000 are occupied: `Get-NetTCPConnection -LocalPort 8123,3000 -State Listen` (PowerShell) to find the PID |
| Frontend serves stale chunks / 400 after a rebuild | Restart the frontend — `next start` holds old build IDs: kill :3000 and `npm run build && npm start` |
| PowerShell JSON body errors | Inline quoting breaks; write the body to a file and `--data-binary '@file'` |
| `alembic` "fails" in PowerShell despite success | Alembic logs to stderr; PowerShell reports exit 1. Check the printed revision, not `$LASTEXITCODE` |
| Responses always `demo: true` | Expected — the mock provider is the only one configured. Add a real provider key to reach OpenAI/Anthropic/Gemini |
| Playwright can't find Chrome | This repo uses **bundled Chromium**, not system Chrome: `npx playwright install chromium` |

---

## 18. Design decisions & honest limitations

**Decisions**
- **No CORS middleware, by design** — the frontend proxies instead, keeping
  cookies first-party and the attack surface smaller.
- **Sync SQLAlchemy, not async** — the workload is I/O-light; sync makes
  transaction boundaries obvious and testable.
- **`httpx`, not provider SDKs** — fewer dependencies, pinned behaviour, and
  provider errors surface as typed categories.
- **No silent routing fallback** — fail closed, always.
- **Prompt content off by default** — privacy by default; opt in with
  `SENTINEL_STORE_PROMPT_CONTENT=true` (stores masked text only).
- **`ai/` as a standalone package** — the governance logic is reusable and
  testable without the web stack.

**Limitations (verified, not glossed)**
- **Docker Compose and GitHub Actions are authored but were not executed on
  the authoring host** (Docker unavailable there). Everything else in
  [§12](#12-testing) ran and passed.
- **Python 3.11**, not 3.12 — the spec asked for 3.12; `requires-python` is
  `>=3.11` and CI pins 3.11. It runs on 3.12; only CI is pinned.
- **SQLite in local dev**, Postgres in Compose/prod — some Postgres-only
  behaviour won't surface locally.
- **In-process rate limits** unless `SENTINEL_REDIS_URL` is set — set it
  before running more than one replica.
- **Single-node audit chain** — the chain is verifiable but not externally
  notarized; export snapshots are your independent anchor.
- **Evaluations use deterministic metrics only** — no LLM-as-judge.

---

## Status

Built and verified end to end: 117 backend tests, 26 frontend tests, a live
E2E flow through a running stack, clean lint/type/build gates, and migrations
at head with no drift.

**No `LICENSE` file yet** — until one is added this repository is
all-rights-reserved by its owner. Add an MIT/Apache-2.0 file before you want
others to reuse it.
