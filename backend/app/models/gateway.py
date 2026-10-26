"""Gateway & governance models: providers, models, policies, requests, audit, evaluations."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, id_pk, utcnow


class Provider(Base, TimestampMixin):
    """A configured AI provider for an organization.

    ``secret_ref`` holds the *name* of the environment variable carrying the
    credential (never the value). Secrets stay server-side and are never
    returned by any API response.
    """

    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_provider_org_name"),)

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # openai|anthropic|gemini|ollama|mock
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    models: Mapped[list[ModelConfig]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )


class ModelConfig(Base, TimestampMixin):
    """An allowlisted model with capabilities and (optional) pricing metadata."""

    __tablename__ = "model_configs"
    __table_args__ = (UniqueConstraint("provider_id", "model_key", name="uq_model_provider_key"),)

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_key: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    capabilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # ["chat","tools"]
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_cost_per_1m: Mapped[float | None] = mapped_column(Float, nullable=True)   # USD
    output_cost_per_1m: Mapped[float | None] = mapped_column(Float, nullable=True)  # USD
    pricing_source: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g. "provider list price, 2026-01"
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)  # lower = preferred
    latency_class: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)  # fast|medium|slow
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    provider: Mapped[Provider] = relationship(back_populates="models")


class Policy(Base, TimestampMixin):
    """Declarative security policy with versioned snapshots."""

    __tablename__ = "policies"

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)  # low|medium|high|critical
    action: Mapped[str] = mapped_column(String(16), default="block", nullable=False)  # allow|warn|mask|block
    scope: Mapped[str] = mapped_column(String(16), default="organization", nullable=False)  # organization|project|role
    scope_role: Mapped[str | None] = mapped_column(String(20), nullable=True)  # when scope == "role"
    conditions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    versions: Mapped[list[PolicyVersion]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"

    id: Mapped[str] = id_pk()
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    policy: Mapped[Policy] = relationship(back_populates="versions")


class RequestRecord(Base, TimestampMixin):
    """One gateway call. Content is NOT stored by default — metadata only."""

    __tablename__ = "request_records"

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # success|blocked|error
    policy_outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="allow")  # allow|warn|block
    provider_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    route_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # None = pricing unavailable
    cost_pricing_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Optional content retention (STORE_PROMPT_CONTENT=true) — access-controlled.
    prompt_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    security_events: Mapped[list[SecurityEvent]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class SecurityEvent(Base, TimestampMixin):
    __tablename__ = "security_events"

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("request_records.id", ondelete="CASCADE"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # prompt_injection | pii_detected | policy_violation | rate_limit | output_policy
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    action_taken: Mapped[str] = mapped_column(String(16), default="warn", nullable=False)
    rule_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    detail: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    masked_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    request: Mapped[RequestRecord | None] = relationship(back_populates="security_events")


class AuditLog(Base, TimestampMixin):
    """Append-only audit event with an optional tamper-evident hash chain.

    ``seq`` is per-org, ``hash`` = sha256(canonical_json(event) + prev_hash).
    Rows are never updated or deleted by application code.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (UniqueConstraint("org_id", "seq", name="uq_audit_org_seq"),)

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UsageMetric(Base, TimestampMixin):
    """Daily aggregate per org/model — feeds analytics without scanning requests."""

    __tablename__ = "usage_metrics"
    __table_args__ = (
        UniqueConstraint("org_id", "day", "model_key", name="uq_usage_org_day_model"),
    )

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    model_key: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_kind: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd_sum: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_known_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms_sum: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class EvaluationDataset(Base, TimestampMixin):
    __tablename__ = "evaluation_datasets"

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cases: Mapped[list[EvaluationCase]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class EvaluationCase(Base, TimestampMixin):
    __tablename__ = "evaluation_cases"

    id: Mapped[str] = id_pk()
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reference: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    dataset: Mapped[EvaluationDataset] = relationship(back_populates="cases")


class EvaluationRun(Base, TimestampMixin):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = id_pk()
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_keys: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    baseline_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationResult(Base, TimestampMixin):
    __tablename__ = "evaluation_results"

    id: Mapped[str] = id_pk()
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    model_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")


_ = utcnow  # re-export convenience for importers
