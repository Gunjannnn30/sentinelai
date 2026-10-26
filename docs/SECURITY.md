# Security

Controls implemented in this repository, what they do, and what they do **not**
cover. Threat-model detail lives in [THREAT_MODEL.md](THREAT_MODEL.md).

## 1. Authentication

- **Password hashing**: `scrypt` (stdlib `hashlib`, n=2^14, r=8, p=1) with a
  per-password random salt; stored as `scrypt$n$r$p$salt$hash`. No plain or
  fast-hash (MD5/SHAx) anywhere.
- **Sessions**: signed opaque cookie `sentinel_session` (HttpOnly, SameSite
  Lax) minted with `itsdangerous` using `SENTINEL_AUTH_SECRET`; payload =
  user id + org id + expiry, TTL `SENTINEL_SESSION_TTL_HOURS` (default 12).
  `SENTINEL_SESSION_COOKIE_SECURE=true` must be set behind TLS.
- **Per-request validation**: `get_auth` re-reads the cookie, verifies the
  signature, and re-checks the user/org/membership in the DB on *every*
  request — a revoked member or disabled org loses access immediately.
- **Login throttling**: `login:{ip}:{email}` rate limit
  (`SENTINEL_LOGIN_RATE_LIMIT_PER_MINUTE`, default 10/min) plus a generic
  failure message (no account enumeration).
- **Registration throttling**: `register:{ip}` window limits signup spam.
- **`POST /api/v1/auth/dev-login`** is a dev convenience, guarded twice:
  disabled entirely in `production`, and additionally by
  `SENTINEL_ALLOW_DEV_LOGIN=false` (compose sets it false). Startup config
  validation warns loudly if it would be enabled in production.

## 2. CSRF

- Double-submit token: `sentinel_csrf` is set as a **JS-readable** cookie; all
  unsafe methods (POST/PUT/PATCH/DELETE) from a cookie-authenticated client
  must send `X-CSRF-Token` with the same value. Enforced once in
  middleware (`app.core.security.enforce_csrf`) so no individual route can
  forget it. Failure → 403 `csrf_failed` envelope.
- Session cookie is HttpOnly + SameSite=Lax as defense in depth.

## 3. Authorization (RBAC) & tenant isolation

- Roles per membership: `owner` > `admin` > `developer` > `viewer`
  (role checks are *minimum rank*: `require_role("admin")` accepts admin **and**
  owner). Mutations on providers/models/members/settings require admin+;
  configuration reads require developer+; audit/settings reads allow viewer.
- **Server-side org scoping**: every query filters by the org resolved from the
  session. Org id is *never* taken from request bodies or query strings, so
  cross-tenant reads require breaking the session signer (see threats T1).
- Multi-org users switch orgs only through `POST /auth/switch-org`, which
  requires an existing membership (checked server-side).

## 4. Secrets & sensitive data

- **Never logged**: logging fields are whitelisted (method, path, status,
  request id, duration). Headers, cookies, bodies, and provider keys are never
  emitted; tests assert this.
- **Provider keys** come from `SENTINEL_*_API_KEY` env vars. The DB stores only
  `providers.secret_ref` (a name/reference), never the value.
- **Prompt/response content is off by default**
  (`SENTINEL_STORE_PROMPT_CONTENT=false`). When enabled, guardrails run first
  and the *masked* form is stored (emails/phones irreversibly replaced;
  credential-shaped strings never reach storage or the provider).
- **Audit log content**: audit `detail` JSON carries rule names, masked types,
  counts — not raw user text.
- `.env` is gitignored; `.env.example` contains placeholders only.

## 5. Input & abuse controls

- Request-size guard: bodies > `SENTINEL_MAX_REQUEST_BYTES` (64 KiB) → 413
  before parsing.
- Field limits enforced by Pydantic (message content ≤ 60k chars, ≤ 50
  messages, bounded temperatures/tokens).
- Per-org sliding-window rate limit on chat (`SENTINEL_RATE_LIMIT_PER_MINUTE`
  or `organizations.rate_limit_per_minute`) → 429 with `Retry-After`.
- Validation failures return the envelope with `details.errors[].field` (no
  stack traces, no SQL, no internal paths).

## 6. Gateway policy controls

- Guardrail findings feed versioned policies with explicit actions:
  `block` (request never reaches a provider), `mask` (irreversible redaction
  before egress), `warn` (pass + record), `allow`.
- Credential-shaped content (`api_key`, `jwt`) blocks by default policy —
  secrets cannot leave the boundary even if a user pastes one.
- Router **fails closed**: no eligible model ⇒ typed error, never a silent
  fallback to a model outside the capability/cost constraints.

## 7. Transport, headers, infrastructure

- Cookie flags: HttpOnly (session), SameSite=Lax, Secure configurable.
- Compose/production guidance: terminate TLS at a reverse proxy, set
  `SENTINEL_SESSION_COOKIE_SECURE=true`, put the DB on an internal network,
  set a unique `SENTINEL_AUTH_SECRET` (128-bit+ random) per environment.
- Non-root user in both Docker images; minimal base images; pinned dependency
  versions in `pyproject.toml`.

## 8. Audit integrity

- Events are hash-chained per org (`seq`, `prev_hash`, `hash` over a canonical
  serialization including the previous hash).
- `GET /api/v1/admin/audit/verify` recomputes and reports the first broken
  position; `GET /admin/audit/verify` returns `ok=false` on tampering.
- Honest limitation: an attacker with **database write access** could recompute
  the whole chain. The chain detects in-application tampering and casual
  SQL edits, not a fully privileged, chain-aware attacker. Export snapshots
  (audit export endpoint) provide an external anchor.

## 9. Denial of service & availability

- Rate limits (above), bounded provider timeouts
  (`SENTINEL_GATEWAY_TIMEOUT_SECONDS`) and retries
  (`SENTINEL_GATEWAY_MAX_RETRIES`), request-size caps, `/health` + `/ready`
  probes for orchestration, and typed errors instead of 500-by-default.

## 10. Explicit non-goals / residual risks

- No SSO/OIDC, MFA, or account-recovery flows yet (cookie sessions only).
- No per-field encryption at rest; DB access is the trust boundary.
- In-process rate limits are per-worker (use Redis when scaling out).
- No automated dependency scanning in CI (only lint/type/test/build gates).
- Prompt-injection detection is heuristic (score-based) — it reduces, not
  eliminates, injection risk.

## Reporting a vulnerability

Open a private security advisory on the repository (or contact the
maintainers). Do not file public issues for exploitable vulnerabilities.
Please include the `request_id` from the error envelope when reporting
server-side issues.
