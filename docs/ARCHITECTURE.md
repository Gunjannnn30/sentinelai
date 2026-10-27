# Architecture

SentinelAI is a two-app monorepo: a **FastAPI gateway** that mediates every
model call, and a **Next.js console** that drives it. This document describes
the runtime shape of the backend, where responsibilities live, and how a
request flows end to end.

## 1. Layering

The repo has **two** Python packages at the backend boundary:

```
backend/app/        web application (FastAPI)
  app/api/v1/       HTTP layer: routes, auth guards, response models
  app/services/     application services: request_service (gateway orchestration),
                    audit, ratelimit, deps (auth/tenancy), seed
  app/models/       SQLAlchemy 2 models (persistence)
  app/schemas/      Pydantic DTOs shared across layers
  app/core/         config, security (hashing/sessions/CSRF), errors, logging
  app/db/           engine/session
  alembic/          migrations

ai/                 top-level, framework-free domain library (no FastAPI/DB)
  ai/gateway/       pipeline.run_pipeline — the guardrails → policy → route →
                    provider → observe sequence (DB-agnostic; I/O injected)
  ai/guardrails/    pii (find/mask), injection scoring, output_guard,
                    policy_engine (condition evaluation → PolicyRule actions)
  ai/routing/       engine: Candidate / RoutingConstraints / route() — fail-closed
  ai/providers/     base protocol + registry.build_adapter and adapters:
                    mock, openai, anthropic, gemini, ollama (httpx REST)
  ai/evaluation/    metrics: evaluate_case / summarize_results / regression_delta
```

Dependency rule: **`backend/app` → `ai`**, never the reverse; `ai` never
imports `app` (it is testable standalone — the pytest suite covers both).
Inside `app`: **api → services → models/core**. Services never import from
`app.api`; Pydantic schemas are the only DTOs (no ORM objects cross the HTTP
boundary).

## 2. Application composition

`app/main.py` builds the app:

1. `setup_logging()` — structured JSON logs, request-id correlation.
2. `RequestContextMiddleware` — assigns `X-Request-ID`, logs one line per
   request, and enforces **CSRF for cookie-authenticated unsafe methods**.
3. `RequestSizeMiddleware` — rejects bodies over `SENTINEL_MAX_REQUEST_BYTES`
   with 413 *before* they are buffered.
4. Error handlers — `AppError`, `RequestValidationError`, generic `Exception`,
   plus catch-all 404/405 → all return the same envelope
   (`{"error": {code, message, details, request_id}}`).
5. `lifespan` — first-boot seed (demo org/user when
   `SENTINEL_SEED_DEMO_DATA=true` and the DB is empty), config validation
   (`missing_required()` explains missing `SENTINEL_*` names), and
   `Base.metadata.create_all` **only outside production** (production schema is
   owned by Alembic).

## 3. Request lifecycle (chat completion)

```
POST /api/v1/chat/completions
  ├─ RequestContextMiddleware   request id + CSRF (double-submit cookie check)
  ├─ RequestSizeMiddleware      413 guard
  ├─ get_auth                   session cookie → org/user/role context (re-validated
  │                             on every request; no trusted claims cached)
  ├─ org rate limit             in-process sliding window (Redis if configured)
  ├─ request_service.run_pipeline (delegates to ai.gateway.pipeline)
  │   ├─ load org policies + model candidates (DB → plain objects)
  │   ├─ ai.guardrails: pii.find_pii/mask_pii + injection.detect_injection
  │   │                 → findings + score
  │   ├─ ai.guardrails.policy_engine: JSON conditions → PolicyRule actions
  │   │     block   → status=blocked, findings + audit events, NO provider call
  │   │     mask    → prompt content irreversibly masked before provider call
  │   │     warn    → pass-through, findings attached to the record
  │   ├─ ai.routing.route          capability gate → constraints (cost/latency) →
  │   │                         priority → deterministic tie-break; FAIL CLOSED
  │   │                         (no candidate ⇒ typed error, never a
  │   │                         silent fallback)
  │   ├─ ai.providers registry     mock | openai | anthropic | gemini | ollama via
  │   │                         httpx REST; timeout + bounded retries; typed
  │   │                         upstream errors (never invented content)
  │   └─ persist                request_record, security_events, usage_metrics,
  │                             audit append_event (hash-chained)
  └─ ChatCompletionOut          status | policy_outcome | findings | content |
                                usage | demo flag | error{category,...}
```

**Fail-closed guarantees**

- Routing with no eligible model → typed error, no provider call.
- Upstream failure → `status=error` with a real category (`provider_error`,
  `provider_timeout`, `policy_blocked`, `rate_limited`, …), content untouched.
- The `mock` provider is the only synthetic source and is always labeled
  `demo: true`.

## 4. Module map

**Domain library `ai/`** (framework-free)

| Module | Responsibility |
|---|---|
| `ai.gateway.pipeline` | `run_pipeline(...)` — the §3 sequence; accepts an injected adapter factory, so it is fully unit-testable without DB |
| `ai.guardrails.pii` | detectors (SSN, card, email, phone, api_key, jwt) + irreversible `mask_pii` |
| `ai.guardrails.injection` | heuristics for instruction override, secrets exfiltration, hierarchy manipulation, safety bypass → `injection_score` |
| `ai.guardrails.output_guard` | post-response guard (egress checks on provider output) |
| `ai.guardrails.policy_engine` | condition evaluation (`eq/ne/in/gte/...`) → `PolicyRule` action selection |
| `ai.routing.engine` | `Candidate`/`RoutingConstraints`/`route()` — capability gate, cost/latency caps, priority, fail-closed |
| `ai.providers.*` | `base` protocol + `registry.build_adapter` → mock/openai/anthropic/gemini/ollama (httpx) |
| `ai.evaluation.metrics` | `evaluate_case`, `summarize_results`, `regression_delta` (deterministic metrics only) |

**Application `backend/app`**

| Module | Responsibility |
|---|---|
| `app/services/request_service` | DB-aware orchestration: load candidates/policies → call `run_pipeline` → persist `request_record`, `security_events`, `usage_metrics`, audit events; `DEFAULT_POLICY_DEFS` installed per new org; `build_adapter_for` resolves `providers.secret_ref` → `SENTINEL_*` env key |
| `app/services/audit` | `append_event` (seq, prev_hash → hash), `verify_chain`, `audit_summary` |
| `app/services/ratelimit` | sliding-window limiter keyed `register:{ip}`, `login:{ip}:{email}`, `chat:{org_id}`; in-process, Redis optional |
| `app/services/deps` | `get_auth`, `require_role`, org scoping (the tenancy chokepoint) |
| `app/services/seed` | first-boot demo org/user/policies/provider (rows flagged `is_demo_data`) |
| `app/api/v1/analytics_api` | overview/costs/security/models queries over `usage_metrics` |
| `app/api/v1/evals_api` | dataset/case/run endpoints; executes runs through the gateway pipeline and scores with `ai.evaluation.metrics` |
| `app/api/v1/policies_api` | policy CRUD + version snapshots + preview |

## 5. Auth model (summary — details in SECURITY.md)

- `scrypt` password hashing; sessions are **signed cookies**
  (`sentinel_session`, HttpOnly, TTL `SENTINEL_SESSION_TTL_HOURS`) minted with
  `itsdangerous`.
- Companion **CSRF cookie** `sentinel_csrf` (JS-readable) with double-submit
  header `X-CSRF-Token` on every unsafe method. Enforced centrally in
  middleware, so no route can forget it.
- Multi-tenancy: every row carries `org_id`; queries are always filtered by the
  org from the *session*, never from the payload. `Membership.role` ∈
  owner/admin/developer/viewer; admin routes use `require_role(...)`.

## 6. Persistence & state

- **SQLite (dev) / PostgreSQL (compose & prod)** behind SQLAlchemy 2 sync
  sessions (`session_scope` context manager). Async deliberately avoided: all
  work is I/O-light and sync keeps transaction boundaries obvious.
- **Schema**: `Base.metadata.create_all` outside production; **Alembic** is
  authoritative in production (`alembic upgrade head`, CI runs
  `alembic check` to catch drift).
- **Rate limits**: in-process sliding window by default; set
  `SENTINEL_REDIS_URL` for a shared counter when scaling horizontally.
- **Audit chain**: per-org `seq` + `prev_hash` + `hash` over a canonical event
  serialization; `GET /api/v1/admin/audit/verify` recomputes the chain.

## 7. Frontend ↔ backend contract

- The browser calls **same-origin only** (`API_BASE = ""`): `/api/v1/...`,
  `/health`, `/ready`, `/metrics`. `frontend/middleware.ts` forwards those
  paths to the backend (`SENTINEL_API_ORIGIN`, default `http://127.0.0.1:8123`,
  read per request), so the page never talks to :8123 directly. Same
  `POST /api/v1/...` paths as docs/API.md. The equivalent `rewrites()` block in
  `next.config.ts` was removed: Next resolves those at **build** time, which
  would make the proxy target a compile-time constant.
- Why proxy instead of a direct browser call: the API is a different origin
  (3000 → 8123) and the backend ships **no CORS middleware by design**, so
  cross-origin calls are blocked. Proxying keeps the session + CSRF cookies
  first-party (no cross-site SameSite/Secure problems) and adds no attack
  surface — the backend still enforces CSRF, body-size and auth server-side.
  Set `NEXT_PUBLIC_API_URL` to an absolute origin only if you deliberately add
  permissive CORS to the backend.
- Unsafe requests include `X-CSRF-Token` read from the `sentinel_csrf` cookie
  (same rule the backend enforces).
- Every response carries the standard envelope; the UI renders
  `error.message` + `error.request_id` for support.

## 8. Extension points

- **New provider**: implement the adapter protocol (one class, `complete()`),
  register it in `providers.build_adapter`, add config under `SENTINEL_*`.
- **New detector**: add to `guardrails` detectors list — findings flow through
  policies automatically (`pii_type` / `prompt_injection_category` fields).
- **New policy condition field**: extend the condition context in
  `policy.evaluate`; existing policies keep working (JSON conditions, versioned).
- **New metric**: aggregate into `usage_metrics` (documented in DATABASE.md) and
  expose through `analytics`.
