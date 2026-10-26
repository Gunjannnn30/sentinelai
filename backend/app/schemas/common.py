"""Pydantic v2 request/response schemas for the public API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["owner", "admin", "developer", "viewer"]


# ── Auth ────────────────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(default="", max_length=200)
    org_name: str = Field(min_length=2, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class DevLoginIn(BaseModel):
    """Development-only sign-in helper (disabled in production)."""

    email: EmailStr


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str
    retention_days: int
    rate_limit_per_minute: int
    budget_monthly_usd: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    full_name: str


class MeOut(BaseModel):
    user: UserOut
    org: OrgOut
    role: Role
    csrf_token: str
    available_providers: dict[str, bool] = Field(default_factory=dict)


# ── Models & chat ───────────────────────────────────────────────────────────
class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    model_key: str
    display_name: str
    provider: str
    provider_kind: str
    capabilities: list[str]
    context_window: int | None = None
    input_cost_per_1m: float | None = None
    output_cost_per_1m: float | None = None
    pricing_source: str | None = None
    enabled: bool
    is_demo_data: bool = False


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=0, max_length=60_000)


class ChatCompletionIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    model: str | None = None          # model_key; router decides when omitted
    project_id: str | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    dry_run: bool = False             # run guardrails + routing, skip provider call

    @field_validator("messages")
    @classmethod
    def _non_empty_content(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if not any(m.content.strip() for m in v):
            raise ValueError("At least one message must contain non-empty content")
        return v


class SecurityFinding(BaseModel):
    category: str
    severity: str
    rule_name: str
    action_taken: str
    detail: str = ""
    masked_types: list[str] = Field(default_factory=list)


class UsageOut(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    cost_pricing_source: str | None = None
    pricing_available: bool = False


class ChatCompletionOut(BaseModel):
    request_id: str
    status: Literal["success", "blocked", "error"]
    policy_outcome: Literal["allow", "warn", "block"]
    model: str | None = None
    provider: str | None = None
    content: str | None = None
    latency_ms: int | None = None
    usage: UsageOut = Field(default_factory=UsageOut)
    findings: list[SecurityFinding] = Field(default_factory=list)
    route_explanation: str | None = None
    error: dict[str, Any] | None = None
    demo: bool = False


# ── Requests / audit ────────────────────────────────────────────────────────
class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    project_id: str | None = None
    status: str
    policy_outcome: str
    provider_kind: str | None = None
    model_key: str | None = None
    route_explanation: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    cost_pricing_source: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    blocked_reason: str | None = None
    prompt_chars: int = 0
    response_chars: int = 0
    has_content: bool = False
    actor_email: str | None = None
    created_at: datetime
    is_demo_data: bool = False


class SecurityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    request_id: str | None = None
    category: str
    severity: str
    action_taken: str
    rule_name: str
    detail: str
    masked_types: list[str]
    created_at: datetime


class RequestDetailOut(RequestOut):
    security_events: list[SecurityEventOut] = Field(default_factory=list)


class RequestPage(BaseModel):
    items: list[RequestOut]
    total: int
    page: int
    page_size: int


# ── Policies ────────────────────────────────────────────────────────────────
class PolicyCondition(BaseModel):
    field: Literal[
        "prompt_injection_category",
        "pii_type",
        "prompt_contains",
        "model",
        "provider",
        "message_role",
        "project_id",
        "actor_role",
        "prompt_length_over",
        "response_contains",
    ]
    op: Literal["equals", "contains", "in", "gte", "matches"] = "equals"
    value: Any = None


class PolicyIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    action: Literal["allow", "warn", "mask", "block"] = "block"
    scope: Literal["organization", "project", "role"] = "organization"
    scope_role: Role | None = None
    project_id: str | None = None
    conditions: list[PolicyCondition] = Field(default_factory=list, max_length=20)


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    project_id: str | None = None
    name: str
    description: str
    enabled: bool
    severity: str
    action: str
    scope: str
    scope_role: str | None = None
    conditions: list[dict]
    version: int
    created_at: datetime
    updated_at: datetime


class PolicyPreviewIn(BaseModel):
    """Dry-run evaluation of the *unsaved* policy draft against sample input."""

    policy: PolicyIn
    prompt: str = Field(default="", max_length=60_000)
    model: str | None = None
    provider: str | None = None
    actor_role: Role = "developer"
    project_id: str | None = None


class PolicyDecision(BaseModel):
    matched: bool
    action: str
    severity: str
    matched_conditions: list[dict] = Field(default_factory=list)
    explanation: str = ""


class PolicyPreviewOut(BaseModel):
    decision: PolicyDecision
    injection: dict[str, Any] = Field(default_factory=dict)
    pii: dict[str, Any] = Field(default_factory=dict)


# ── Analytics ───────────────────────────────────────────────────────────────
class OverviewOut(BaseModel):
    total_requests: int
    successful_requests: int
    blocked_requests: int
    error_requests: int
    avg_latency_ms: float | None
    estimated_spend_usd: float | None      # None = pricing unavailable for all
    spend_pricing_available: bool
    policy_pass_rate: float | None
    unique_models: int
    demo_data_included: bool
    series: list[dict[str, Any]] = Field(default_factory=list)


class CostBreakdownRow(BaseModel):
    key: str
    requests: int
    tokens: int
    cost_usd: float | None
    pricing_available: bool


class AnalyticsOut(BaseModel):
    by_provider: list[CostBreakdownRow]
    by_model: list[CostBreakdownRow]
    daily: list[dict[str, Any]]
    budget_monthly_usd: str | None = None
    month_to_date_usd: float | None = None
    pricing_source_note: str = ""


class SecurityAnalyticsOut(BaseModel):
    blocked_requests: int
    injection_detections: int
    pii_masking_events: int
    policy_violations: int
    by_severity: dict[str, int]
    top_rules: list[dict[str, Any]]
    series: list[dict[str, Any]] = Field(default_factory=list)


class ModelAnalyticsRow(BaseModel):
    model_key: str
    provider_kind: str
    requests: int
    errors: int
    error_rate: float
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    total_tokens: int
    est_cost_usd: float | None
    pricing_available: bool


class ModelAnalyticsOut(BaseModel):
    rows: list[ModelAnalyticsRow]
    demo_data_included: bool


# ── Evaluation ──────────────────────────────────────────────────────────────
class EvalCaseIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=60_000)
    expected: str = Field(default="", max_length=20_000)
    reference: str = Field(default="", max_length=20_000)
    tags: list[str] = Field(default_factory=list)


class EvalDatasetIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    cases: list[EvalCaseIn] = Field(default_factory=list, max_length=500)


class EvalCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    prompt: str
    expected: str
    reference: str
    tags: list[str]


class EvalDatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    is_synthetic: bool
    created_at: datetime
    case_count: int = 0


class EvalRunIn(BaseModel):
    dataset_id: str
    model_keys: list[str] = Field(min_length=1, max_length=8)
    name: str = Field(min_length=2, max_length=200)
    baseline_run_id: str | None = None


class EvalResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    case_id: str
    model_key: str
    status: str
    output: str | None
    error_category: str | None
    latency_ms: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    metrics: dict


class EvalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dataset_id: str
    name: str
    model_keys: list[str]
    status: str
    baseline_run_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    summary: dict
    created_at: datetime


class EvalRunDetailOut(EvalRunOut):
    results: list[EvalResultOut] = Field(default_factory=list)


# ── Administration ──────────────────────────────────────────────────────────
class ProviderIn(BaseModel):
    kind: Literal["openai", "anthropic", "gemini", "ollama", "mock"]
    name: str = Field(min_length=2, max_length=120)
    base_url: str = Field(default="", max_length=500)
    secret_ref: str = Field(default="", max_length=120)
    enabled: bool = True
    api_key: str | None = Field(default=None, max_length=500)  # write-only, never returned


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    name: str
    base_url: str
    secret_ref: str
    enabled: bool
    configured: bool = False   # credential present server-side?
    model_count: int = 0


class ModelConfigIn(BaseModel):
    provider_id: str
    model_key: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    capabilities: list[str] = Field(default_factory=lambda: ["chat"])
    context_window: int | None = None
    max_output_tokens: int | None = None
    input_cost_per_1m: float | None = Field(default=None, ge=0)
    output_cost_per_1m: float | None = Field(default=None, ge=0)
    pricing_source: str | None = Field(default=None, max_length=200)
    priority: int = 100
    latency_class: Literal["fast", "medium", "slow"] = "medium"
    enabled: bool = True


class MemberIn(BaseModel):
    email: EmailStr
    role: Role


class MemberOut(BaseModel):
    user_id: str
    email: EmailStr
    full_name: str
    role: Role
    teams: list[str] = Field(default_factory=list)


class TeamIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    member_count: int = 0


class ProjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str = Field(default="", max_length=1000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    org_id: str
    name: str
    slug: str
    description: str
    is_default: bool


class OrgSettingsIn(BaseModel):
    retention_days: int = Field(default=90, ge=1, le=3650)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=100_000)
    budget_monthly_usd: str | None = Field(default=None, max_length=32)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    seq: int
    event_type: str
    actor_email: str | None
    resource_type: str
    resource_id: str | None
    request_id: str | None
    outcome: str
    detail: dict
    prev_hash: str
    hash: str
    created_at: datetime


class AuditVerifyOut(BaseModel):
    ok: bool
    checked: int
    first_bad_seq: int | None = None
    message: str


class HealthOut(BaseModel):
    status: str
    service: str = "sentinelai"
    version: str = "0.1.0"
    env: str


class ReadyOut(BaseModel):
    status: str
    database: str
    checks: dict[str, Any] = Field(default_factory=dict)


# date-range helper used by analytics endpoints
class RangeIn(BaseModel):
    days: int = Field(default=7, ge=1, le=90)

    @property
    def start_date(self) -> date:
        from datetime import timedelta

        return date.today() - timedelta(days=self.days - 1)
