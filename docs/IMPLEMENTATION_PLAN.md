# SentinelAI — Implementation Plan

## Environment inspection (2026-10-25)

| Item | Result |
|---|---|
| Working directory | `C:\Users\DELL` (home dir, **not** a git repository) |
| Existing application | None. Project created fresh at `C:\Users\DELL\sentinelai` |
| Python | 3.11.9 (target `>=3.11`; 3.12 recommended — no 3.12 interpreter available on this host) |
| Node / npm | v24.21.0 / 11.19.0 |
| Docker / PostgreSQL / Redis binaries | **Not installed** on host → local dev defaults to SQLite + in-memory rate limiter; Postgres + Redis are provided through `docker-compose.yml` for environments that have Docker |
| Provider API keys (OPENAI/GEMINI/ANTHROPIC) | **Not set** (names checked, values not printed) → external providers are optional; a deterministic local mock provider powers local mode, tests and demo |
| Ollama | Installed (`~/.ollama`) but daemon not running → optional, documented |
| Network / package registry | Reachable (pip + npm verified) |

**Configuration note:** all backend settings are read with the `SENTINEL_`
env prefix (`env_prefix` in `app/core/config.py`); unprefixed names such as
`DATABASE_URL` are silently ignored. Documented backend port for local dev is
**8123** (8000 is occupied on this host).

## Design decisions

1. **Single FastAPI backend** (modular monolith) — no microservices in the MVP. The AI engine lives in a top-level `ai/` package (providers, gateway, guardrails, routing, evaluation) imported by the API layer; repo root is added to `sys.path` by a documented bootstrap (`app/core/bootstrap.py`) so the package boundary stays visible without packaging tricks.
2. **Database**: SQLAlchemy 2 + Alembic. `SENTINEL_DATABASE_URL` may point at PostgreSQL (docker-compose, production) **or** SQLite (local dev without Docker). Same schema, UUID string primary keys, org_id on every tenant-owned row.
3. **Auth**: established session-based implementation — scrypt password hashing (stdlib `hashlib`), signed session cookie (`itsdangerous`), double-submit CSRF token. No custom cryptography, no invented protocol. Roles: owner/admin/developer/viewer, enforced in the backend.
4. **Provider adapters**: common `ProviderAdapter` interface; OpenAI / Anthropic / Gemini via direct REST (`httpx`) — one HTTP stack, deterministic timeouts/retries, no import-time key requirements (documented deviation from "official SDKs where practical"). Ollama optional. A **local mock provider** (clearly labeled `mock` / demo) guarantees a working local mode with zero credentials.
5. **Deterministic routing**: explainable rule engine (policy allowlist → capability → cost/latency preference → admin priority). Fails closed when no compliant model exists.
6. **Guardrails**: regex/rule-based prompt-injection detector + PII detector/masker + declarative policy engine with dry-run. Explicitly documented as *risk signals*, not proof, with known false-positive/negative modes.
7. **Audit**: append-only audit events with an optional SHA-256 **hash chain** (canonical JSON, per-org sequence, concurrency-safe insert + verification endpoint). Raw prompt/response content is **not** stored by default.
8. **Frontend**: Next.js 15 (App Router) + TypeScript strict + Tailwind + hand-built shadcn/ui-style components + Recharts + RHF/Zod. Talks to the FastAPI backend with cookie sessions.

## Milestones / checklist

### M1 — Foundation & shell
- [x] Repo skeleton, branding (SentinelAI), `.gitignore`, `.env.example`
- [x] Backend: config validation (`SENTINEL_*` prefix), structured JSON logging, error envelope, `/health`, `/ready`
- [x] Frontend app shell: sidebar (9 items), top bar, theme, login page *(built by frontend workstream; gates reported separately)*
- [x] `docker-compose.yml` (postgres, redis, backend, frontend), Dockerfiles — *authored; no Docker on this host, see DEPLOYMENT.md*
- [x] CI: backend lint+tests+coverage+alembic drift; frontend typecheck+lint+tests+build — *authored, runs on GitHub*

### M2 — Database, auth, tenancy
- [x] SQLAlchemy models for all required tables; Alembic initial migration (`98827150dfb3`, `alembic check` clean)
- [x] Session auth (register/login/logout/me/switch-org), CSRF middleware, RBAC dependency (`require_role` min-rank)
- [x] Orgs, teams, memberships, projects; org-scoped query enforcement (`app/services/deps.py`)
- [x] Tests: tenant isolation, authorization failures

### M3 — Provider abstraction & working completion
- [x] `ProviderAdapter` interface + OpenAI/Anthropic/Gemini/Ollama/Mock adapters (REST via `httpx`; documented SDK deviation)
- [x] `POST /api/v1/chat/completions`, `GET /api/v1/models`
- [x] Latency, token usage, normalized errors, timeouts, bounded retries (transient only)
- [x] Tests: adapter behavior, missing credentials, timeout/error handling

### M4 — Pipeline, guardrails, routing, audit
- [x] Request pipeline in `ai/gateway/pipeline.py` (injection → PII/mask → policy → route → provider → observe/audit)
- [x] Prompt-injection detector, PII detection/masking, policy engine (allow/warn/mask/block, scopes, versions, preview/dry-run)
- [x] Deterministic router with human-readable explanation (`route_explanation`), fail-closed
- [x] Audit events + hash-chain verification; security events
- [x] Rate limiting (in-process; Redis optional) + request-size limits (413)
- [x] Tests: injection, PII, policy allow/block, routing fail-closed, audit chain, rate limit

### M5 — Dashboard & request history
- [x] Overview metrics from persisted data; request list with search/filters/pagination (backend)
- [x] Request detail + security timeline (backend)
- [x] Frontend tests: navigation, filtering, loading/empty/error states — 26 unit tests (Vitest/RTL); `tsc` + lint clean

### M6 — Administration, model & cost analytics
- [x] Provider config (write-only secrets), model config, policies CRUD + versions, team/roles, retention settings, audit export (CSV/JSON) (backend)
- [x] Cost/security/model analytics endpoints (backend); missing pricing surfaced as *unavailable*
- [x] Frontend admin + analytics pages — all routes built; `npm run build` 15/15 routes green

### M7 — Evaluation harness
- [x] Datasets/cases/runs/results, multi-model runs, deterministic metrics, regression delta, CSV/JSON audit report, synthetic dataset flag
- [x] Tests: metrics, run recording

### M8 — Hardening, deployment, docs, e2e
- [x] Timeouts, retries, metrics endpoint, log redaction (whitelisted log fields), error-envelope catch-alls
- [x] Playwright e2e (register → playground → blocked request → history → audit → analytics) — passing against live stack (chromium)
- [x] Docs: README, ARCHITECTURE, SECURITY, API, DATABASE, THREAT_MODEL, EVALUATION, DEPLOYMENT
- [x] Deployment guide for one practical setup (Docker Compose on a single Linux host)
- [x] Live verification on this host: 113 backend tests green, `ruff check . ../ai` clean, alembic head+check, `scripts/smoke.py` 6/6 against a running server

## Known limitations (tracked, expanded in README)

- Prompt-injection and PII detection are deterministic pattern/risk heuristics — expect false positives and false negatives; they are risk signals, not a safety guarantee.
- Local dev without Docker uses SQLite; production should use PostgreSQL (docker-compose / deployment guide).
- External model providers require user-supplied API keys; the test suite never needs them (mock adapters).
- Host has no Docker daemon — Compose files and CI are provided but could not be executed on this machine; verified instead by running both apps directly.
