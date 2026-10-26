"""Request history: search, filter, paginate, detail + security timeline."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models.gateway import RequestRecord, SecurityEvent
from app.models.identity import User
from app.schemas.common import RequestDetailOut, RequestOut, RequestPage, SecurityEventOut
from app.services.deps import AuthContext, get_auth

router = APIRouter(prefix="/requests", tags=["requests"])


def _to_out(rec: RequestRecord, actor_email: str | None = None) -> RequestOut:
    return RequestOut(
        id=rec.id, org_id=rec.org_id, project_id=rec.project_id, status=rec.status,
        policy_outcome=rec.policy_outcome, provider_kind=rec.provider_kind,
        model_key=rec.model_key, route_explanation=rec.route_explanation,
        latency_ms=rec.latency_ms, prompt_tokens=rec.prompt_tokens,
        completion_tokens=rec.completion_tokens, total_tokens=rec.total_tokens,
        estimated_cost_usd=rec.estimated_cost_usd,
        cost_pricing_source=rec.cost_pricing_source,
        error_category=rec.error_category, error_message=rec.error_message,
        blocked_reason=rec.blocked_reason, prompt_chars=rec.prompt_chars,
        response_chars=rec.response_chars,
        has_content=bool(rec.response_content),
        actor_email=actor_email, created_at=rec.created_at,
        is_demo_data=rec.is_demo_data,
    )


@router.get("", response_model=RequestPage)
def list_requests(
    q: str | None = Query(default=None, description="Request ID (exact or prefix)"),
    status: str | None = Query(default=None, pattern="^(success|blocked|error)$"),
    policy_outcome: str | None = Query(default=None, pattern="^(allow|warn|block)$"),
    model: str | None = Query(default=None),
    error_category: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    project_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> RequestPage:
    since = datetime.now(UTC) - timedelta(days=days)
    stmt = select(RequestRecord).where(RequestRecord.org_id == ctx.org_id,
                                       RequestRecord.created_at >= since)
    if q:
        stmt = stmt.where(or_(RequestRecord.id == q, RequestRecord.id.like(f"{q}%")))
    if status:
        stmt = stmt.where(RequestRecord.status == status)
    if policy_outcome:
        stmt = stmt.where(RequestRecord.policy_outcome == policy_outcome)
    if model:
        stmt = stmt.where(RequestRecord.model_key == model)
    if error_category:
        stmt = stmt.where(RequestRecord.error_category == error_category)
    if project_id:
        stmt = stmt.where(RequestRecord.project_id == project_id)

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(RequestRecord.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )
    emails = _actor_emails(db, {r.actor_user_id for r in rows})
    return RequestPage(
        items=[_to_out(r, emails.get(r.actor_user_id)) for r in rows],
        total=total, page=page, page_size=page_size,
    )


def _actor_emails(db: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.email).where(User.id.in_(ids))).all()
    return {i: e for i, e in rows}


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: str,
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> RequestDetailOut:
    rec = db.get(RequestRecord, request_id)
    # Tenant isolation: another org's ID must look identical to a missing one.
    if rec is None or rec.org_id != ctx.org_id:
        raise NotFoundError("Request not found.")
    events = (
        db.execute(
            select(SecurityEvent)
            .where(SecurityEvent.request_id == rec.id)
            .order_by(SecurityEvent.created_at.asc())
        )
        .scalars()
        .all()
    )
    email = db.execute(select(User.email).where(User.id == rec.actor_user_id)).scalar_one_or_none()
    out = _to_out(rec, email)
    return RequestDetailOut(
        **out.model_dump(),
        security_events=[SecurityEventOut.model_validate(e) for e in events],
    )
