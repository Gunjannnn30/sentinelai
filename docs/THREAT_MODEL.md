# Threat Model

Scope: the SentinelAI **backend gateway** (FastAPI + SQLite/Postgres) and its
**console frontend** as deployed by `docker-compose.yml` or an equivalent
production topology. Controls referenced by name are described in
[SECURITY.md](SECURITY.md); data structures in [DATABASE.md](DATABASE.md).

## 1. Assets

| Asset | Why it matters |
|---|---|
| Tenant conversations (prompts/responses) | Confidential customer data; the core privacy asset |
| Provider API keys (`SENTINEL_*_API_KEY`) | Direct financial + data-loss impact if exfiltrated |
| Session signing secret (`SENTINEL_AUTH_SECRET`) | Forging it = full account takeover across all orgs |
| Audit chain (`audit_logs`) | Evidence of who did what; tamper = loss of accountability |
| Org configuration (policies, providers, members) | Changing policy action = disabling guardrails |
| Compute/quota (rate limits, model usage) | Unmetered use = cost blowout (budget fields exist for this) |

## 2. Actors

| Actor | Capability | Trust |
|---|---|---|
| Legitimate console user | Own org, role-limited | Trusted within own tenant |
| Malicious tenant user | Authenticated, tries cross-tenant access & injection | Untrusted across tenants |
| Unauthenticated internet client | Can reach public routes (auth, ops, chat if leaked cookie) | Untrusted |
| Compromised/rogue model provider | Sees what we send, controls responses | Semi-trusted (egress-minimized) |
| Host/DB admin (operator) | Full DB read/write | Trusted (ops role) — out of app's reach |
| Browser attacker (XSS/CSRF) | Runs script in console origin | Untrusted |

## 3. Threats → controls (STRIDE-organized)

### Spoofing
| ID | Threat | Control(s) | Status |
|---|---|---|---|
| T1 | Forge/steal session cookie to impersonate a user | Signed cookie (`itsdangerous` + `SENTINEL_AUTH_SECRET`), HttpOnly, TTL, per-request DB re-validation of user/org/membership | Mitigated |
| T2 | Credential stuffing / brute-force login | scrypt hashing, `login:{ip}:{email}` rate limit, uniform error messages | Mitigated (no MFA yet — residual) |
| T3 | CSRF: attacker site issues state-changing API calls with user's cookies | Double-submit CSRF (`sentinel_csrf` + `X-CSRF-Token`) enforced in middleware for all unsafe methods; SameSite=Lax | Mitigated |
| T4 | Spoofed provider identity (traffic to a wrong endpoint) | Base URLs come from fixed config/DB (`providers.base_url`), never from request payloads | Mitigated |

### Tampering
| ID | Threat | Control(s) | Status |
|---|---|---|---|
| T5 | Modify/delete audit events to hide actions | Per-org hash chain (`seq`, `prev_hash`, `hash`) + `audit/verify` + exportable snapshots | Mitigated for app-level tampering; **residual**: fully privileged DB attacker can recompute the chain (see SECURITY.md §8) |
| T6 | Tamper with policies silently | `policy_versions` snapshots with `version` bump + `changed_by` on every PUT | Mitigated |
| T7 | Cross-tenant data write via parameter tampering | Org scoping from session in every query (`app/services/deps.py`); org id never read from payload | Mitigated (code-level; no DB RLS — residual) |
| T8 | Oversized/hostile payloads | 64 KiB body cap (413), Pydantic field limits, parameterized SQL via ORM | Mitigated |

### Repudiation
| ID | Threat | Control(s) | Status |
|---|---|---|---|
| T9 | "Nobody approved/blocked this" disputes | Every request writes `request_records` + security findings; auth actions (`auth.register` etc.) and admin changes append audit events with actor email + `request_id` correlation | Mitigated |

### Information disclosure
| ID | Threat | Control(s) | Status |
|---|---|---|---|
| T10 | Secrets leak into logs | Whitelisted log fields (method/path/status/duration/request id); headers/bodies never logged; tests assert | Mitigated |
| T11 | PII leaves the boundary (provider egress) | Irreversible PII masking before provider call; credential-shaped content (`api_key`, `jwt`) **blocks** by default policy | Mitigated by default policy (editable by admin — residual: admin can weaken) |
| T12 | Prompts stored in audit/DB in plaintext | `SENTINEL_STORE_PROMPT_CONTENT=false` default; audit `detail` stores rule names/counts/masked types only | Mitigated (opt-in re-enablement is an operator decision) |
| T13 | Provider keys stored in DB leak | DB stores `secret_ref` (name) only; values read from environment at adapter build time | Mitigated |
| T14 | Account enumeration / data probing via API | Uniform login errors; paginated list endpoints scoped to session org | Mitigated |

### Denial of service
| ID | Threat | Control(s) | Status |
|---|---|---|---|
| T15 | Chat flooding / cost blowout | Per-org sliding-window rate limit (429 + `Retry-After`), request-size cap, provider timeouts + bounded retries, org monthly budget field, eval runs bounded by dataset size | Mitigated (per-worker limits; Redis for multi-worker) |
| T16 | Slow/hung provider ties up workers | `SENTINEL_GATEWAY_TIMEOUT_SECONDS` on all provider calls, typed `provider_timeout` errors | Mitigated |
| T17 | Liveness not detected | `/health`, `/ready` (incl. DB check), Docker `HEALTHCHECK` | Mitigated |

### Elevation of privilege
| ID | Threat | Control(s) | Status |
|---|---|---|---|
| T18 | Viewer performs admin mutations | `require_role(minimum)` rank check (`viewer < developer < admin < owner`) on every admin route | Mitigated |
| T19 | User joins an org without membership | Membership created only through register/invite flows; `switch-org` requires an existing membership | Mitigated |
| T20 | Dev login used in production | Gated by `app_env != production` **and** `SENTINEL_ALLOW_DEV_LOGIN` (compose sets false); config validation warns | Mitigated (config-dependent) |
| T21 | Prompt injection steers the model or the gateway | Injection scoring + block policy at score ≥50 (critical/2×high), plus masking policy; `output_guard` on responses; **deterministic policy evaluation happens outside the model** | Partially mitigated — heuristic detection reduces but cannot eliminate injection (documented residual) |

### Provider-specific
| ID | Threat | Control(s) | Status |
|---|---|---|---|
| T22 | Fabricated/misleading model responses presented as real | Only the deterministic `mock` provider synthesizes text and it is always labeled `demo: true`; real providers' failures propagate as typed errors, never replaced with invented content | Mitigated by design |
| T23 | Provider outage cascades | Bounded retries (2) + typed `provider_error`/`provider_timeout`; router fails closed rather than silently degrading constraints | Mitigated |

## 4. Data-flow trust boundaries

```
[Browser] --cookie+CSRF--> |boundary 1| FastAPI session & role checks
                            |boundary 2| guardrails/policy (deterministic, pre-egress)
                            |boundary 3| mask/block before crossing to provider network
                            v
                    [Provider API over HTTPS]
   DB (SQLite/Postgres) <--- app only; secrets read from env, never DB
```

## 5. Residual risks (accepted, documented)

1. **Heuristic prompt-injection detection** (T21) — score-based, not provable.
2. **No DB-level RLS** (T7) — a code bug in one query could cross tenants;
   mitigated by funneling all queries through `deps.py` and org-scoped tests.
3. **Audit chain vs. full-privilege attacker** (T5) — chain detects in-app and
   casual tampering; export snapshots are the external anchor.
4. **No MFA/SSO**, no account lockout beyond rate limits (T2).
5. **Admin can weaken policies** (T11) — admins are trusted; every change is
   versioned + audited.
6. **In-process rate limiting** per worker without Redis (T15).
7. **Compose stack authored but not executed on the authoring host**
   (no Docker available) — first deployment is a verification step.

## 6. Verification evidence

- `backend/tests/` (117 tests) covers: auth/CSRF/RBAC, tenant isolation,
  guardrail detections + masking, policy actions, fail-closed routing,
  provider error paths, audit chain + tamper detection, rate limits,
  validation envelopes.
- `scripts/smoke.py` (6 checks) exercises a live server: register →
  success (demo-labeled) → **blocked** credential prompt → audit verify.
- CI: backend lint+tests+coverage+alembic drift check; frontend
  typecheck+lint+tests+build.
