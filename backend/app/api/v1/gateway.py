"""Models listing + chat completions (the gateway entrypoint)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.ops import bump_requests
from app.db.session import get_db
from app.schemas.common import ChatCompletionIn, ChatCompletionOut, ModelOut, UsageOut
from app.services.deps import AuthContext, get_auth
from app.services.ratelimit import check_rate_limit
from app.services.request_service import execute_chat

router = APIRouter(tags=["gateway"])


@router.get("/models", response_model=list[ModelOut])
def list_models(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> list[ModelOut]:
    """Allowlisted models for the caller's organization only."""
    from app.models.gateway import ModelConfig, Provider

    rows = db.execute(
        select(ModelConfig, Provider)
        .join(Provider, ModelConfig.provider_id == Provider.id)
        .where(ModelConfig.org_id == ctx.org_id)
        .order_by(Provider.kind, ModelConfig.display_name)
    ).all()
    return [
        ModelOut(
            id=m.id, model_key=m.model_key, display_name=m.display_name,
            provider=p.name, provider_kind=p.kind, capabilities=list(m.capabilities or []),
            context_window=m.context_window, input_cost_per_1m=m.input_cost_per_1m,
            output_cost_per_1m=m.output_cost_per_1m, pricing_source=m.pricing_source,
            enabled=m.enabled and p.enabled, is_demo_data=m.is_demo_data,
        )
        for m, p in rows
    ]


@router.post("/chat/completions", response_model=ChatCompletionOut)
def chat_completions(
    payload: ChatCompletionIn,
    request: Request,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ChatCompletionOut:
    """Run one request through the full SentinelAI pipeline.

    Order: auth (dependency) → org access (dependency) → CSRF → rate limit →
    size limit → schema (pydantic) → injection → PII → policies → routing →
    provider → output checks → persist audit → respond.
    """
    bump_requests()
    # CSRF (middleware also enforces — belt and braces for the gateway route).
    from app.core.security import enforce_csrf as _csrf

    _csrf(request)
    check_rate_limit(f"chat:{ctx.org_id}", org_rate_limit(request, ctx, db))
    # Size limit: enforce_content_length runs in middleware on Content-Length.

    outcome, record = execute_chat(
        db,
        org_id=ctx.org_id,
        project_id=payload.project_id,
        actor_user_id=ctx.user_id,
        actor_email=ctx.email,
        actor_role=ctx.role,
        messages=[{"role": m.role, "content": m.content} for m in payload.messages],
        requested_model=payload.model,
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
        dry_run=payload.dry_run,
    )
    db.commit()

    error = None
    if outcome.error:
        error = {
            **outcome.error,
            "policy_outcome": outcome.policy_outcome,
            "blocked_reason": outcome.blocked_reason,
        }

    usage = outcome.usage or {}
    return ChatCompletionOut(
        request_id=record.id,
        status="success" if outcome.status in ("success", "dry_run") else outcome.status,
        policy_outcome=outcome.policy_outcome,
        model=outcome.model,
        provider=outcome.provider,
        content=outcome.content,
        latency_ms=outcome.latency_ms,
        usage=UsageOut(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            estimated_cost_usd=usage.get("estimated_cost_usd"),
            cost_pricing_source=usage.get("cost_pricing_source"),
            pricing_available=bool(usage.get("pricing_available")),
        ),
        findings=outcome.findings,  # type: ignore[arg-type]
        route_explanation=outcome.routing.get("explanation") if outcome.routing else None,
        error=error,
        demo=outcome.provider == "mock",
    )


def org_rate_limit(request: Request, ctx: AuthContext, db: Session) -> int:
    from app.models.identity import Organization

    org = db.get(Organization, ctx.org_id)
    return org.rate_limit_per_minute if org else 60
