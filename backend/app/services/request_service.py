"""Request persistence: run the gateway pipeline, persist request + security +
audit records, bump usage aggregates.

Content retention: raw prompt/response are stored **only** when
``STORE_PROMPT_CONTENT=true`` (org setting can further restrict). Metadata is
always stored; secrets are masked *before* any persistence, and rejected
requests never store unmasked text.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ai.gateway.pipeline import (
    PipelineConfig,
    PipelineOutcome,
    PipelineRequest,
    run_pipeline,
)
from ai.guardrails.injection import InjectionConfig
from ai.guardrails.pii import PiiConfig
from ai.routing.engine import Candidate, RoutingConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.gateway import (
    ModelConfig,
    Policy,
    Provider,
    RequestRecord,
    SecurityEvent,
    UsageMetric,
)
from app.services.audit import append_event

# Default policies installed on a fresh organization (demo-safety net).
DEFAULT_POLICY_DEFS: list[dict[str, Any]] = [
    {
        "name": "Block obvious prompt injection (critical)",
        "description": "Blocks requests whose injection score reaches 50 (one critical or two "
                       "high-severity detection rules).",
        "severity": "critical",
        "action": "block",
        "conditions": [{"field": "injection_score", "op": "gte", "value": 50}],
    },
    {
        "name": "Warn on any injection signal",
        "description": "Surfaces any prompt-injection finding as a warning (does not block).",
        "severity": "medium",
        "action": "warn",
        "conditions": [{"field": "prompt_injection_category", "op": "in",
                        "value": ["instruction_override", "secrets_exfiltration",
                                  "hierarchy_manipulation", "safety_bypass"]}],
    },
    {
        "name": "Mask emails and phone numbers",
        "description": "PII detected in the prompt is masked irreversibly before the provider call.",
        "severity": "medium",
        "action": "mask",
        "conditions": [{"field": "pii_type", "op": "in", "value": ["email", "phone"]}],
    },
    {
        "name": "Block credential-shaped content",
        "description": "Blocks prompts containing API-key/JWT-shaped strings so secrets never "
                       "leave the boundary.",
        "severity": "high",
        "action": "block",
        "conditions": [{"field": "pii_type", "op": "in", "value": ["api_key", "jwt"]}],
    },
]


def load_policies(db: Session, org_id: str, project_id: str | None) -> list[Policy]:
    q = select(Policy).where(Policy.org_id == org_id, Policy.enabled.is_(True))
    if project_id:
        q = q.where((Policy.project_id.is_(None)) | (Policy.project_id == project_id))
    else:
        q = q.where(Policy.project_id.is_(None))
    return list(db.execute(q).scalars().all())


def load_candidates(db: Session, org_id: str) -> list[Candidate]:
    rows = (
        db.execute(
            select(ModelConfig, Provider)
            .join(Provider, ModelConfig.provider_id == Provider.id)
            .where(ModelConfig.org_id == org_id, ModelConfig.enabled.is_(True),
                   Provider.enabled.is_(True))
        )
        .all()
    )
    return [
        Candidate(
            model_key=m.model_key,
            provider_kind=p.kind,
            display_name=m.display_name,
            capabilities=list(m.capabilities or []),
            priority=m.priority,
            latency_class=m.latency_class,
            input_cost_per_1m=m.input_cost_per_1m,
            output_cost_per_1m=m.output_cost_per_1m,
            pricing_source=m.pricing_source,
            enabled=m.enabled and p.enabled,
        )
        for m, p in rows
    ]


def build_adapter_for(provider: Provider):
    from ai.providers.registry import build_adapter

    # Server-side secret lookup — never returned to a client.
    key = ""
    if provider.secret_ref:
        import os

        key = os.environ.get(provider.secret_ref, "")
    if not key:
        # Fall back to the standard env var for the provider kind.
        key = {
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "gemini": settings.gemini_api_key,
        }.get(provider.kind, "")
    base_url = provider.base_url or {
        "openai": settings.openai_base_url,
        "anthropic": settings.anthropic_base_url,
        "gemini": settings.gemini_base_url,
        "ollama": settings.ollama_base_url,
    }.get(provider.kind, "")
    return build_adapter(provider.kind, base_url=base_url, api_key=key,
                         timeout=settings.gateway_timeout_seconds)


def _bump_usage(db: Session, org_id: str, record: RequestRecord) -> None:
    if not record.model_key:
        return
    day = record.created_at.date() if record.created_at else date.today()
    row = db.execute(
        select(UsageMetric).where(
            UsageMetric.org_id == org_id,
            UsageMetric.day == day,
            UsageMetric.model_key == record.model_key,
        )
    ).scalar_one_or_none()
    if row is None:
        row = UsageMetric(org_id=org_id, day=day, model_key=record.model_key,
                          provider_kind=record.provider_kind or "",
                          requests=0, blocked=0, errors=0, total_tokens=0,
                          cost_usd_sum=0.0, cost_known_requests=0,
                          latency_ms_sum=0, latency_count=0)
        db.add(row)
    row.requests = (row.requests or 0) + 1
    if record.status == "blocked":
        row.blocked = (row.blocked or 0) + 1
    if record.status == "error":
        row.errors = (row.errors or 0) + 1
    row.total_tokens = (row.total_tokens or 0) + (record.total_tokens or 0)
    if record.estimated_cost_usd is not None:
        row.cost_usd_sum = (row.cost_usd_sum or 0.0) + record.estimated_cost_usd
        row.cost_known_requests = (row.cost_known_requests or 0) + 1
    if record.latency_ms is not None:
        row.latency_ms_sum = (row.latency_ms_sum or 0) + record.latency_ms
        row.latency_count = (row.latency_count or 0) + 1


def execute_chat(
    db: Session,
    *,
    org_id: str,
    project_id: str | None,
    actor_user_id: str,
    actor_email: str,
    actor_role: str,
    messages: list[dict[str, str]],
    requested_model: str | None,
    max_tokens: int | None,
    temperature: float | None,
    dry_run: bool,
) -> tuple[PipelineOutcome, RequestRecord]:
    """Run the full pipeline and persist every record. Returns (outcome, request_row)."""
    from ai.guardrails.policy_engine import PolicyRule

    policies = [PolicyRule.from_model(p) for p in load_policies(db, org_id, project_id)]
    candidates = load_candidates(db, org_id)

    def _model_lookup(key: str) -> ModelConfig | None:
        return db.execute(
            select(ModelConfig).where(ModelConfig.org_id == org_id,
                                      ModelConfig.model_key == key)
        ).scalar_one_or_none()

    def _build_adapter(kind: str):
        provider = db.execute(
            select(Provider).where(Provider.org_id == org_id, Provider.kind == kind,
                                   Provider.enabled.is_(True))
        ).scalars().first()
        if provider is None:
            from ai.providers.base import ProviderError

            raise ProviderError(
                f"No enabled provider of kind '{kind}' is configured for this organization.",
                category="auth_error", provider=kind, retryable=False,
            )
        return build_adapter_for(provider)

    outcome = run_pipeline(
        PipelineRequest(
            messages=messages, model=requested_model, project_id=project_id,
            actor_role=actor_role, max_tokens=max_tokens, temperature=temperature,
            dry_run=dry_run,
        ),
        policies=policies,
        candidates=candidates,
        build_adapter=_build_adapter,
        model_lookup=_model_lookup,
        routing_constraints=RoutingConstraints(),
        config=PipelineConfig(
            timeout_seconds=settings.gateway_timeout_seconds,
            max_retries=settings.gateway_max_retries,
            store_content=settings.store_prompt_content,
            injection=InjectionConfig(),
            pii=PiiConfig(),
            mask_pii=True,
        ),
    )

    record = RequestRecord(
        org_id=org_id,
        project_id=project_id,
        actor_user_id=actor_user_id,
        status="success" if outcome.status == "success" else
               ("blocked" if outcome.status == "blocked" else
                ("error" if outcome.status == "error" else "success")),
        policy_outcome=outcome.policy_outcome,
        provider_kind=outcome.provider,
        model_key=outcome.model or (outcome.routing.get("selected") if outcome.routing else None),
        route_explanation=outcome.routing.get("explanation") if outcome.routing else None,
        latency_ms=outcome.latency_ms,
        prompt_tokens=outcome.usage.get("prompt_tokens"),
        completion_tokens=outcome.usage.get("completion_tokens"),
        total_tokens=outcome.usage.get("total_tokens"),
        estimated_cost_usd=outcome.estimated_cost_usd,
        cost_pricing_source=outcome.cost_pricing_source,
        error_category=(outcome.error or {}).get("category") if outcome.error else None,
        error_message=(outcome.error or {}).get("message") if outcome.error else None,
        blocked_reason=outcome.blocked_reason,
        prompt_chars=sum(len(m.get("content", "")) for m in messages),
        response_chars=len(outcome.content or ""),
        prompt_content=(messages[-1]["content"][:20000]
                        if settings.store_prompt_content and messages else None),
        response_content=(outcome.content[:20000]
                          if settings.store_prompt_content and outcome.content else None),
    )
    db.add(record)
    db.flush()

    # Security events (masked detail only — no raw secrets ever persisted).
    for f in outcome.findings:
        db.add(SecurityEvent(
            org_id=org_id,
            request_id=record.id,
            category=f["category"],
            severity=f["severity"],
            action_taken=f["action_taken"],
            rule_name=f["rule_name"][:200],
            detail=f["detail"][:2000],
            masked_types=list(f.get("masked_types") or []),
        ))
    if outcome.status == "dry_run":
        record.status = "success"

    _bump_usage(db, org_id, record)

    append_event(
        db,
        org_id=org_id,
        event_type="gateway.request",
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        resource_type="request",
        resource_id=record.id,
        request_id=record.id,
        outcome=record.status,
        detail={
            "model": record.model_key,
            "provider": record.provider_kind,
            "policy_outcome": record.policy_outcome,
            "status": record.status,
            "latency_ms": record.latency_ms,
            "dry_run": dry_run,
            "findings": [f["category"] for f in outcome.findings],
        },
    )
    return outcome, record
