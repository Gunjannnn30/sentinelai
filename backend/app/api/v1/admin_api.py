"""Administration: providers, models, members, teams, projects, settings, audit.

Secrets (``ProviderIn.api_key``) are write-only: accepted here, stored as the
*name* of an environment variable, and never echoed back by any response.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.session import get_db
from app.models.gateway import AuditLog, ModelConfig, Provider
from app.models.identity import Membership, Organization, Project, Team, TeamMember, User
from app.schemas.common import (
    AuditLogOut,
    AuditVerifyOut,
    MemberIn,
    MemberOut,
    ModelConfigIn,
    OrgSettingsIn,
    ProjectIn,
    ProjectOut,
    ProviderIn,
    ProviderOut,
    TeamIn,
    TeamOut,
)
from app.services.audit import append_event, export_events, verify_chain
from app.services.deps import AuthContext, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


def _provider_out(db: Session, p: Provider) -> ProviderOut:
    count = db.execute(
        select(func.count()).select_from(ModelConfig).where(ModelConfig.provider_id == p.id)
    ).scalar_one()
    configured = bool(
        (p.secret_ref and __import__("os").environ.get(p.secret_ref))
        or getattr(app_settings, f"{p.kind}_api_key", "")
    )
    return ProviderOut(
        id=p.id, kind=p.kind, name=p.name, base_url=p.base_url,
        secret_ref=p.secret_ref, enabled=p.enabled,
        configured=configured or p.kind in ("mock", "ollama"), model_count=count,
    )


# ── Providers ───────────────────────────────────────────────────────────────
@router.get("/providers", response_model=list[ProviderOut])
def list_providers(
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> list[ProviderOut]:
    rows = (db.execute(select(Provider).where(Provider.org_id == ctx.org_id)
                       .order_by(Provider.created_at.asc())).scalars().all())
    return [_provider_out(db, p) for p in rows]


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(
    payload: ProviderIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ProviderOut:
    exists = db.execute(
        select(Provider).where(Provider.org_id == ctx.org_id, Provider.name == payload.name)
    ).scalar_one_or_none()
    if exists:
        raise ConflictError("A provider with that name already exists.")
    secret_ref = payload.secret_ref
    if payload.api_key and not secret_ref:
        secret_ref = f"PROVIDER_{payload.kind.upper()}_API_KEY"
    p = Provider(
        org_id=ctx.org_id, kind=payload.kind, name=payload.name,
        base_url=payload.base_url, secret_ref=secret_ref, enabled=payload.enabled,
    )
    db.add(p)
    db.flush()
    # NOTE: the raw api_key is intentionally NOT persisted to the DB. Operators
    # must export it server-side under the name in ``secret_ref``.
    append_event(db, org_id=ctx.org_id, event_type="admin.provider_created",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="provider", resource_id=p.id,
                 detail={"kind": p.kind, "name": p.name, "secret_ref_set": bool(secret_ref)})
    db.commit()
    db.refresh(p)
    return _provider_out(db, p)


@router.put("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(
    provider_id: str,
    payload: ProviderIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ProviderOut:
    p = db.get(Provider, provider_id)
    if p is None or p.org_id != ctx.org_id:
        raise NotFoundError("Provider not found.")
    p.kind, p.name, p.base_url, p.enabled = payload.kind, payload.name, payload.base_url, payload.enabled
    if payload.secret_ref:
        p.secret_ref = payload.secret_ref
    append_event(db, org_id=ctx.org_id, event_type="admin.provider_updated",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="provider", resource_id=p.id, detail={"name": p.name})
    db.commit()
    db.refresh(p)
    return _provider_out(db, p)


# ── Models ──────────────────────────────────────────────────────────────────
@router.get("/models", response_model=list[dict])
def list_model_configs(
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = (db.execute(select(ModelConfig).where(ModelConfig.org_id == ctx.org_id)
                       .order_by(ModelConfig.priority.asc())).scalars().all())
    provider_names = {p.id: p.name for p in
                      db.execute(select(Provider).where(Provider.org_id == ctx.org_id)).scalars()}
    return [{
        "id": m.id, "provider_id": m.provider_id,
        "provider": provider_names.get(m.provider_id, ""),
        "model_key": m.model_key, "display_name": m.display_name,
        "capabilities": m.capabilities, "context_window": m.context_window,
        "max_output_tokens": m.max_output_tokens,
        "input_cost_per_1m": m.input_cost_per_1m, "output_cost_per_1m": m.output_cost_per_1m,
        "pricing_source": m.pricing_source, "priority": m.priority,
        "latency_class": m.latency_class, "enabled": m.enabled,
        "is_demo_data": m.is_demo_data,
    } for m in rows]


@router.post("/models", status_code=201)
def create_model_config(
    payload: ModelConfigIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    provider = db.get(Provider, payload.provider_id)
    if provider is None or provider.org_id != ctx.org_id:
        raise NotFoundError("Provider not found.")
    dup = db.execute(
        select(ModelConfig).where(ModelConfig.org_id == ctx.org_id,
                                  ModelConfig.model_key == payload.model_key)
    ).scalar_one_or_none()
    if dup:
        raise ConflictError("A model with that key already exists.")
    m = ModelConfig(
        org_id=ctx.org_id, provider_id=provider.id, model_key=payload.model_key,
        display_name=payload.display_name, capabilities=payload.capabilities,
        context_window=payload.context_window, max_output_tokens=payload.max_output_tokens,
        input_cost_per_1m=payload.input_cost_per_1m, output_cost_per_1m=payload.output_cost_per_1m,
        pricing_source=payload.pricing_source, priority=payload.priority,
        latency_class=payload.latency_class, enabled=payload.enabled,
    )
    db.add(m)
    db.flush()
    append_event(db, org_id=ctx.org_id, event_type="admin.model_created",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="model_config", resource_id=m.id,
                 detail={"model_key": m.model_key, "provider": provider.name})
    db.commit()
    return {"id": m.id, "model_key": m.model_key, "status": "created"}


# ── Members ─────────────────────────────────────────────────────────────────
@router.get("/members", response_model=list[MemberOut])
def list_members(
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    rows = db.execute(
        select(Membership, User).join(User, User.id == Membership.user_id)
        .where(Membership.org_id == ctx.org_id)
    ).all()
    team_names: dict[str, list[str]] = {}
    for tm, team in db.execute(
        select(TeamMember, Team).join(Team, Team.id == TeamMember.team_id)
        .join(Membership, Membership.user_id == TeamMember.user_id)
        .where(Membership.org_id == ctx.org_id)
    ).all():
        team_names.setdefault(tm.user_id, []).append(team.name)
    return [MemberOut(user_id=u.id, email=u.email, full_name=u.full_name,
                      role=m.role, teams=team_names.get(u.id, []))
            for m, u in rows]


@router.post("/members", response_model=MemberOut, status_code=201)
def upsert_member(
    payload: MemberIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> MemberOut:
    if ctx.role == "admin" and payload.role in ("owner", "admin") and payload.role != ctx.role:
        raise ValidationError("Admins cannot grant owner or admin roles.")
    user = db.execute(select(User).where(User.email == payload.email.lower())).scalar_one_or_none()
    if user is None:
        raise NotFoundError("No account with that email. Ask them to register first.")
    membership = db.execute(
        select(Membership).where(Membership.org_id == ctx.org_id, Membership.user_id == user.id)
    ).scalar_one_or_none()
    if membership is None:
        membership = Membership(org_id=ctx.org_id, user_id=user.id, role=payload.role)
        db.add(membership)
    else:
        membership.role = payload.role
    append_event(db, org_id=ctx.org_id, event_type="admin.member_role_set",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="membership", resource_id=user.id,
                 detail={"email": user.email, "role": payload.role})
    db.commit()
    return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name,
                     role=payload.role)


# ── Teams ───────────────────────────────────────────────────────────────────
@router.get("/teams", response_model=list[TeamOut])
def list_teams(
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> list[TeamOut]:
    rows = db.execute(select(Team).where(Team.org_id == ctx.org_id)).scalars().all()
    out: list[TeamOut] = []
    for t in rows:
        count = db.execute(
            select(func.count()).select_from(TeamMember).where(TeamMember.team_id == t.id)
        ).scalar_one()
        out.append(TeamOut(id=t.id, name=t.name, member_count=count))
    return out


@router.post("/teams", response_model=TeamOut, status_code=201)
def create_team(
    payload: TeamIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> TeamOut:
    t = Team(org_id=ctx.org_id, name=payload.name)
    db.add(t)
    db.flush()
    append_event(db, org_id=ctx.org_id, event_type="admin.team_created",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="team", resource_id=t.id, detail={"name": t.name})
    db.commit()
    return TeamOut(id=t.id, name=t.name, member_count=0)


# ── Projects ────────────────────────────────────────────────────────────────
@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    ctx: AuthContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> list[ProjectOut]:
    rows = (db.execute(select(Project).where(Project.org_id == ctx.org_id)
                       .order_by(Project.created_at.asc())).scalars().all())
    return [ProjectOut.model_validate(p) for p in rows]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ProjectOut:
    dup = db.execute(
        select(Project).where(Project.org_id == ctx.org_id, Project.slug == payload.slug)
    ).scalar_one_or_none()
    if dup:
        raise ConflictError("A project with that slug already exists.")
    p = Project(org_id=ctx.org_id, name=payload.name, slug=payload.slug,
                description=payload.description)
    db.add(p)
    db.flush()
    append_event(db, org_id=ctx.org_id, event_type="admin.project_created",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="project", resource_id=p.id, detail={"slug": p.slug})
    db.commit()
    db.refresh(p)
    return ProjectOut.model_validate(p)


# ── Org settings ────────────────────────────────────────────────────────────
@router.get("/settings")
def get_settings(
    ctx: AuthContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> dict:
    org = db.get(Organization, ctx.org_id)
    assert org is not None
    return {
        "name": org.name, "slug": org.slug,
        "retention_days": org.retention_days,
        "rate_limit_per_minute": org.rate_limit_per_minute,
        "budget_monthly_usd": org.budget_monthly_usd,
    }


@router.put("/settings")
def update_settings(
    payload: OrgSettingsIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    org = db.get(Organization, ctx.org_id)
    assert org is not None
    org.retention_days = payload.retention_days
    org.rate_limit_per_minute = payload.rate_limit_per_minute
    org.budget_monthly_usd = payload.budget_monthly_usd
    append_event(db, org_id=ctx.org_id, event_type="admin.settings_updated",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="organization", resource_id=org.id,
                 detail=payload.model_dump())
    db.commit()
    return {"status": "updated", **payload.model_dump()}


# ── Audit ───────────────────────────────────────────────────────────────────
@router.get("/audit", response_model=dict)
def list_audit(
    limit: int = 50, offset: int = 0,
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> dict:
    limit = max(1, min(limit, 500))
    total = db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.org_id == ctx.org_id)
    ).scalar_one()
    rows = (db.execute(
        select(AuditLog).where(AuditLog.org_id == ctx.org_id)
        .order_by(AuditLog.seq.desc()).offset(offset).limit(limit)
    ).scalars().all())
    return {"total": total, "limit": limit, "offset": offset,
            "items": [AuditLogOut.model_validate(r).model_dump() for r in rows]}


@router.get("/audit/verify", response_model=AuditVerifyOut)
def audit_verify(
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> AuditVerifyOut:
    ok, checked, first_bad, message = verify_chain(db, ctx.org_id)
    return AuditVerifyOut(ok=ok, checked=checked, first_bad_seq=first_bad, message=message)


@router.get("/audit/export")
def audit_export(
    format: str = "csv",
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Response:
    rows = export_events(db, ctx.org_id)
    append_event(db, org_id=ctx.org_id, event_type="admin.audit_exported",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="audit_log", detail={"format": format, "rows": len(rows)})
    db.commit()
    if format not in ("csv", "json"):
        raise ValidationError("format must be 'csv' or 'json'.")
    if format == "json":
        import json

        body = json.dumps([AuditLogOut.model_validate(r).model_dump(mode="json") for r in rows])
        return Response(content=body, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="audit.json"'})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["seq", "event_type", "actor_email", "resource_type", "resource_id",
                     "outcome", "hash", "prev_hash", "created_at"])
    for r in rows:
        writer.writerow([r.seq, r.event_type, r.actor_email, r.resource_type,
                         r.resource_id, r.outcome, r.hash, r.prev_hash,
                         r.created_at.isoformat()])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="audit.csv"'})
