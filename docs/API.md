# API

Base URL: `http://127.0.0.1:8123` (dev) — all endpoints below are prefixed
`/api/v1` unless noted. Interactive docs: **`/docs`** (Swagger UI),
`/redoc`, and the machine spec at **`/api/v1/openapi.json`**. The spec is the
authoritative source for request/response schemas; this file documents
conventions and the catalog.

## Conventions

**Error envelope** — every non-2xx response:

```json
{
  "error": {
    "code": "policy_blocked",
    "message": "Request blocked by policy",
    "details": {"findings": [ ... ], "errors": [{"field": "messages.0.content", "...": "..."}]},
    "request_id": "b31f..."
  }
}
```

- `request_id` is echoed in the `X-Request-ID` response header and appears in
  server logs — quote it in bug reports.
- 422 validation errors put the location under `details.errors[].field`
  (dotted path such as `messages.0.content`), not FastAPI's `loc`.
- 404 (unknown path) and 405 (wrong method) use the same envelope.
- 429 responses include `Retry-After` (seconds).

**Auth** — cookie `sentinel_session` (HttpOnly) + CSRF double-submit:

1. `POST /auth/register` or `POST /auth/login` → sets both cookies; response
   body also returns `csrf_token`.
2. Every unsafe request from an authenticated client sends header
   `X-CSRF-Token: <sentinel_csrf cookie value>`. Missing/incorrect → 403
   `csrf_failed`.
3. `GET /auth/me` validates the session; `POST /auth/logout` → 204.

**Roles**: `owner | admin | developer | viewer` (membership-scoped).
Admin endpoints require `owner|admin`.

## Catalog

### Ops (no auth)
| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness; 200 `{status:"ok", ...}` (also `/api/v1/health`) |
| GET | `/ready` | readiness: `{status, database, checks:{providers_configured, uptime_seconds}}` |
| GET | `/metrics` | process metrics (also `/api/v1/metrics`) |

### Auth
| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/v1/auth/register` | `RegisterIn` {email, password≥8, org_name, full_name?} | **201** `MeOut`; creates org + 4 default policies + mock provider + demo project/team; sets cookies |
| POST | `/api/v1/auth/login` | `LoginIn` | `MeOut` |
| POST | `/api/v1/auth/dev-login` | `DevLoginIn` | dev/test only; disabled in production |
| POST | `/api/v1/auth/logout` | — | **204**, clears cookies |
| GET | `/api/v1/auth/me` | — | `MeOut` {user, org, role, csrf_token, available_providers} |
| POST | `/api/v1/auth/switch-org` | `{org_id}` | requires existing membership |

### Gateway
| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/v1/models` | — | **bare array** of `ModelOut` (`model_key`, provider, capabilities, pricing, `is_demo_data`) |
| POST | `/api/v1/chat/completions` | `ChatCompletionIn` | see below |

`ChatCompletionIn`:

```json
{
  "messages": [{"role": "user", "content": "hi"}],   // 1..50, ≤60k chars each
  "model": "sentinel-mock-small",                    // optional; router picks when omitted
  "project_id": null, "max_tokens": 512, "temperature": 0.7,
  "dry_run": false                                   // true = guardrails+routing only, no provider call
}
```

`ChatCompletionOut` (HTTP **200** in every gateway outcome — read the body):

```json
{
  "request_id": "...", "status": "success | blocked | error",
  "policy_outcome": "allow | warn | block",
  "model": "...", "provider": "...",
  "content": "..." | null,
  "findings": [{"category": "pii", "severity": "...", "rule_name": "...",
                 "action_taken": "...", "detail": "...", "masked_types": ["email"]}],
  "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...,
            "estimated_cost_usd": ..., "pricing_available": false},
  "demo": true,                                      // true when the mock provider served it
  "error": {"category": "policy_blocked | provider_error | ...", "message": "..."}
}
```

- `status=blocked` ⇒ `policy_outcome=block`, `content=null`, no provider call.
- `dry_run=true` ⇒ `content=null`, `usage.total_tokens=null`.
- Mock responses are labeled (`demo=true`) — never presented as model output.

### Requests
| Method | Path | Params |
|---|---|---|
| GET | `/api/v1/requests` | `q, status, policy_outcome, model, error_category, days, project_id, page, page_size` |
| GET | `/api/v1/requests/{request_id}` | — |

### Policies
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/policies` | list org policies (versioned) |
| POST | `/api/v1/policies` | `PolicyIn` (name, severity, action=allow\|warn\|mask\|block, conditions[], scope) |
| GET/PUT/DELETE | `/api/v1/policies/{policy_id}` | PUT bumps `version` + snapshots to `policy_versions` |
| POST | `/api/v1/policies/preview` | `PolicyPreviewIn` — dry evaluation, no side effects |

Condition shape: `{"field": "injection_score", "op": "gte", "value": 50}` with
`pii_type`, `prompt_injection_category`, `policy_outcome`, … as fields.

### Analytics
| Method | Path | Params |
|---|---|---|
| GET | `/api/v1/analytics/overview` | `days` (default 30) |
| GET | `/api/v1/analytics/costs` | `days` |
| GET | `/api/v1/analytics/security` | `days` |
| GET | `/api/v1/analytics/models` | `days` |

### Evaluations
| Method | Path | Body |
|---|---|---|
| GET/POST | `/api/v1/evals/datasets` | `EvalDatasetIn` (`is_synthetic` flag marks demo cases) |
| GET | `/api/v1/evals/datasets/{dataset_id}` | — |
| GET | `/api/v1/evals/datasets/{dataset_id}/cases` | — |
| GET/POST | `/api/v1/evals/runs` | `EvalRunIn` {name, dataset_id, model_keys[]} |
| GET | `/api/v1/evals/runs/{run_id}` | run + results + summary |

### Admin (role = *minimum rank* `viewer < developer < admin < owner`)
| Method | Path | Min role |
|---|---|---|
| GET/POST | `/api/v1/admin/providers` | GET `developer` · POST `admin` |
| PUT | `/api/v1/admin/providers/{provider_id}` | `admin` |
| GET/POST | `/api/v1/admin/models` | GET `developer` · POST `admin` |
| GET/POST | `/api/v1/admin/members` | GET `developer` · POST `admin` |
| GET/POST | `/api/v1/admin/teams` | GET `developer` · POST `admin` |
| GET/POST | `/api/v1/admin/projects` | GET `viewer` · POST `admin` |
| GET/PUT | `/api/v1/admin/settings` | GET `viewer` · PUT `admin` |
| GET | `/api/v1/admin/audit` | `developer` → `{total, items[]}` (`limit, offset`) |
| GET | `/api/v1/admin/audit/verify` | `developer` → `{ok, checked, first_bad_seq?}` |
| GET | `/api/v1/admin/audit/export` | `admin` · `format=csv` *(default)* → `text/csv` attachment, or `format=json` → **bare array** |

(`ProviderIn` stores secrets as `secret_ref` only; `OrgSettingsIn` =
`{retention_days, rate_limit_per_minute, budget_monthly_usd}`.)

## Rate limits (defaults)

| Key | Window | Limit |
|---|---|---|
| `chat:{org_id}` | 1 min | `organizations.rate_limit_per_minute` (default 60) |
| `login:{ip}:{email}` | 1 min | `SENTINEL_LOGIN_RATE_LIMIT_PER_MINUTE` (10) |
| `register:{ip}` | 1 min | login limit |

Backend is sync + single-process in dev; use `SENTINEL_REDIS_URL` for shared
counters when running multiple workers.
